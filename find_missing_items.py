import pandas as pd
import sqlite3
import difflib
from pathlib import Path

def normalize_text(text):
    if pd.isna(text): return ""
    return str(text).strip().upper()

def find_matches():
    print("Loading missing items...")
    df = pd.read_csv('tabela_servicos_export.csv')
    missing = df[(df['method'] == 'PO_MANUAL') & (df['type'] == 'ITEM')]
    
    print(f"Total Missing Items: {len(missing)}")
    
    db_path = Path("dados/projeto.sqlite")
    conn = sqlite3.connect(db_path)
    
    # Load candidate tables
    # We'll prioritize tables that look like composition libraries
    
    # 1. Composicoes (General)
    print("Loading 'composicoes' from DB...")
    df_comp = pd.read_sql_query("SELECT fonte, codigo, descricao, unidade FROM composicoes", conn)
    
    # 2. Insumos Unificados (Maybe it's an insumo?)
    print("Loading 'insumos_unificados' from DB...")
    df_insumos = pd.read_sql_query("SELECT fonte, codigo, descricao, unidade, preco_unitario FROM insumos_unificados", conn)
    
    # 3. Composicoes Analiticas (Detailed)
    print("Loading 'composicoes_analiticas_analisadas_unitaria' from DB...")
    # This table seems to link items to compositions, might be useful for description matching
    df_analitica = pd.read_sql_query("SELECT codigo_composicao as codigo, descricao, fonte_composicao as fonte FROM composicoes_analiticas_analisadas_unitaria GROUP BY codigo_composicao", conn)
    
    conn.close()
    
    # Combine sources for searching
    # Add a 'type' col
    df_comp['db_type'] = 'COMPOSICAO'
    df_insumos['db_type'] = 'INSUMO'
    df_analitica['db_type'] = 'COMP_ANALITICA'
    
    # Unified candidate DataFrame
    candidates = pd.concat([
        df_comp[['fonte', 'codigo', 'descricao', 'db_type']],
        df_insumos[['fonte', 'codigo', 'descricao', 'db_type']],
        df_analitica[['fonte', 'codigo', 'descricao', 'db_type']]
    ], ignore_index=True)
    
    # Normalize for matching
    candidates['norm_code'] = candidates['codigo'].apply(normalize_text)
    candidates['norm_desc'] = candidates['descricao'].apply(normalize_text)
    
    suggestions = []
    
    print("Starting matching process (this may take a while)...")
    
    for idx, row in missing.iterrows():
        po_code = normalize_text(row['code'])
        po_desc = normalize_text(row['desc'])
        po_src = normalize_text(row['source'])
        
        # 1. Exact Code Match
        # Filter by code first (fast)
        code_matches = candidates[candidates['norm_code'] == po_code]
        
        for _, match in code_matches.iterrows():
            suggestions.append({
                'po_idx': row['idx'],
                'po_code': row['code'],
                'po_desc': row['desc'],
                'found_code': match['codigo'],
                'found_desc': match['descricao'],
                'found_source': match['fonte'],
                'db_type': match['db_type'],
                'score': 100,
                'match_type': 'EXACT_CODE'
            })
            
        # 2. Description Match (Fuzzy) if no exact code match (or to find alternatives)
        # Only if we haven't found a perfect match or if we want to be thorough
        # Fuzzy matching is slow, so let's limit to items where we didn't find an exact code match from the SAME source
        
        has_exact_source_match = any((m['found_source'] == row['source']) for m in suggestions if m['po_idx'] == row['idx'])
        
        if not has_exact_source_match:
            # Try to match description
            # Use difflib.get_close_matches is too strict/slow for full DB?
            # Let's simple keyword match first? Or just simple contains?
            # For 1133 items x 20k candidates -> 20M checks. Too slow in Python loop.
            # Let's rely on simple token overlap for speed or just skip for now?
            # The user asked to "find compositions... missing".
            # Let's try to match by Source + Code first (Strongest).
            # Then Source + Partial Code?
            # Then Description.
            pass

    # Let's refine the exact code match logic to be more robust
    # Many times codes have formatting differences (e.g. 02.02.130 vs 2.2.130)
    
    # Re-run with normalized code comparison (removing dots/dashes)
    def clean_code(c):
        return str(c).replace('.','').replace('-','').strip().upper()

    candidates['clean_code'] = candidates['norm_code'].apply(clean_code)
    
    count = 0
    for idx, row in missing.iterrows():
        po_clean = clean_code(row['code'])
        if not po_clean: continue
        
        # Look for clean code match
        matches = candidates[candidates['clean_code'] == po_clean]
        
        for _, match in matches.iterrows():
            # Check if we already added this one
            exists = False
            for s in suggestions:
                if s['po_idx'] == row['idx'] and s['found_code'] == match['codigo'] and s['found_source'] == match['fonte']:
                    exists = True
                    break
            
            if not exists:
                score = 90
                if normalize_text(match['fonte']) == normalize_text(row['source']):
                    score = 100
                
                suggestions.append({
                    'po_idx': row['idx'],
                    'po_code': row['code'],
                    'po_desc': row['desc'],
                    'found_code': match['codigo'],
                    'found_desc': match['descricao'],
                    'found_source': match['fonte'],
                    'db_type': match['db_type'],
                    'score': score,
                    'match_type': 'CLEAN_CODE_MATCH'
                })
        
        count += 1
        if count % 100 == 0:
            print(f"Processed {count}/{len(missing)} items...")

    # Export Report
    if suggestions:
        df_sug = pd.DataFrame(suggestions)
        # Sort by PO Item then Score
        df_sug = df_sug.sort_values(['po_idx', 'score'], ascending=[True, False])
        
        # Remove duplicates (keep highest score per item/source pair)
        df_sug = df_sug.drop_duplicates(subset=['po_idx', 'found_code', 'found_source'])
        
        df_sug.to_csv("relatorio_itens_encontrados_db.csv", index=False, encoding='utf-8-sig')
        print(f"Found {len(df_sug)} potential matches. Saved to relatorio_itens_encontrados_db.csv")
        
        # Show top matches
        print("\nTop 20 Matches Found:")
        print(df_sug[['po_idx', 'po_code', 'found_source', 'found_code', 'score', 'db_type']].head(20).to_string())
    else:
        print("No matches found in DB.")

if __name__ == "__main__":
    find_matches()
