import pandas as pd
import os

def generate_txt_report():
    csv_path = "relatorio_itens_encontrados_db.csv"
    if not os.path.exists(csv_path):
        print(f"Arquivo {csv_path} não encontrado.")
        return

    df = pd.read_csv(csv_path)
    
    # Sort for better readability
    df = df.sort_values(by=['db_type', 'po_idx'])
    
    output_path = "itens_encontrados_origem.txt"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("RELATÓRIO DE ORIGEM DOS ITENS ENCONTRADOS NO BANCO DE DADOS\n")
        f.write("===========================================================\n\n")
        
        # Summary
        f.write("RESUMO:\n")
        summary = df['db_type'].value_counts()
        for type_name, count in summary.items():
            f.write(f"  - {type_name}: {count} itens\n")
        f.write(f"  - TOTAL: {len(df)} itens\n\n")
        f.write("===========================================================\n\n")
        
        current_type = None
        
        for _, row in df.iterrows():
            db_type = row['db_type']
            
            # Section Header for Table Type
            if db_type != current_type:
                f.write(f"\n>>> ORIGEM: TABELA {db_type} <<<\n")
                f.write("-" * 60 + "\n")
                current_type = db_type
            
            f.write(f"ITEM PO: {row['po_idx']} | CÓD: {row['po_code']}\n")
            f.write(f"  -> Encontrado na Fonte: {row['found_source']} (Código BD: {row['found_code']})\n")
            f.write(f"  -> Descrição no Banco:  {row['found_desc']}\n")
            f.write(f"  -> Tipo de Match:       {row['match_type']} (Score: {row['score']})\n")
            f.write("\n")

    print(f"Relatório TXT gerado em: {output_path}")

if __name__ == "__main__":
    generate_txt_report()
