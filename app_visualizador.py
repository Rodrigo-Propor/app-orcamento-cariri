import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import os
import threading
import sys
from io import StringIO
import importlib.util

# Tenta importar o script de geração como módulo
# Isso permite rodar a função diretamente se preferir, ou usar subprocess.
# Vamos usar execução direta da função para simplificar a integração, 
# mas redirecionando stdout para capturar logs.

def get_script_module(script_path):
    spec = importlib.util.spec_from_file_location("generate_final_export_v3", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_final_export_v3"] = module
    spec.loader.exec_module(module)
    return module

class RedirectText:
    def __init__(self, text_ctrl):
        self.output = text_ctrl

    def write(self, string):
        self.output.insert(tk.END, string)
        self.output.see(tk.END)

    def flush(self):
        pass

class OrcamentoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Visualizador de Orçamento de Obras Públicas")
        self.root.geometry("1200x800")

        # Variáveis de dados
        self.df_servicos = None
        self.df_insumos = None

        # --- Layout Principal ---
        # Top Bar (Botoes)
        frame_top = ttk.Frame(root, padding=10)
        frame_top.pack(fill=tk.X)

        btn_recalc = ttk.Button(frame_top, text="Recalcular Completo (Gerar CSVs)", command=self.start_recalc)
        btn_recalc.pack(side=tk.LEFT, padx=5)

        btn_load = ttk.Button(frame_top, text="Carregar Dados Existentes", command=self.load_data)
        btn_load.pack(side=tk.LEFT, padx=5)

        self.lbl_status = ttk.Label(frame_top, text="Aguardando ação...", foreground="blue")
        self.lbl_status.pack(side=tk.LEFT, padx=20)

        # Filtros Avançados (Acima da Treeview)
        # Vamos criar um frame para conter os filtros específicos
        
        # PanedWindow (Split Vertical)
        paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # --- Lado Esquerdo: Lista de Serviços (PO) ---
        frame_left = ttk.Labelframe(paned, text="Itens da Planilha (PO)", padding=5)
        paned.add(frame_left, weight=2)

        # Frame de filtros
        frame_filters = ttk.Frame(frame_left)
        frame_filters.pack(fill=tk.X, pady=(0, 5))
        
        self.filters = {}
        
        # Filtro Código
        ttk.Label(frame_filters, text="Cód:").pack(side=tk.LEFT)
        self.filters['code'] = ttk.Entry(frame_filters, width=10)
        self.filters['code'].pack(side=tk.LEFT, padx=(0, 10))
        self.filters['code'].bind("<KeyRelease>", self.apply_advanced_filter)

        # Filtro Descrição
        ttk.Label(frame_filters, text="Desc:").pack(side=tk.LEFT)
        self.filters['desc'] = ttk.Entry(frame_filters)
        self.filters['desc'].pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.filters['desc'].bind("<KeyRelease>", self.apply_advanced_filter)
        
        # Filtro Fonte
        ttk.Label(frame_filters, text="Fonte:").pack(side=tk.LEFT)
        self.filters['source'] = ttk.Entry(frame_filters, width=10)
        self.filters['source'].pack(side=tk.LEFT)
        self.filters['source'].bind("<KeyRelease>", self.apply_advanced_filter)

        cols_po = ("idx", "source", "code", "desc", "unit", "qty", "price_unit", "price_total")
        self.tree_po = ttk.Treeview(frame_left, columns=cols_po, show="headings", selectmode="browse")
        
        # Configurar colunas PO
        self.tree_po.heading("idx", text="Item")
        self.tree_po.column("idx", width=50, anchor="center")
        self.tree_po.heading("source", text="Fonte")
        self.tree_po.column("source", width=60, anchor="center")
        self.tree_po.heading("code", text="Código")
        self.tree_po.column("code", width=80, anchor="center")
        self.tree_po.heading("desc", text="Descrição")
        self.tree_po.column("desc", width=300)
        self.tree_po.heading("unit", text="Unid")
        self.tree_po.column("unit", width=50, anchor="center")
        self.tree_po.heading("qty", text="Qtd")
        self.tree_po.column("qty", width=60, anchor="e")
        self.tree_po.heading("price_unit", text="Preço Unit.")
        self.tree_po.column("price_unit", width=80, anchor="e")
        self.tree_po.heading("price_total", text="Total")
        self.tree_po.column("price_total", width=80, anchor="e")

        # Configurar Cores (Tags)
        self.tree_po.tag_configure('error_price', foreground='red') # Preço Zero
        self.tree_po.tag_configure('warning_source', foreground='#e67e22') # Fonte desconhecida/estranha
        self.tree_po.tag_configure('ok', foreground='black')

        scroll_po = ttk.Scrollbar(frame_left, orient="vertical", command=self.tree_po.yview)
        self.tree_po.configure(yscrollcommand=scroll_po.set)
        
        self.tree_po.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_po.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Legenda de Cores ---
        frame_legend = ttk.Frame(frame_left)
        frame_legend.pack(fill=tk.X, pady=5)
        
        ttk.Label(frame_legend, text="Legenda:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=5)
        
        # Helper para criar itens da legenda
        def add_legend_item(parent, text, color, is_bg=False):
            lbl = tk.Label(parent, text=text, font=('Arial', 8))
            if is_bg:
                lbl.config(bg=color)
            else:
                lbl.config(fg=color)
            lbl.pack(side=tk.LEFT, padx=5)
            
        add_legend_item(frame_legend, "■ Grupo/Título", "#f0f0f0", is_bg=True)
        add_legend_item(frame_legend, "■ Calculado (OK)", "black")
        add_legend_item(frame_legend, "■ Sem Composição (Manual/Direto)", "blue")
        add_legend_item(frame_legend, "■ Cálculo Parcial", "#e67e22")
        add_legend_item(frame_legend, "■ Erro/Zerado", "red")

        self.tree_po.bind("<<TreeviewSelect>>", self.on_item_select)

        # --- Lado Direito: Detalhes da Composição ---
        frame_right = ttk.Labelframe(paned, text="Detalhes da Composição (Insumos/Filhos)", padding=5)
        paned.add(frame_right, weight=3)

        # Área de info do item selecionado
        self.lbl_item_detail = ttk.Label(frame_right, text="Selecione um item para ver a composição.", wraplength=400)
        self.lbl_item_detail.pack(fill=tk.X, pady=5)

        cols_ins = ("type", "code", "desc", "unit", "coef", "price", "total")
        self.tree_ins = ttk.Treeview(frame_right, columns=cols_ins, show="headings")
        
        # Configurar colunas Insumos
        self.tree_ins.heading("type", text="Tipo/Fonte")
        self.tree_ins.column("type", width=80)
        self.tree_ins.heading("code", text="Código")
        self.tree_ins.column("code", width=80, anchor="center")
        self.tree_ins.heading("desc", text="Descrição")
        self.tree_ins.column("desc", width=250)
        self.tree_ins.heading("unit", text="Unid")
        self.tree_ins.column("unit", width=50, anchor="center")
        self.tree_ins.heading("coef", text="Coef")
        self.tree_ins.column("coef", width=60, anchor="e")
        self.tree_ins.heading("price", text="Preço Unit")
        self.tree_ins.column("price", width=80, anchor="e")
        self.tree_ins.heading("total", text="Subtotal")
        self.tree_ins.column("total", width=80, anchor="e")

        scroll_ins = ttk.Scrollbar(frame_right, orient="vertical", command=self.tree_ins.yview)
        self.tree_ins.configure(yscrollcommand=scroll_ins.set)

        self.tree_ins.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_ins.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Log Output Area (Bottom) ---
        frame_log = ttk.Labelframe(root, text="Logs de Processamento", padding=5)
        frame_log.pack(fill=tk.X, padx=10, pady=5)
        
        self.txt_log = tk.Text(frame_log, height=6)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        # Tentar carregar dados ao iniciar se existirem
        self.load_data(silent=True)

    def log(self, msg):
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)

    def start_recalc(self):
        self.lbl_status.config(text="Calculando... Verifique os logs abaixo.")
        self.btn_recalc_state(tk.DISABLED)
        
        # Thread para não travar a GUI
        t = threading.Thread(target=self.run_calculation_script)
        t.start()

    def btn_recalc_state(self, state):
        # Helper para habilitar/desabilitar botões durante processamento
        pass 

    def run_calculation_script(self):
        # Redirecionar stdout para a caixa de texto
        old_stdout = sys.stdout
        sys.stdout = RedirectText(self.txt_log)
        
        try:
            print("--- INICIANDO CÁLCULO ---")
            # Importa dinamicamente o script existente
            if os.path.exists("generate_final_export_v3.py"):
                mod = get_script_module("generate_final_export_v3.py")
                mod.run_final_export_v3()
                print("--- CÁLCULO CONCLUÍDO COM SUCESSO ---")
                
                # Agenda o recarregamento dos dados na thread principal
                self.root.after(100, lambda: self.finish_recalc(success=True))
            else:
                print("ERRO: Arquivo 'generate_final_export_v3.py' não encontrado.")
                self.root.after(100, lambda: self.finish_recalc(success=False))
                
        except Exception as e:
            print(f"ERRO CRÍTICO: {e}")
            import traceback
            traceback.print_exc()
            self.root.after(100, lambda: self.finish_recalc(success=False))
        finally:
            sys.stdout = old_stdout

    def finish_recalc(self, success):
        self.btn_recalc_state(tk.NORMAL)
        if success:
            self.lbl_status.config(text="Cálculo finalizado. Carregando dados...")
            self.load_data()
        else:
            self.lbl_status.config(text="Erro no cálculo. Verifique os logs.")
            messagebox.showerror("Erro", "Ocorreu um erro durante o cálculo. Verifique a área de logs.")

    def load_data(self, silent=False):
        f_serv = "tabela_servicos_export.csv"
        f_ins = "tabela_insumos_export.csv"

        if not os.path.exists(f_serv) or not os.path.exists(f_ins):
            if not silent:
                messagebox.showwarning("Aviso", "Arquivos de dados não encontrados. Clique em 'Recalcular Completo'.")
            return

        try:
            self.df_servicos = pd.read_csv(f_serv)
            self.df_insumos = pd.read_csv(f_ins)
            
            # Limpar e popular Treeview PO
            self.populate_po_tree(self.df_servicos)
            
            self.lbl_status.config(text="Dados carregados com sucesso.")
            if not silent:
                messagebox.showinfo("Sucesso", "Dados carregados!")
                
        except Exception as e:
            self.lbl_status.config(text=f"Erro ao ler dados: {e}")
            if not silent:
                messagebox.showerror("Erro de Leitura", str(e))

    def populate_po_tree(self, df):
        for i in self.tree_po.get_children():
            self.tree_po.delete(i)
            
        if df is None: return

        # Configurar tags de cores
        self.tree_po.tag_configure('header', font=('Arial', 10, 'bold'), background='#f0f0f0')
        self.tree_po.tag_configure('partial', foreground='#e67e22') # Laranja
        self.tree_po.tag_configure('no_comp', foreground='blue') # Azul
        self.tree_po.tag_configure('error', foreground='red')
        self.tree_po.tag_configure('ok', foreground='black')

        # Map idx -> tree_item_id
        self.idx_to_id = {}
        
        # Sort by idx logic
        try:
            # Create temporary sort key
            df = df.copy()
            df['sort_key'] = df['idx'].apply(lambda x: [int(part) for part in str(x).split('.') if part.isdigit()] if pd.notnull(x) else [])
            df = df.sort_values('sort_key')
        except:
            pass 

        for _, row in df.iterrows():
            idx = str(row['idx']).strip()
            
            # Find parent
            parts = idx.split('.')
            parent_id = ""
            # Try to find parent by progressively removing last segment
            # e.g. 1.1.1 -> try 1.1 -> try 1
            if len(parts) > 1:
                parent_idx = ".".join(parts[:-1])
                if parent_idx in self.idx_to_id:
                    parent_id = self.idx_to_id[parent_idx]
            
            # Prepare values
            code = str(row['code']) if pd.notnull(row['code']) else ""
            desc = str(row['desc']) if pd.notnull(row['desc']) else ""
            unit = str(row['unit']) if pd.notnull(row['unit']) else ""
            status = str(row['status']) if pd.notnull(row['status']) else ""
            
            # Qty
            qty_val = 0.0
            if 'qty' in row and pd.notnull(row['qty']):
                try: qty_val = float(row['qty'])
                except: pass
            
            # Price
            price_val = 0.0
            if 'final_price' in row and pd.notnull(row['final_price']):
                price_val = float(row['final_price'])
            
            # If item is ITEM type, use final_price. If HEADER, we will sum later (initially 0 or -)
            p_unit_str = f"R$ {price_val:,.2f}" if status != 'HEADER' else ""
            
            # Calculate Total for Items
            total_val = 0.0
            p_total_str = ""
            if status != 'HEADER':
                total_val = price_val * qty_val
                p_total_str = f"R$ {total_val:,.2f}"

            # Tags
            tags = []
            if status == 'HEADER': tags.append('header')
            elif status == 'PARTIAL': tags.append('partial')
            elif status == 'NO_COMP': tags.append('no_comp')
            elif status == 'ERROR' or price_val == 0: tags.append('error')
            else: tags.append('ok')
            
            # Insert (Open by default to show structure)
            vals = (idx, row['source'], code, desc, unit, f"{qty_val:,.2f}", p_unit_str, p_total_str)
            iid = self.tree_po.insert(parent_id, tk.END, values=vals, tags=tuple(tags), open=True)
            self.idx_to_id[idx] = iid

        # Calculate Group Totals
        self.calculate_group_totals()

    def calculate_group_totals(self):
        # Recursive calculation
        def calc_node(item_id):
            children = self.tree_po.get_children(item_id)
            vals = list(self.tree_po.item(item_id)['values'])
            
            # If it's a leaf/item, return its TOTAL price (from col 7)
            # Col 7 is 'price_total'
            # Note: treeview values are strings if we inserted strings.
            # Index: 0=idx, 1=src, 2=code, 3=desc, 4=unit, 5=qty, 6=price_unit, 7=price_total
            
            current_total = 0.0
            
            if not children:
                # Leaf Item
                try:
                    t_str = vals[7] 
                    if t_str:
                        current_total = float(t_str.replace('R$ ','').replace('.','').replace(',','.'))
                except:
                    pass
                return current_total

            # If it has children, it's a group. Sum children.
            total = 0.0
            for child in children:
                total += calc_node(child)
            
            # Update this node's Total column (Col 7)
            vals[7] = f"R$ {total:,.2f}"
            self.tree_po.item(item_id, values=vals)
            return total

        for child in self.tree_po.get_children(""):
            calc_node(child)


    def apply_advanced_filter(self, event):
        if self.df_servicos is None: return
        
        f_code = self.filters['code'].get().lower()
        f_desc = self.filters['desc'].get().lower()
        f_src = self.filters['source'].get().lower()
        
        # Inicia com todos
        mask = pd.Series([True] * len(self.df_servicos))
        
        if f_code:
            mask = mask & self.df_servicos['code'].astype(str).str.lower().str.contains(f_code)
        if f_desc:
            mask = mask & self.df_servicos['desc'].astype(str).lower().str.contains(f_desc)
        if f_src:
            mask = mask & self.df_servicos['source'].astype(str).str.lower().str.contains(f_src)
            
        filtered_df = self.df_servicos[mask]
        self.populate_po_tree(filtered_df)

    def on_item_select(self, event):
        selected = self.tree_po.selection()
        if not selected: return
        
        item_vals = self.tree_po.item(selected[0])['values']
        code = str(item_vals[2]) # code index
        desc = item_vals[3]
        
        self.lbl_item_detail.config(text=f"Composição do Item: {code} - {desc}")
        
        # Limpar tree insumos
        for i in self.tree_ins.get_children():
            self.tree_ins.delete(i)
            
        if self.df_insumos is None: return
        
        # Filtrar insumos
        insumos = self.df_insumos[self.df_insumos['parent_code'].astype(str) == code]
        
        total_comp = 0.0
        
        for _, row in insumos.iterrows():
            coef = float(row['coef']) if pd.notnull(row['coef']) else 0.0
            price = float(row['price']) if pd.notnull(row['price']) else 0.0
            subtotal = coef * price
            total_comp += subtotal
            
            vals = (
                row['src'],
                row['res_code'],
                row['res_desc'],
                row['res_unit'],
                f"{coef:.4f}",
                f"R$ {price:,.2f}",
                f"R$ {subtotal:,.2f}"
            )
            self.tree_ins.insert("", tk.END, values=vals)
            
        # Adicionar linha de total
        self.tree_ins.insert("", tk.END, values=("TOTAL", "", "", "", "", "", f"R$ {total_comp:,.2f}"), tags=('total',))
        self.tree_ins.tag_configure('total', font=('Arial', 10, 'bold'), background='#e6e6e6')

if __name__ == "__main__":
    root = tk.Tk()
    app = OrcamentoApp(root)
    root.mainloop()
