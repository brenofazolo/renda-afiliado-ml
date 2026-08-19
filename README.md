# Renda Afiliado ML

Motor inicial para descoberta, análise e priorização de oportunidades de afiliados do Mercado Livre.

## MVP 0.1

Fluxo atual:

```text
Mercado Livre API
      ↓
Busca de produtos
      ↓
Normalização
      ↓
Score de oportunidade
      ↓
Ranking
      ↓
CSV com oportunidades
```

O projeto começa deliberadamente simples. A prioridade é colocar a operação para funcionar rapidamente e evoluir com dados reais.

## Princípios

- Usar APIs e integrações oficiais sempre que possível.
- Nunca armazenar tokens ou chaves no Git.
- Diferenciar dados observados de estimativas.
- Não assumir comissão de afiliado quando ela não estiver disponível na fonte.
- Registrar data/hora da coleta para construir histórico.

## Execução local

1. Criar ambiente virtual.
2. Instalar dependências com `pip install -r requirements.txt`.
3. Copiar `.env.example` para `.env`.
4. Configurar o token do Mercado Livre, quando necessário.
5. Executar `python -m app.main --query "air fryer"`.

O resultado será salvo em `data/oportunidades.csv`.

## Próximas evoluções

- histórico de preços e posições;
- reviews e reputação do vendedor;
- tendência própria;
- score de afiliado;
- geração de conteúdo com IA;
- tracking de links;
- dashboard;
- automação periódica.
