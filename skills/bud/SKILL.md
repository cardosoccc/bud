---
name: bud
description: gerencia orcamentos pessoais via ferramenta cli bud. lida com projetos, contas, transacoes, orcamentos, previsoes, recorrencias e relatorios de status. use quando o usuario pedir para registrar gastos, verificar saldos, planejar orcamentos, criar previsoes, gerenciar contas recorrentes ou ver relatorios financeiros. frases gatilho incluem "adicionar gasto", "registrar transacao", "status do orcamento", "criar previsao", "orcamento mensal", "conta recorrente".
---

# bud

bud e uma ferramenta cli de gestao de orcamento pessoal. todos os dados ficam em um banco sqlite local em `~/.bud/bud.db`. comandos sao executados via `bud` (ou `uv run bud` em desenvolvimento).

## regras fundamentais

- todos os valores monetarios usam convencao de sinal: **positivo = receita/entrada**, **negativo = despesa/saida**
- toda operacao e vinculada a um projeto. garanta que um projeto padrao exista (`bud p s <nome>`) antes de executar comandos.
- defina o mes ativo com `bud g s month yyyy-mm` para que comandos com escopo mensal saibam qual periodo usar.
- sempre inicialize o banco primeiro: `bud db init`
- quando um nome de categoria nao existe, bud oferece cria-la na hora. confirme com `y`.

## sistema de aliases

bud usa aliases de uma letra para agilidade. sempre prefira aliases aos nomes completos.

### grupos de comandos

| alias | comando |
|-------|---------|
| `t` | transaction (transacao) |
| `b` | budget (orcamento) |
| `c` | category (categoria) |
| `f` | forecast (previsao) |
| `p` | project (projeto) |
| `r` | recurrence (recorrencia) |
| `a` | account (conta) |
| `s` | status (relatorio) |
| `g` | config (configuracao) |

### subcomandos

| alias | subcomando |
|-------|------------|
| `c` | create (criar) |
| `e` | edit (editar) |
| `d` | delete (excluir) |
| `l` | list (listar) |
| `s` | show (mostrar) / set-default (definir padrao) |

### atalhos de listagem

comandos de duas letras listam um recurso diretamente: `tt` (transacoes), `ff` (previsoes), `bb` (orcamentos), `pp` (projetos), `aa` (contas), `cc` (categorias), `rr` (recorrencias), `gg` (configs).

### aliases de opcoes comuns

`-v` valor, `-d` descricao, `-p` projeto, `-c` categoria, `-t` tags (ou data em transacoes), `-a` conta (ou --all em recorrencias), `-s` mostrar-id, `-n` nome, `-y` sim (pular confirmacao), `-r` recorrente, `-e` fim-recorrencia, `-i` parcelas.

## fluxo de configuracao

execute estes comandos para configurar um novo ambiente bud:

```bash
bud db init
bud p c -n "pessoal"
bud p s pessoal
bud g s month 2025-03
bud a c -n "banco" -t debit
bud a c -n "cartao" -t credit
```

## registrando transacoes

```bash
# despesa da conta bancaria
bud t c -v -50 -d "mercado" -a banco -c alimentacao

# receita na conta bancaria
bud t c -v 3000 -d "salario" -a banco -c salario

# compra no cartao de credito
bud t c -v -100 -d "restaurante" -a cartao -c alimentacao

# listar transacoes do mes atual
bud tt

# listar transacoes de um mes especifico
bud tt 2025-02

# editar transacao #3 da lista do mes atual
bud t e 3 -v -45 -d "mercado (corrigido)"

# excluir transacao #2 (sem confirmacao)
bud t d 2 -y
```

## orcamentos e previsoes

```bash
# criar orcamento para um mes (preenche recorrencias automaticamente)
bud b c 2025-03

# criar previsao simples (orcamento criado automaticamente se nao existir)
bud f c -v -200 -d "mercado" -c alimentacao

# criar previsao em um orcamento especifico
bud f c 2025-04 -v -200 -d "mercado" -c alimentacao

# criar previsao recorrente aberta (repete todo mes)
bud f c -v -1500 -d "aluguel" -c moradia -r

# criar previsao recorrente com data final
bud f c -v -100 -d "academia" -c saude -r -e 2025-12

# criar previsao parcelada (ex: 10 parcelas mensais)
bud f c -v -300 -d "maquina de lavar" -c eletrodomesticos -i 10

# registrar compra ja na 5a parcela (cria parcelas 5-10)
bud f c -v -300 -d "maquina de lavar" -c eletrodomesticos -i 10 --current-installment 5

# listar previsoes do mes atual
bud ff

# editar previsao #2 do mes atual
bud f e 2 -v -250

# transformar previsao nao-recorrente em recorrencia
bud f e 3 -r
```

## gerenciando recorrencias

recorrencias sao os modelos por tras de previsoes recorrentes.

```bash
# listar recorrencias ativas no mes atual
bud rr

# listar todas as recorrencias do projeto
bud r l -a

# editar recorrencia #3 da lista completa, atualizar valor, propagar para previsoes vinculadas
bud r e 3 -a -v -1600 --propagate

# excluir recorrencia #5 da lista completa e todas as previsoes vinculadas
bud r d 5 -a -c -y

# excluir recorrencia mas manter previsoes (ficam orfas)
bud r d 5 -a -y
```

## visualizando relatorios de status

```bash
# status do mes atual
bud s

# status de um mes especifico
bud s 2025-04

# status de um projeto especifico
bud s -p empresa
```

o relatorio mostra duas secoes:
1. **balances** - saldo calculado vs atual por conta, com totais e linhas de expectativa
2. **forecasts** - valor planejado de cada previsao, gasto real (correspondido por categoria/tags/descricao) e diferenca restante

## resolucao de ids

bud aceita nomes legiveis em qualquer lugar onde uuids sao esperados:
- projetos: `bud t c -a banco -p pessoal` (resolve "pessoal" para uuid)
- contas: `bud t c -a "cartao"` (resolve por nome dentro do projeto)
- orcamentos: `bud f l 2025-03` (resolve yyyy-mm para uuid do orcamento)
- categorias: `bud t c -c alimentacao` (resolve por nome, ou oferece criar)

## selecao por contador

comandos de edicao e exclusao aceitam um contador de lista (coluna `#` da listagem) em vez de uuid:
- `bud t e 3` - editar transacao #3 do mes atual
- `bud f d 2 -y` - excluir previsao #2 do mes atual
- `bud r e 1 -a` - editar recorrencia #1 da lista completa

## erros comuns e solucoes

**"error: no project specified"** - execute `bud p s <nome>` para definir um projeto padrao.

**"no forecasts found"** - o orcamento daquele mes pode nao existir. crie com `bud b c yyyy-mm`.

**"error: --project required"** - nenhum projeto padrao definido. execute `bud p l` para ver projetos, depois `bud p s <nome>`.

**prompt de categoria nao encontrada** - bud oferece criar categorias novas na hora. responda `y` para criar.

**"forecast is already recurrent"** - nao e possivel transformar uma previsao que ja tem recorrencia em recorrencia novamente.

## sincronizacao com nuvem

```bash
# configurar aws
bud g aws
bud g s bucket s3://meu-bucket/bud

# configurar gcp
bud g gcp
bud g s bucket gs://meu-bucket/bud

# enviar banco local para nuvem
bud db push

# baixar mais recente da nuvem
bud db pull

# forcar push/pull (ignora verificacao de versao)
bud db push --force
bud db pull --force
```

## gerenciamento do banco de dados

```bash
bud db init       # inicializar banco (seguro executar varias vezes)
bud db migrate    # executar migracoes de schema pendentes
bud db destroy    # excluir arquivo do banco (irreversivel, pede confirmacao)
bud db reset      # destruir + reinicializar
```

## recomendações específicas para este usuário

- tudo deve ser registrado com letras minúsculas;

- as contas utilizadas são:

# | name              | type   
-----+-------------------+-----
1 | bb                | debit  
2 | btg-pactual       | debit  
3 | cartao-bb         | credit 
4 | cartao-inter      | credit 
5 | ifood-alimentacao | debit  
6 | ifood-livre       | debit  
7 | ifood-refeicao    | debit  
8 | inter             | debit  
9 | santander         | debit  

- caso o usuário crie novas contas ou exclua, atualize essa seção;

- transferências devem ter categoria e tag "transferências" e a descrição deve ser "transferência origem->destino";

- as transações são armazenadas nestas categorias:

   # | name
-----+------------
   1 | cartão
   2 | filhas
   3 | investimentos
   4 | moradia
   5 | outros
   6 | rendimentos
   7 | salário
   8 | transferências
   9 | transporte

gastos com cartão de crédito são armazenados na categoria "cartão", exceto:

- gastos com a academia (all-in) da filha (marina);
- gastos com dentista da marina;

que devem ser armazenados na categoria "filhas".

- antes de alguma transação ser registrada, deve ser feita uma consulta às recorrências planejadas para o mês;
- devem ser usadas as categorias e tags correspondentes à recorrência que mais fizer sentido;
- gastos com mercado, mercadinho, armazém e conveniências devem ser registrados em categoria "outras", tag "mercado", "mercadinho" ou "conveniência";
- gastos com combustível (geralmente posto de gasolina acima de 50 reais) devem ser registradas com categoria "transporte", tag "combustível";
- na dúvida, transações devem ser lançadas na categoria "outras"

as tags que geralmente são utilizadas são:

- "fixo" ou "variável" para indicar se uma despesa/receita é fixa ou variável;
- "salário-base", "benefícios", "descontos" em transações relacionadas ao salário;
- "marina" e "aurora" para indicar qual a filha relacionada;
- "água", "luz", "telecom", "celular", "tv-internet", "faxina", "jardineiro" e "manutenção" para despesas com moradia; 
- "carro", "manutenção", "lavação", "multa", "ipva", "liecenciamento" para despesas relacionadas ao carro; 
- "serviços" para assinaturas em geral;
- "eletrodomésticos"
- "eletrônicos"
- "presentes"
- "viagens"
- "saúde"
- "lazer"
- "academia"
- "educação"
- "vestuário"
- "aluguel", "dividendos", "jcp" para rendimentos provenientes de investimentos (aluguel de ações, dividendos; jcp);
- "transferências" para transferências internas entre contas

## importação de transações (imagens, csv, pdf)

- ao receber um recibo, nota fiscal, cupom, o usuário deseja importar essa transação para o bud, faça o melhor para encontrar conta, categorias e tag apropriadas e peça confirmação antes de importar;
- ao receber um csv ou um pdf, pode ser que o usuário esteja solicitando a importação das transações a partir do extrato bancário, ou extrato do cartão;
- as transações recebidas no extrato já podem ter sido importadas de alguma outra maneira. consulte as transações já existente, conferindo descrição, data e valor para identificar uma possível duplicidade;
- caso identifique possível duplicidade, informe para o usuário a razão da suspeita e peça confirmação;
- o extrato do banco "inter" chega pelo email, na versão csv e pdf. baixe a versão em csv do email quando solicitado para a importação
- transações de pagamento de cartão devem ter uma entrada positiva na conta relacionada ao cartão (eg: cartão-bb, cartão-inter), e uma negativa na conta-correspondete correspondente (bb, inter);
- pagamento de cartão devem ter categoria "cartão" e tag "pagamento",  e não devem ter tag "fixo" ou "variável";
- o fechamento das faturas dos cartões encerram no último dia do mês, portanto todas as transações devem ser lançadas em um único mês, nesse caso, o mês anterior à data de pagamento da fatura;
- as transações de cartão que tiverem recorrência correspondente dem ter a categoria e tags indicadas na recorrência;
- as transações de cartão que não são associadas a nenhuma recorrência devem ter as categorias e tags que mais fizerem sentido;
- não ignore transações só por terem valor baixo;
- não ignore transferências internas. tente identificar a conta origem/destino da transferência e lance uma transação em cada conta (entrada e saída);
- caso não for possível identificar a conta de origem ou destino da transferência, informe o usuário que será preciso lançar manualmente;
- quando receber um csv com o título seguindo o padrão "Extrato conta corrente - MMYYYY.csv" ou "DOC-YYYYMMDD-*.csv" significa que transações da conta "bb" serão importadas para o bud.
  - a coluna data está no formato dd/mm/yyy.
  - registros com o texto "Saldo" presente na coluna "Lançamento" não devem ser registrado.
  - com base na coluna descrição, é possível inferir a descrição, categorias e tags.
  - transações para "Andressa Machado Martins": devem ser registrados como "pensão (aurora)";
  - transações para "MARINA SCARAMELLA CARGNIN" devem ser registradas como "mesada (marina)";
  - transações para "CASSIA REGINA WICTHOFF" devem ser registradas como "psicóloga (marina)";
  - transações para "REGIA GUEDES FERNANDES" devem ser registradas como "faxina";
  - transações para "LUIZ CESAR COSTA" devem ser registradas como "jardineiro";
  - pagamentos para "VIVO MOVEL" devem ser registradas como "vivo";
  - pagamentos para "CLARO S.A" devem ser registradas como "claro";
  - pagamentos para "CASAN CIA CATARINENSE" devem ser registradas como "casan";
  - pagamentos para "CELESC DISTRIBUICAO S.A" devem ser registradas como "celesc";

- quando receber um pdf com o título "Comptrovante_DD-MM-YYYY_******.pdf" siginifica que transações da conta "cartão-bb" serão importadas para o bud.
  - a fatura referente a um determinado mês pode conter transações realizadas no mês referente à fatura e no mês anterior.
  - o pdf tem uma lista de lançamentos. algumas linhas são lançamentos de fato, e outras indicam quais as tags as transações abaixo dessa linha devem ter;
  - transações abaixo da linha "restaurantes" devem ter categoria "outros" e tag "alimentacao";
  - transações abaixo da linha "lazer" devem ter categoria "outros" e tag "lazer";
  - transações abaixo da linha "saúde" devem ter categoria "outros" e tag "saúde";
  - transações abaixo de linha "serviços" com menção à "posto", ou "galo", com valores acima de 50, devem ter categoria "transporte" e tag "combustivel"
  - transações abaixo de linha "serviços" com menção à "posto", ou "galo", com valores abaixo de 50, devem ter categoria "outros" e tag "conveniência"
  - transações abaixo de linha "serviços" com menção à "fort", "atacadista", "giassi", "supermercado", "mercado", "armazém", devem ter categoria "outros" e a tag apropriada;
  - transações abaixo de linha "serviços" com menção à "uber", devem ter categoria "transporte" e tag "uber"
  - transações abaixo de linha "serviços" com menção à "prime", devem ser lançadas como "prime" e ter categoria "cartão" e tag "serviços,lazer"
  - transações abaixo de linha "serviços" com menção à "netflix", ser lançadas como "netflix" e ter categoria "cartão" e tag "serviços,lazer"
  - transações abaixo de linha "serviços" com menção à "claude", "anthropic", "chatgpt" ou "openai", devem ter categoria "cartão" e tag "serviços,ai"
  - devem ser consultados os forecasts do mês correspondente para identificar se alguma compra ou parcela estava prevista, lançar com a descrição conforme o forecast
  - parcelas de compras realizadas em meses anteriores presentes na fatura do mês atual são registradas como transações do mês atual, com data correspondete ao primeiro dia do mês;

## referências

- [README](references/README.md)
