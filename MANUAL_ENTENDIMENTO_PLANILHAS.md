# Manual de Entendimento da Hierarquia e Cálculos

## 1. Visão Geral

Este documento explica a origem dos dados, a hierarquia de planilhas e a lógica de prioridade utilizada pelo sistema ("Robô") para gerar os preços finais do orçamento. O objetivo é dar transparência total sobre como os números apresentados no Visualizador são obtidos, permitindo que auditores e engenheiros rastreiem a origem de cada centavo.

## 2. As Fontes de Dados (Hierarquia das Planilhas)

O sistema lê vários arquivos, mas eles tem papéis muito diferentes. Podemos classificá-los em três grupos:

### A. O "Guia" (Onde tudo começa)

* **Arquivo**: `PO.xlsx` (Aba `PO`)
* **Função**: Define a **lista de desejos**.
* **Responsabilidade**: Diz ao sistema QUAIS serviços precisamos orçar. O sistema só vai buscar dados para os códigos que aparecerem aqui.

### B. O "Motor Principal" (SINAPI)

A planilha do SINAPI (`SINAPI_Referência_2024_08.xlsx`) é a fonte primária de inteligência. O sistema lê três abas distintas dela, cada uma com um propósito vital:

1. **Aba `Analítico` (A Receita)**:
    * Não contém preços, apenas **estrutura**.
    * Diz: "Para fazer 1m³ de Concreto (Código A), você precisa de X kg de Cimento (Código B) e Y horas de Pedreiro (Código C)".
    * É daqui que vem a hierarquia visualizada na tela (itens dentro de itens).

2. **Aba `CSD` (Preço Sintético Oficial)**:
    * Contém o preço das composições, calculado pela CAIXA. Elas servem de base para verificar se o calculo foi feito corretamente.
    * O valor que esta na coluna 54 é o preço final que o cliente paga sem o BDI. Ela não deve ser usada como sendo o preço final do orçamento, ela será apenas para verificar se o calculo foi feito corretamente.
    * É lido da **Coluna 54** (na versão atual do script).

3. **Aba `ISD` (Preço de Insumos)**:
    * Contém o preço dos materiais básicos e mão de obra. É daqui que vem  os preços que o sistema usa para calcular os preços finais.
    * Os insumos são a base de tudo, se o preço de  um insumo muda, muda todo o orçamento. Por isso é importante que todas as composições sejam calculadas com os preços dos insumos, e não
    co o preço pronto do serviço. Se mudarmos o preço de um insumo, todas as composições que usam esse insumo terão que ser re calculadas.
    * É lido da **Coluna 30**.

OBS MUITO IMPORTANTE: TODOS OS CALCULOS DEVEM SER FEITOS SEPARADAMENTE POR GRUPO DE INSUMOS. PRECISO SABER O TOTAL DE MÃO DE OBRA, O TOTAL DE EQUIPAMENTO, O TOTAL DE MATERIAIS, ETC.

### C. As Fontes Auxiliares e Específicas

Entram em ação quando o item não é do padrão SINAPI ou requer um preço de mercado específico:

* **SICRO** (`CE 07-2025...xlsx`): Lê a estrutura de composições rodoviárias.
DEve se ter muita atenação com as composições e o método de cálculo do SICRO, pois ele usa uma metodologa diferente do sinapi. As principais diferenças são:
  * Composições por produção: as composições por produção são calculadas da seguinte forma: o produto do preço do insumo pelo coeficiente de utilização do insumo. (ISSO É IGUAL AO SINAPI). So que o sicro
    pequa o resultado dos custos calculados de mão de obra + os custos calcuados de equipamento e divide pela produação da equipe. Esse resultado é somando aos demais ites calculados da composição.
  * O preço dos equipamentos do SICRO é calculado em uma única linha, ou seja, ele tem 2 colunas a mais onde o preço improdutivo é calculado ao lado do preço produtivo. O sinapi por sua vez utiliza um insumo
    para o preço produtivo e outro para o preço improdutivo.

* **CDHU** (`TABELA COMPLETA CDHU.xlsx`): Lê composições do padrão CDHU. Segue o mesmo padrão do SINAPI.
* **Cotações** (`Banco de Dados SQLite`): Preços inseridos manualmente pela equipe de engenharia para itens sem referência oficial (Mercado). Seu preço é lançado diretamente na planilha de orçamento como preço unitário sem bdi.
  * Localização: `dados/projeto.sqlite`
  * Tabela `cotacoes_aba`: Contém o cadastro dos preços de mercado (Código, Descrição, Valor Material, etc).
  * Tabela `validacoes_cot`: Faz o vínculo entre o ITEM da PO e o CÓDIGO da cotação. Exemplo: O item "1.1.1" da PO usa a cotação "MERCADO 01". Isso permite que itens com códigos genéricos na PO recebam preços específicos do banco de dados.
  * O sistema lê automaticamente essas duas tabelas e insere os preços de "MERCADO" na lista de prioridades.

---

## 3. Lógica de Prioridade (Quem decide o número final?)

Esta é a parte mais importante para entender os números. Quando o Visualizador exibe um valor, ele segue uma hierarquia estrita de decisão. Se houver divergência, **quem está no topo da lista ganha**.

### Prioridade 1 (Suprema): O Preço Calculado (Soma dos Filhos)

* **Regra**: Se o sistema conseguiu "abrir" a composição (sabe o que tem dentro) e sabe o preço de cada ingrediente, ele **ignora** qualquer preço fechado que veio do Excel e usa a soma o produto que ele mesmo calculou.

### Prioridade 2: O Preço Oficial da Planilha (Sintético)

* **O que é**: O valor que estava na aba `CSD` do SINAPI ou na coluna de preço do SICRO/CDHU.
* **Quando é usado**: Quando o sistema **não consegue** calcular a soma (por exemplo, mão de obra pura, que não tem "ingredientes", ou uma composição cuja estrutura não foi encontrada no Analítico).
* **Mecanismo de Segurança**: Existe um script de "Patch" (`patch_prices.py`) que roda no final. Se o preço oficial principal estiver vazio/zero, ele varre as colunas vizinhas da planilha original tentando encontrar qualquer número válido para não deixar o orçamento zerado.

### Prioridade 3: O Preço da PO Original

* **Quando é usado**: Se o código não existe no SINAPI, nem no SICRO, nem no CDHU, nem nas cotações.
* **Resultado**: O sistema mantém o valor que o engenheiro digitou manualmente no Excel da PO.

---

## 4. O Processo de "Cálculo Iterativo" (O Segredo)

Muitas vezes, uma composição dentro do SINAPI é feita de outras composições (Composições Auxiliares), que são feitas de outras, criando uma "avó -> mãe -> filha".

Para resolver isso, o robô roda um processo inteligente:

1. Ele carrega todos os preços básicos (cimento, hora-homem).
2. Ele procura composições que só dependem desses básicos e calcula o preço delas.
3. Agora que ele tem esses preços novos, ele procura composições que dependem delas e calcula.
4. Ele repete esse ciclo (até 15 vezes) até que todos os níveis da hierarquia tenham preços calculados.

É por isso que, às vezes, um preço no Visualizador pode diferir centavos do PDF oficial do SINAPI: o nosso sistema está recalculando com precisão matemática baseada nos insumos atuais, propagando o valor exato desde a base até o topo.

## 5. Resumo Visual

O aplicativo Visualizador:

O aplicativo é para ser uma caixa de ferramentas de veficação e de teste de preços pra o engenheiro. O visualizador precisa deixar claro quais foram os serviços que foram calculados corretamente, quais estão dependendo de um insumo ou serviço, listar os itens pendentes. Permitir a fácil vizualização dos preços calculados por tipo de insumo (material, mão de obra, equipamentos, serviços), organizar os itens por ordem crescente e decrescente, fazer pesquisas, filtro, clicar em um insumos e vem em quais composições ele é usado e quanto daquele material será usadod na obra. Em fim, várias outras funcionalidades que serão necessarias para o engenheiro ter uma visão clara do orçamento.
