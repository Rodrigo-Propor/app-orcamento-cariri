import pandas as pd
import numpy as np
from pathlib import Path
import math

class OrcamentoService:
    def __init__(self, po_file="PO.xlsx", sinapi_file="SINAPI_Referência_2024_08.xlsx"):
        self.po_file = po_file
        self.sinapi_file = sinapi_file
        self.po_items = []
        self.sinapi_prices = {}
        self.comp_map = {} # parent -> list of {code, coef}
        self.po_prices = {} # code -> price from PO
        self.calculated_prices = {} # code -> calculated price
        self.composition_details = {} # code -> list of components
        self.is_loaded = False

    def normalize_val(self, v):
        if pd.isna(v): return None
        s = str(v).strip().upper()
        if s.endswith('.0'): s = s[:-2]
        return s

    def sanitize_for_json(self, data):
        # Recursively sanitize data for JSON (handle NaN, Infinity)
        if isinstance(data, list):
            return [self.sanitize_for_json(i) for i in data]
        elif isinstance(data, dict):
            return {k: self.sanitize_for_json(v) for k, v in data.items()}
        elif isinstance(data, float):
            if pd.isna(data) or math.isinf(data):
                return None
            return data
        return data

    def load_and_calculate(self):
        print("Loading PO items...")
        self._load_po()
        print("Loading SINAPI...")
        self._load_sinapi()
        print("Calculating...")
        self._calculate_compositions()
        self._apply_fallback_logic()
        self.is_loaded = True
        print("Data loaded and calculated.")

    def _load_po(self):
        if not Path(self.po_file).exists():
            print(f"PO File not found: {self.po_file}")
            return

        # PO.xlsx: Data starts around row 12.
        df = pd.read_excel(self.po_file, sheet_name="PO", skiprows=12, header=None)
        
        for _, row in df.iterrows():
            po_idx = str(row[0]).strip()
            if po_idx == 'nan' or po_idx == 'ITEM': continue
            
            source = self.normalize_val(row[1])
            code = self.normalize_val(row[2])
            desc = row[3]
            unit = row[4]

            # BDI - Assuming it might be in the sheet or fixed. 
            # The MVP text says "BDI % (da PO)". 
            # Looking at PO.xlsx logic in previous script, it didn't explicitly capture BDI column.
            # I'll check if there's a BDI column later, for now assume 0 or 25% if not found.
            # Let's assume a standard BDI or look for it.
            # For this MVP, I'll default to a placeholder if not in row.
            
            # Header Detection
            if not source:
                item_type = "HEADER"
                if code and (pd.isna(desc) or str(desc).strip() == ""):
                    desc = row[2]
                    code = ""
            else:
                item_type = "ITEM"
            try:
                qty = float(row[5]) if not pd.isna(row[5]) else 0.0
            except:
                qty = 0.0
            
            # Capture BDI
            try:
                bdi = float(row[12]) if not pd.isna(row[12]) else 0.0
            except:
                bdi = 0.0

            # Capture manual price (Col 8 based on inspection)
            try:
                p_val = row[8]
                if isinstance(p_val, str): p_val = p_val.replace(',', '.')
                p_float = float(p_val)
            except:
                p_float = 0.0

            self.po_items.append({
                "idx": po_idx, 
                "source": source, 
                "code": code, 
                "desc": desc, 
                "unit": unit,
                "qty": qty,
                "manual_price": p_float,
                "type": item_type,
                "bdi_percent": bdi
            })
            
            if code and item_type == "ITEM":
                self.po_prices[code] = p_float

    def _load_sinapi(self):
        if not Path(self.sinapi_file).exists():
            print(f"SINAPI File not found: {self.sinapi_file}")
            return

        # Load Prices (ISD & CSD)
        def load_prices(sheet_name, price_col_idx):
            try:
                df_x = pd.read_excel(self.sinapi_file, sheet_name=sheet_name, header=None, skiprows=10)
                for _, row in df_x.iterrows():
                    raw_c = row[1]
                    if pd.isna(raw_c): continue
                    c_x = str(raw_c).strip()
                    if c_x.endswith('.0'): c_x = c_x[:-2]
                    
                    if c_x:
                        val_float = 0.0
                        found = False
                        
                        # Try primary column
                        if price_col_idx < len(row):
                            p_val = row[price_col_idx]
                            try:
                                if isinstance(p_val, str): p_val = p_val.replace(',', '.')
                                val_float = float(p_val)
                                if val_float > 0: found = True
                            except:
                                pass
                        
                        # Fallback scan
                        if not found or val_float == 0:
                            for idx in range(4, len(row)):
                                if idx == price_col_idx: continue
                                try:
                                    v = row[idx]
                                    if isinstance(v, (int, float)) and not pd.isna(v) and v > 0:
                                        val_float = float(v)
                                        found = True
                                        break
                                except:
                                    pass

                        if found:
                            self.sinapi_prices[c_x] = val_float
            except Exception as e:
                print(f"Error loading {sheet_name}: {e}")

        load_prices("ISD", 30)
        load_prices("CSD", 54)

        # Load Analítico
        try:
            df = pd.read_excel(self.sinapi_file, sheet_name="Analítico", header=None, skiprows=5)
            current_comp_calc = None
            
            for _, row in df.iterrows():
                c_comp = self.normalize_val(row[1])
                if not c_comp: continue
                
                tipo = str(row[2]).strip().upper()
                if tipo in ["NAN", "", "NONE"] or pd.isna(row[2]):
                    current_comp_calc = c_comp
                    if current_comp_calc not in self.comp_map:
                        self.comp_map[current_comp_calc] = []
                elif current_comp_calc:
                    r_code = self.normalize_val(row[3])
                    if not r_code: continue
                    try:
                        coef = float(row[6]) if not pd.isna(row[6]) else 0.0
                    except:
                        coef = 0.0
                    
                    self.comp_map[current_comp_calc].append({
                        'code': r_code, 
                        'coef': coef,
                        'desc': row[4],
                        'unit': row[5]
                    })
        except Exception as e:
            print(f"Error loading Analítico: {e}")

    def _calculate_compositions(self):
        # Iterative calculation
        for i in range(15):
            added_count = 0
            for parent, children in self.comp_map.items():
                if parent in self.sinapi_prices:
                    continue 
                
                total = 0.0
                ready = True
                
                for child in children:
                    c_code = child['code']
                    c_coef = child['coef']
                    
                    if c_code in self.sinapi_prices:
                        total += self.sinapi_prices[c_code] * c_coef
                    else:
                        if c_code in self.comp_map:
                            ready = False
                            break
                        else:
                            # Missing input, assume 0
                            pass
                
                if ready:
                    self.sinapi_prices[parent] = total
                    added_count += 1
            
            if added_count == 0:
                break

    def _apply_fallback_logic(self):
        # Map final prices to PO Items
        for item in self.po_items:
            if item['type'] == 'HEADER':
                item['final_unit_price'] = 0.0
                item['total_price'] = 0.0
                item['origin'] = 'HEADER'
                continue

            code = item['code']
            price = 0.0
            origin = 'SEM_PREÇO'
            
            # 1. Calculated / SINAPI
            if code in self.sinapi_prices:
                price = self.sinapi_prices[code]
                if price > 0:
                    if code in self.comp_map:
                        origin = 'CALCULADO'
                    else:
                        origin = 'SINAPI_DIRETO'
            
            # 2. Fallback PO Manual
            if price == 0 and code in self.po_prices:
                price = self.po_prices[code]
                if price > 0:
                    origin = 'PO_MANUAL'
            
            item['final_unit_price'] = price
            item['total_price'] = price * item['qty']
            item['origin'] = origin
            
            # BDI Calcs
            bdi = item.get('bdi_percent', 0.0)
            item['unit_price_with_bdi'] = price * (1 + bdi)
            item['total_price_with_bdi'] = item['unit_price_with_bdi'] * item['qty']

            # Prepare composition details for Inspector
            if code in self.comp_map:
                comps = []
                for child in self.comp_map[code]:
                    c_price = self.sinapi_prices.get(child['code'], 0.0)
                    comps.append({
                        "code": child['code'],
                        "desc": child['desc'],
                        "unit": child['unit'],
                        "coef": child['coef'],
                        "unit_price": c_price,
                        "total": c_price * child['coef']
                    })
                self.composition_details[code] = comps

    def get_grid_data(self):
        return self.sanitize_for_json(self.po_items)

    def get_composition(self, code):
        return self.sanitize_for_json(self.composition_details.get(code, []))
