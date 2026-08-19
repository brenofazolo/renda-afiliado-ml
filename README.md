# Renda Afiliado ML

Motor inicial para descoberta, análise e priorização de oportunidades para afiliados do Mercado Livre.

## MVP 0.2

Fluxo atual:

```text
Mercado Livre API
      ↓
Busca de produtos
      ↓
Categoria + hierarquia
      ↓
Ranking de Mais Vendidos
      ↓
Preço + desconto + frete
      ↓
Regra de comissão por categoria
      ↓
Opportunity Score provisório
      ↓
TOP oportunidades
      ↓
CSV
```

O projeto continua deliberadamente simples. A prioridade é colocar a operação para funcionar rapidamente e evoluir com dados reais.

## Dados usados

O MVP utiliza recursos oficiais do Mercado Livre para:

- busca de anúncios;
- detalhe/categoria do anúncio;
- hierarquia de categorias;
- ranking de Mais Vendidos (`/highlights`);
- preço e desconto quando disponíveis;
- frete/logística;
- atributos básicos do anúncio.

A API oficial documenta o recurso `/highlights` para consultar os 20 principais produtos/itens de uma categoria e também a posição de um item no ranking. A consulta exige autenticação.

A comissão de afiliado é mantida em `config/affiliate_commissions.json`. Os percentuais não são preenchidos automaticamente a partir de fontes de terceiros: a tabela oficial do programa deve ser validada e cadastrada antes de o score usar esse componente.

## Princípios

- Usar APIs e integrações oficiais sempre que possível.
- Nunca armazenar tokens ou chaves no Git.
- Diferenciar dados observados de estimativas.
- Não inventar comissão de afiliado.
- Registrar data/hora da coleta para construir histórico.

## Execução local

### 1. Clonar o repositório

```bash
git clone https://github.com/brenofazolo/renda-afiliado-ml.git
cd renda-afiliado-ml
```

### 2. Criar ambiente virtual

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Windows CMD:

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

### 3. Instalar dependências

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Criar o arquivo `.env`

Copie `.env.example` para `.env` e informe o token oficial do Mercado Livre:

```env
MELI_ACCESS_TOKEN=seu_token_aqui
MELI_SITE_ID=MLB
MELI_QUERY=air fryer
MELI_LIMIT=20
```

**Nunca faça commit do `.env`.** Ele já está no `.gitignore`.

### 5. Executar o primeiro teste

```bash
python -m app.main --query "air fryer" --limit 20
```

O resultado será salvo em:

```text
data/oportunidades.csv
```

## Próximas evoluções

- validar e cadastrar a tabela oficial de comissão;
- coletar reviews e reputação do vendedor;
- histórico de preços, posições e avaliações;
- tendência própria;
- score de afiliado completo;
- geração de conteúdo com IA;
- tracking de links;
- dashboard;
- automação periódica.
