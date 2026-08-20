# Renda Afiliado ML

Motor inicial para descoberta, análise e priorização de oportunidades para afiliados do Mercado Livre.

## MVP 0.3

Fluxo atual:

```text
Mercado Livre API
      ↓
Busca de produtos de catálogo
      ↓
Oferta vencedora (buy box)
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

- busca de produtos ativos de catálogo (`/products/search`);
- detalhe do produto e oferta vencedora, quando disponível (`/products/{product_id}`);
- detalhe e hierarquia da categoria (`/categories/{category_id}`);
- ranking de Mais Vendidos do produto (`/highlights/{site_id}/product/{product_id}`);
- preço, desconto, frete e logística informados na oferta vencedora.

A API também oferece `/products/{product_id}/items` para listar as publicações concorrentes de uma página de produto. Para manter este MVP simples, a versão atual usa somente `buy_box_winner`. Produtos sem uma oferta vencedora são ignorados.

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

Se o repositório já estiver no GitHub Desktop, clique em **Fetch origin** e depois em **Pull origin**.

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

### 5. Executar o teste

```powershell
python -m app.main --query "air fryer" --limit 20
```

O resultado será salvo em:

```text
data/oportunidades.csv
```

O número de produtos analisados pode ser menor que o limite solicitado, porque produtos sem `buy_box_winner` são ignorados.

## Próximas evoluções

- validar e cadastrar a tabela oficial de comissão;
- avaliar todas as ofertas concorrentes por produto;
- coletar reviews e reputação do vendedor;
- histórico de preços, posições e avaliações;
- tendência própria;
- score de afiliado completo;
- geração de conteúdo com IA;
- tracking de links;
- dashboard;
- automação periódica.
