COMO RODAR O SISTEMA DE ORÇAMENTO
=================================

Este sistema permite calcular orçamentos de obras públicas utilizando bases SINAPI, SICRO, CDHU e Cotações de Mercado, com resolução automática de dependências entre composições.

PASSO A PASSO
-------------

1. Instalação (Primeira vez apenas):
   Certifique-se de ter o Python instalado.
   Instale as bibliotecas necessárias rodando no terminal:
   
   pip install -r requirements.txt

2. Executando o Visualizador:
   Para abrir a interface gráfica, ver os itens e recalcular o orçamento, rode:
   
   python app_visualizador.py

3. Funcionalidades do Visualizador:
   - Botão "Recalcular Completo": Lê todas as planilhas (SINAPI, PO, SICRO, etc), refaz os cálculos e gera os dados atualizados.
   - Lista da Esquerda: Mostra os itens da sua Planilha Orçamentária (PO).
   - Lista da Direita: Mostra a composição detalhada do item selecionado (Insumos, Mão de Obra, etc).
   - Barra de Pesquisa: Filtre itens por código ou descrição.

ARQUIVOS DO SISTEMA
-------------------
- app_visualizador.py: Interface Gráfica (O PROGRAMA PRINCIPAL).
- generate_final_export_v3.py: Motor de cálculo (rodado automaticamente pelo visualizador).
- PO.xlsx: Sua planilha de orçamento (INPUT).
- SINAPI_..., CDHU..., CE...: Planilhas de referência de preços.
- dados/projeto.sqlite: Banco de dados de cotações manuais.
- tabela_servicos_export.csv e tabela_insumos_export.csv: Arquivos gerados pelo cálculo (OUTPUT).

SOLUÇÃO DE PROBLEMAS
--------------------
- Se o visualizador não abrir, verifique se instalou o tkinter (geralmente já vem com o Python).
- Se os preços estiverem zerados, clique em "Recalcular Completo" e aguarde o fim do processo (pode levar alguns minutos).
