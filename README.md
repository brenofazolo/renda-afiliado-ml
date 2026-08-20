# Renda Afiliado ML

Motor inicial para descoberta, análise e priorização de oportunidades para afiliados do Mercado Livre.

## MVP 0.5 em teste

Fluxo atual:

```text
Mercado Livre API
      ↓
Busca de produtos de catálogo
      ↓
Filtro pelo domínio predominante
      ↓
Oferta vencedora ou oferta associada
      ↓
Categoria + hierarquia
      ↓
Categoria raiz
      ↓
Regra de comissão para afiliado generalista
      ↓
Preço + comissão estimada
      ↓
Opportunity Score provisório
      ↓
TOP oportunidades + diagnóstico
      ↓
CSV
```

O projeto continua deliberadamente simples. A prioridade é colocar a operação para funcionar rapidamente e evoluir com dados reais.

## Dados usados

O MVP utiliza recursos oficiais do Mercado Livre para:

- busca de produtos ativos de catálogo (`/products/search`);
- detalhe do produto e oferta vencedora, quando disponível (`/products/{product_id}`);
- fallback para uma oferta associada quando `buy_box_winner` estiver vazio (`/products/{product_id}/items`);
- detalhe e hierarquia da categoria (`/categories/{category_id}`);
- ranking de Mais Vendidos do produto (`/highlights/{site_id}/product/{product_id}`);
- preço, desconto, frete e logística informados na oferta selecionada.

A versão atual prefere `buy_box_winner`. Quando ele vem vazio, usa a primeira oferta concreta retornada por `/products/{product_id}/items`. O CSV registra essa decisão no campo `offer_source`. Produtos sem oferta acessível continuam sendo ignorados.

Para reduzir falsos positivos, a coleta identifica o `domain_id` mais frequente nos resultados e mantém somente esse domínio. A saída mostra quantos produtos foram encontrados, filtrados e associados a ofertas.

O MVP não depende de `/items/{item_id}`, pois esse recurso pode estar bloqueado para a aplicação. O permalink do anúncio permanece vazio até existir uma fonte oficial acessível para obtê-lo.

## Comissão de afiliado

As regras ficam centralizadas em `config/affiliate_commissions.json` e usam como chave a categoria raiz do `category_path` oficial. Exemplo:

```text
Eletrodomésticos > Pequenos Eletrodomésticos > ...
        ↓
Eletrodomésticos
        ↓
12% direta / 6% indireta
```

Esta versão inclui somente a tabela normal para afiliados generalistas. A tabela de cupons personalizados foi deliberadamente deixada para uma fase posterior.

A comissão exibida é uma estimativa calculada sobre o preço coletado. A elegibilidade da venda, a atribuição, eventuais ganhos extras, cancelamentos, impostos e o pagamento final dependem das regras e da validação do Programa de Afiliados e Criadores do Mercado Livre. A fonte registrada para as faixas é a página oficial [Quanto se ganha por venda](https://www.mercadolivre.com.br/ajuda/27913).

## Princípios

- Usar APIs e integrações oficiais sempre que possível.
- Nunca armazenar tokens ou chaves no Git.
- Diferenciar dados observados de estimativas.
- Centralizar taxas configuráveis.
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

O resultado será salvo em `data/oportunidades.csv`.

## Próximas evoluções

- validar periodicamente as taxas oficiais;
- tratar cupons personalizados separadamente;
- comparar ofertas concorrentes;
- melhorar ranking de mais vendidos;
- coletar reviews e reputação do vendedor;
- histórico de preços, posições e avaliações;
- geração de conteúdo, tracking de links e dashboard.
