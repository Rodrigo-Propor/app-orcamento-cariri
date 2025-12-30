import pandas as pd
import numpy as np
import sqlite3
from pathlib import Path

def normalize_val(v):
    if pd.isna(v): return None
    s = str(v).strip().upper()
    if s.endswith('.0'): s = s[:-2]
    return s

def run_final_export_v3():
    print("Loading PO items...")
    # PO.xlsx: Data starts around row 12.
    po_df = pd.read_excel("PO.xlsx", sheet_name="PO", skiprows=12, header=None)
    po_items = []
    po_prices = {} # code -> price
    required_codes = set()
    
    for _, row in po_df.iterrows():
        po_idx = str(row[0]).strip()
        # Debug
        if po_idx.startswith('1.1'):
             print(f"DEBUG ROW: {po_idx} - {row[1]} - {row[2]}")
             pass

        if po_idx == 'nan' or po_idx == 'ITEM': continue
        
        source = normalize_val(row[1])
        code = normalize_val(row[2])
        desc = row[3]
        unit = row[4]
        try:
            qty = float(row[5]) if not pd.isna(row[5]) else 0.0
        except:
            qty = 0.0
        
        item_type = "ITEM"
        
        # Header Detection
        if not source:
            # If source is empty, it's likely a header.
            # Title might be in Col 2 (Code) or Col 3 (Desc).
            # Based on inspection: Col 2 has the text.
            item_type = "HEADER"
            if code and (pd.isna(desc) or str(desc).strip() == ""):
                desc = row[2] # Use Col 2 as desc
                code = "" # Clear code
            elif not code and not pd.isna(desc):
                 # Normal header in desc col?
                 pass
        
        # Capture manual price
        try:
            p_val = row[8]
            if isinstance(p_val, str): p_val = p_val.replace(',', '.')
            p_float = float(p_val)
        except:
            p_float = 0.0

        # We include everything now, distinguishing via item_type
        po_items.append({
            "idx": po_idx, 
            "source": source, 
            "code": code, 
            "desc": desc, 
            "unit": unit,
            "qty": qty,
            "manual_price": p_float,
            "type": item_type
        })
        
        if code and item_type == "ITEM":
            po_prices[code] = p_float
            required_codes.add(code)

    # DB Cotações
    db_path = Path("dados/projeto.sqlite")
    conn = sqlite3.connect(db_path)
    db_mapped = pd.read_sql_query("SELECT po_item, codigo as m_code FROM validacoes_cot", conn)
    db_prices = pd.read_sql_query("SELECT codigo, descricao, valor_material FROM cotacoes_aba", conn)
    db_map = dict(zip(db_mapped['po_item'], db_mapped['m_code']))
    db_price = db_prices.set_index('codigo').to_dict('index')
    conn.close()

    final_insumos = []
    expanded_items = set() # Track which PO items got components

    # --- 1. SINAPI ---
    f_sinapi = "SINAPI_Referência_2024_08.xlsx"
    sinapi_prices = {}
    if Path(f_sinapi).exists():
        print(f"Loading SINAPI Prices from {f_sinapi} (ISD & CSD)...")
        
        def load_prices(sheet_name, price_col_idx):
            try:
                # Skip 10 rows (Headers are in first 10 rows, data starts row 10)
                df_x = pd.read_excel(f_sinapi, sheet_name=sheet_name, header=None, skiprows=10)
                loaded_count = 0
                for _, row in df_x.iterrows():
                    # Code is always Col 1
                    raw_c = row[1]
                    if pd.isna(raw_c): continue
                    
                    c_x = str(raw_c).strip()
                    if c_x.endswith('.0'): c_x = c_x[:-2]
                    
                    if c_x:
                        # Price column varies by sheet
                        # PATCH LOGIC: If target column is empty/zero, scan row for first float > 0
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
                        
                        # Fallback: Scan row if not found or zero (and we suspect it might be elsewhere)
                        # We scan from col 4 onwards to avoid code/desc
                        if not found or val_float == 0:
                            for idx in range(4, len(row)):
                                if idx == price_col_idx: continue
                                try:
                                    v = row[idx]
                                    if isinstance(v, (int, float)) and not pd.isna(v) and v > 0:
                                        val_float = float(v)
                                        found = True
                                        # print(f"PATCH: Found price for {c_x} in col {idx}: {val_float}")
                                        break
                                except:
                                    pass

                        if found:
                            sinapi_prices[c_x] = val_float
                            loaded_count += 1
                            
                            # Debug specific codes
                            if c_x in ["34547", "88316"]:
                                print(f"DEBUG LOAD {sheet_name}: Found {c_x} -> {val_float}")
                                
                print(f"Loaded {loaded_count} items from {sheet_name}")
            except Exception as e:
                print(f"Error loading {sheet_name}: {e}")

        # Code=Col 1 (Index 1). Price (SP)=Col 30 (ISD) and Col 54 (CSD).
        load_prices("ISD", 30)
        load_prices("CSD", 54)
        
        print(f"Total prices loaded: {len(sinapi_prices)}")

        print(f"Parsing {f_sinapi} (Analítico)...")
        # Read Analítico (Structural)
        df = pd.read_excel(f_sinapi, sheet_name="Analítico", header=None, skiprows=5)

        # --- Iterative Calculation of Composition Prices ---
        print("Building composition dependency map for price calculation...")
        comp_map = {} # parent -> list of {code, coef}
        current_comp_calc = None

        # Pass 1: Build dependency map
        for _, row in df.iterrows():
            c_comp = normalize_val(row[1])
            if not c_comp: continue
            
            tipo = str(row[2]).strip().upper()
            if tipo in ["NAN", "", "NONE"] or pd.isna(row[2]):
                current_comp_calc = c_comp
                if current_comp_calc not in comp_map:
                    comp_map[current_comp_calc] = []
            elif current_comp_calc:
                # Component
                r_code = normalize_val(row[3])
                if not r_code: continue
                
                try:
                    coef = float(row[6]) if not pd.isna(row[6]) else 0.0
                except:
                    coef = 0.0
                
                comp_map[current_comp_calc].append({'code': r_code, 'coef': coef})
        
        print(f"Mapped {len(comp_map)} compositions. Starting iterative calculation...")
        
        # Pass 2: Iterative Calculation
        for i in range(15): # Max 15 passes
            added_count = 0
            for parent, children in comp_map.items():
                if parent in sinapi_prices:
                    continue # Already calculated or loaded
                
                total = 0.0
                ready = True
                
                for child in children:
                    c_code = child['code']
                    c_coef = child['coef']
                    
                    if c_code in sinapi_prices:
                        total += sinapi_prices[c_code] * c_coef
                    else:
                        if c_code in comp_map:
                            ready = False
                            break
                        else:
                            # Missing input, assume 0
                            pass
                
                if ready:
                    sinapi_prices[parent] = total
                    added_count += 1
            
            print(f"Pass {i+1}: Calculated {added_count} new composition prices.")
            if added_count == 0:
                break
        
        print(f"Total prices after calculation: {len(sinapi_prices)}")

        # --- Expand required_codes to include all sub-compositions (Transitive Closure) ---
        print("Expanding export list to include sub-compositions...")
        queue = list(required_codes)
        visited_exp = set(required_codes)
        while queue:
            curr = queue.pop(0)
            if curr in comp_map:
                for child in comp_map[curr]:
                    c_code = child['code']
                    if c_code not in visited_exp:
                        visited_exp.add(c_code)
                        queue.append(c_code)
        
        required_codes = visited_exp
        print(f"Total items to export details for: {len(required_codes)}")

        # --- Export Pass ---
        current_comp = None
        for _, row in df.iterrows():
            c_comp = normalize_val(row[1])
            if not c_comp: continue
            tipo = str(row[2]).strip().upper()
            
            # Identify Composition Header
            if tipo in ["NAN", "", "NONE"] or pd.isna(row[2]):
                current_comp = c_comp
            elif current_comp in required_codes:
                # It's an item inside the composition
                r_code = normalize_val(row[3])
                if not r_code: continue
                
                price = sinapi_prices.get(r_code, 0.0)
                
                final_insumos.append({
                    "parent_code": current_comp, "src": "SINAPI", "res_code": r_code,
                    "res_desc": row[4], "res_unit": row[5], "coef": row[6], "price": price
                })
                expanded_items.add(current_comp)

    # --- 2. CDHU ---
    f_cdhu = "TABELA COMPLETA CDHU.xlsx"
    if Path(f_cdhu).exists():
        print(f"Parsing {f_cdhu}...")
        df = pd.read_excel(f_cdhu, sheet_name="Composição", header=None)
        current_comp = None
        for _, row in df.iterrows():
            c1 = normalize_val(row[0])
            if not c1: continue
            if pd.isna(row[3]): current_comp = c1
            elif current_comp in required_codes:
                price = row[4] if len(row) > 4 else 0
                final_insumos.append({
                    "parent_code": current_comp, "src": "CDHU", "res_code": c1,
                    "res_desc": row[1], "res_unit": row[2], "coef": row[3], "price": price
                })
                expanded_items.add(current_comp)

    # --- 3. SICRO (THE BIG ONE) ---
    f_sicro = "CE 07-2025 Relatório Analítico de Composições de Custos.xlsx"
    if Path(f_sicro).exists():
        print(f"Parsing {f_sicro} (200k rows)...")
        df = pd.read_excel(f_sicro, sheet_name=0, header=None)
        current_comp = None
        for _, row in df.iterrows():
            col0 = normalize_val(row[0])
            if col0 in required_codes and not pd.isna(row[1]) and pd.isna(row[3]):
                current_comp = col0
            elif current_comp and not pd.isna(row[1]) and not pd.isna(row[3]):
                price = row[5] if len(row) > 5 else 0
                final_insumos.append({
                    "parent_code": current_comp, "src": "SICRO", "res_code": col0,
                    "res_desc": row[1], "res_unit": row[4] if not pd.isna(row[4]) else row[3],
                    "coef": row[2] if not pd.isna(row[2]) else row[3],
                    "price": price
                })
                expanded_items.add(current_comp)
            if col0 and col0 != current_comp and col0 not in required_codes and not pd.isna(row[1]) and pd.isna(row[3]):
                current_comp = None

    # --- 4. COTAÇÕES / DB ---
    print("Adding Database Cotacoes...")
    for item in po_items:
        if item['idx'] in db_map:
            m_code = db_map[item['idx']]
            if m_code in db_price:
                p = db_price[m_code]
                final_insumos.append({
                    "parent_code": item['code'], "src": "MERCADO", "res_code": m_code,
                    "res_desc": p['descricao'], "res_unit": "UN", "coef": 1, "price": p['valor_material']
                })
                expanded_items.add(item['code'])

    # --- 5. FALLBACK / SELF-REFERENCE & STATUS CALCULATION ---
    print("Checking for missing items and applying Fallback/PO Price...")
    
    # Pre-scan for partial compositions (any child with price 0)
    partial_codes = set()
    for ins in final_insumos:
        if ins['price'] == 0 and ins['coef'] != 0:
            partial_codes.add(ins['parent_code'])

    final_po_export = []
    
    for item in po_items:
        if item['type'] == 'HEADER':
            item['status'] = 'HEADER'
            item['final_price'] = 0.0 # Will be calc by visualizer
            item['method'] = 'SUM_CHILDREN'
            final_po_export.append(item)
            continue
            
        code = item['code']
        price = 0.0
        method = 'UNKNOWN'
        status = 'ERROR'
        
        # 1. Check if it was expanded (Composition)
        if code in expanded_items:
            # It is a composition
            price = sinapi_prices.get(code, 0.0)
            if price == 0 and item['manual_price'] > 0:
                # If calculated is 0 but we have manual, use manual? 
                # Manual says: Priority 1 is Calculated. Priority 3 is PO.
                # If Calculated is 0, it failed? Or is it really 0?
                # Let's assume if 0, we fall back.
                pass
            
            if price > 0:
                method = 'CALCULATED'
                status = 'OK'
                if code in partial_codes:
                    status = 'PARTIAL'
            else:
                method = 'CALC_ZERO'
        
        # 2. If price is still 0/low, check Direct SINAPI (Leaf)
        if price == 0:
            price = sinapi_prices.get(code, 0.0)
            if price > 0:
                method = 'SINAPI_DIRECT'
                status = 'NO_COMP' # No composition expanded, but price exists
        
        # 3. Fallback to PO Manual
        if price == 0:
            price = po_prices.get(code, 0.0)
            if price > 0:
                method = 'PO_MANUAL'
                status = 'NO_COMP'
                
                # Add a dummy insumo line to show it's manual
                final_insumos.append({
                    "parent_code": code, "src": "PO_MANUAL", "res_code": code,
                    "res_desc": item['desc'], "res_unit": item['unit'], "coef": 1.0, "price": price
                })

        item['final_price'] = price
        item['method'] = method
        item['status'] = status
        final_po_export.append(item)

    # Export
    pd.DataFrame(final_po_export).to_csv("tabela_servicos_export.csv", index=False, encoding="utf-8-sig")
    final_df = pd.DataFrame(final_insumos)
    final_df.to_csv("tabela_insumos_export.csv", index=False, encoding="utf-8-sig")
    print(f"Export V3 FINISHED. Total Insumos: {len(final_insumos)}")

if __name__ == "__main__":
    run_final_export_v3()
