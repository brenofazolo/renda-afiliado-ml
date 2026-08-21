# Renda Afiliado ML

Motor inicial para descoberta, análise e priorização de oportunidades para afiliados do Mercado Livre.

## MVP 0.6 em teste

Fluxo atual:

```text
Mercado Livre API
      ↓
Busca de produtos de catálogo
      ↓
Filtro pelo domínio predominante
      ↓
Ofertas válidas da busca
      ↓
Categoria predominante das ofertas
      ↓
TOP 20 de mais vendidos da categoria
      ↓
Adição de produtos do ranking ainda ausentes da busca
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

## Descoberta de candidatos

O MVP combina duas fontes oficiais de candidatos:

1. `/products/search`, que traz produtos relevantes para a consulta informada;
2. `/highlights/{site_id}/category/{category_id}`, que traz até 20 produtos mais vendidos da categoria identificada.

Os IDs retornados pelo ranking com `type=PRODUCT` são `catalog_product_id`. Produtos do ranking que já estavam entre as ofertas válidas da busca não são duplicados. Para os demais, o sistema tenta encontrar uma oferta concreta e adicioná-la ao pool final.

O ranking de mais vendidos é um sinal de demanda, não o ranking final. O `TOP OPORTUNIDADES` continua sendo calculado pelo MVP considerando demanda, preço/oferta, comissão, frete, condição, potencial visual e loja oficial.

## Dados usados

O MVP utiliza recursos oficiais do Mercado Livre para:

- busca de produtos ativos de catálogo (`/products/search`);
- detalhe do produto e oferta vencedora, quando disponível (`/products/{product_id}`);
- fallback para uma oferta associada quando `buy_box_winner` estiver vazio (`/products/{product_id}/items`);
- detalhe e hierarquia da categoria (`/categories/{category_id}`);
- TOP de Mais Vendidos por categoria (`/highlights/{site_id}/category/{category_id}`);
- preço, desconto, frete e logística informados na oferta selecionada.

A versão atual prefere `buy_box_winner`. Quando ele vem vazio, usa a primeira oferta concreta retornada por `/products/{product_id}/items`. O CSV registra essa decisão no campo `offer_source`. Produtos sem oferta acessível continuam sendo ignorados.

Para reduzir falsos positivos, a busca identifica o `domain_id` mais frequente nos resultados e mantém somente esse domínio. A categoria usada no ranking é a categoria mais frequente entre as ofertas válidas da busca.

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

As comissões direta e indireta são exibidas separadamente como estimativas calculadas sobre o preço coletado. Somente a comissão direta participa do score atual. A indireta permanece como indicador informativo, pois representa uma compra alternativa e não deve ser somada à direta como se ambas ocorressem na mesma venda.

A elegibilidade da venda, a atribuição, eventuais ganhos extras, cancelamentos, impostos e o pagamento final dependem das regras e da validação do Programa de Afiliados e Criadores do Mercado Livre. A fonte registrada para as faixas é a página oficial [Quanto se ganha por venda](https://www.mercadolivre.com.br/ajuda/27913).

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

Copie `.env.example` para `.env` e informe as credenciais/tokens oficiais do Mercado Livre. **Nunca faça commit do `.env`.** Ele já está no `.gitignore`.

## Renovação automática do token

Todas as chamadas do MVP passam por `app/token_manager.py`. Quando a validade registrada estiver próxima do fim, ou quando uma chamada retornar `401`, o módulo:

1. envia o `MELI_REFRESH_TOKEN` para `/oauth/token`;
2. recebe um novo access token e um novo refresh token;
3. substitui os dois juntos no `.env`;
4. registra `MELI_TOKEN_EXPIRES_AT`;
5. repete a chamada original uma única vez.

O Mercado Livre permite usar somente o refresh token mais recente. Por isso, os dois tokens são persistidos juntos e nunca impressos no terminal. Em caso de `invalid_grant`, revogação ou expiração do refresh token, será necessária uma nova autorização manual.

### 5. Executar o teste

```powershell
python -m app.main --query "air fryer" --limit 20
```

O resultado será salvo em `data/oportunidades.csv`.

## Interface web piloto

A interface usa o mesmo pipeline do comando acima, roda localmente no PC e exige
um usuário e uma senha simples definidos no `.env`. Ela não possui cadastro,
recuperação de senha ou banco de usuários.

### 1. Configurar o acesso

Além das credenciais do Mercado Livre, preencha no `.env`:

```dotenv
WEB_USERNAME=seu_usuario
WEB_PASSWORD=uma_senha_forte
WEB_SECRET_KEY=uma_chave_aleatoria_longa
WEB_HOST=127.0.0.1
WEB_PORT=5000
```

`WEB_HOST=127.0.0.1` restringe o acesso ao próprio PC. Para um primeiro teste em
outro aparelho da mesma rede, use `WEB_HOST=0.0.0.0` e acesse o endereço IP do PC.
Não exponha este servidor diretamente à internet: esta autenticação é adequada
somente para o piloto local.

### 2. Iniciar a interface

Com o ambiente virtual ativado e as dependências instaladas:

```powershell
python -m app.web
```

Abra [http://127.0.0.1:5000](http://127.0.0.1:5000), entre com os dados do `.env`
e faça uma consulta por texto e limite (de 1 a 50 resultados iniciais).

A tela mostra título, preço, score, posição entre os mais vendidos, comissões
direta e indireta, link direto quando disponível, busca alternativa no Mercado
Livre, resumo da coleta e tempo total.

## Próximas evoluções

- validar periodicamente as taxas oficiais;
- tratar cupons personalizados separadamente;
- comparar ofertas concorrentes;
- coletar reviews e reputação do vendedor;
- histórico de preços, posições e avaliações;
- geração de conteúdo, tracking de links e dashboard.
