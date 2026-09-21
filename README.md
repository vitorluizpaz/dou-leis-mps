# DOU Leis e MPs

Bot que monitora a Seção 1 do Diário Oficial da União, identifica novas **Leis** e **Medidas Provisórias**, armazena os resultados em PostgreSQL e publica cada item novo em um grupo ou canal do Telegram.

## O que a aplicação faz

1. Consulta o portal oficial do DOU para uma data.
2. Localiza publicações cujo título contém `Lei` ou `Medida Provisória`.
3. Normaliza e remove duplicatas pelo fingerprint do item.
4. Salva título, tipo, número, data e link oficial no banco.
5. Envia ao Telegram somente publicações ainda não enviadas.
6. Registra cada envio para não publicar a mesma lei duas vezes.

A mensagem enviada ao Telegram contém o título da publicação e um link **Clique para ler** que aponta para a fonte oficial. O sistema não replica o texto integral do ato.

## Arquitetura

```text
GitHub Actions (a cada hora)
             |
             v
      POST /api/scrape
             |
             v
   FastAPI + APScheduler
       |          |
       v          v
   PostgreSQL   Telegram Bot API
       |
       v
    GET /api/laws
```

O serviço também possui um agendador interno de 60 minutos. O workflow do GitHub Actions é a camada mais importante em produção gratuita, pois acorda o serviço do Render quando ele entra em estado de espera.

## Interface web

A página inicial está disponível em:

```text
https://dou-leis-mps.onrender.com/
```

Ela mostra:

- status do serviço;
- intervalo e fuso horário configurados;
- indicador de conexão com o Telegram;
- contador regressivo para a próxima verificação estimada;
- execução manual por data;
- lista de publicações salvas.

O contador é uma estimativa visual baseada no intervalo configurado. A execução real é feita pelo agendador interno e pelo workflow horário.

## Rodar localmente

Requisitos: Python 3.11+ e, opcionalmente, PostgreSQL. Para desenvolvimento, SQLite é usado automaticamente quando `DATABASE_URL` não é informado.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Abra `http://127.0.0.1:8000/`. A documentação interativa da API fica em `http://127.0.0.1:8000/docs`.

Para executar uma coleta local:

```bash
python -m app.cli scrape --date 2026-09-20
```

Para rodar os testes:

```bash
PYTHONPATH=. .venv/bin/pytest -q
```

## Variáveis de ambiente

Copie `.env.example` e preencha os valores no ambiente local ou no Render. Nunca coloque secrets no GitHub, no HTML ou em commits.

| Variável | Obrigatória | Função |
| --- | --- | --- |
| `DATABASE_URL` | Produção | URL do PostgreSQL. SQLite serve para desenvolvimento. |
| `READ_API_KEY` | Sim | Autoriza consultas em `/api/laws` e `/api/runs`. |
| `SCRAPE_API_KEY` | Sim | Autoriza execuções em `/api/scrape`. Deve ser diferente da READ key. |
| `TELEGRAM_BOT_TOKEN` | Para publicar | Token criado pelo @BotFather. |
| `TELEGRAM_CHAT_ID` | Para publicar | ID do canal/grupo, por exemplo `-100...`, ou `@username` em canal público. |
| `SCRAPE_INTERVAL_MINUTES` | Não | Intervalo do agendador interno. Padrão: `60`. |
| `TIMEZONE` | Não | Fuso horário. Padrão: `America/Sao_Paulo`. |
| `DOU_BASE_URL` | Não | Endpoint da leitura do DOU. |
| `REQUEST_TIMEOUT` | Não | Timeout das requisições externas. |

### Como as chaves da API são usadas

As chaves de leitura e scraping são chaves da **aplicação**, não do Telegram:

```bash
curl -H "X-API-Key: $READ_API_KEY" \
  "https://dou-leis-mps.onrender.com/api/laws?date=2026-09-20"

curl -X POST -H "X-API-Key: $SCRAPE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-09-20"}' \
  "https://dou-leis-mps.onrender.com/api/scrape"
```

Na interface web, informe a `READ_API_KEY` para consultar publicações e a `SCRAPE_API_KEY` para executar uma coleta manual. O token do Telegram nunca deve ser colocado nesses campos.

## Configurar o Telegram

1. Abra o `@BotFather` e crie um bot com `/newbot`.
2. Guarde o token em `TELEGRAM_BOT_TOKEN`.
3. Adicione o bot ao grupo ou canal.
4. Promova-o a administrador com permissão para enviar mensagens.
5. Configure o ID do destino em `TELEGRAM_CHAT_ID`.

Para um grupo privado, o ID normalmente começa com `-100`. Para obter o ID, envie uma mensagem no grupo e consulte `getUpdates` usando o token do bot. Em produção, prefira cadastrar o valor diretamente nos secrets do Render e não em arquivos locais.

## API

### `GET /api/health`

Endpoint público de saúde e configuração não sensível:

```json
{
  "status": "ok",
  "scrape_interval_minutes": 60,
  "timezone": "America/Sao_Paulo",
  "auth_configured": true,
  "telegram_configured": true
}
```

### `GET /api/laws`

Lista publicações salvas. Exige `X-API-Key: READ_API_KEY`.

Parâmetros:

- `date=YYYY-MM-DD` filtra por data;
- `limit=100` limita o resultado, até 500.

### `POST /api/scrape`

Executa coleta imediata. Exige `X-API-Key: SCRAPE_API_KEY`.

Corpo opcional:

```json
{"date":"2026-09-20"}
```

A resposta informa quantidade encontrada, quantidade nova e quantidade enviada ao Telegram:

```json
{"date":"2026-09-20","found":2,"new":2,"telegram_sent":2,"items":[]}
```

### `GET /api/runs`

Lista as últimas execuções do scraper. Exige `X-API-Key: READ_API_KEY`.

## Agendamento em produção

O workflow `.github/workflows/hourly-scrape.yml` é executado no minuto `00` de cada hora e faz uma requisição autenticada para `/api/scrape`.

No GitHub, configure estes secrets no repositório:

| Secret | Valor |
| --- | --- |
| `API_URL` | `https://dou-leis-mps.onrender.com` |
| `SCRAPE_API_KEY` | A mesma chave configurada no Render |

Também é possível iniciar o workflow manualmente pela aba **Actions** usando **Run workflow**.

## Deploy no Render

O arquivo `render.yaml` descreve o serviço web e o banco PostgreSQL. O fluxo usado neste projeto é:

1. Repositório no GitHub conectado ao Render.
2. Web Service criado a partir do `render.yaml`.
3. PostgreSQL criado no Render.
4. `DATABASE_URL`, chaves da API e variáveis do Telegram cadastradas em **Environment**.
5. Deploy automático após cada push na branch `main`.

O plano gratuito pode colocar o web service em espera após inatividade. Por isso o workflow horário do GitHub Actions deve permanecer ativo. O banco PostgreSQL gratuito também pode ter prazo ou limites definidos pelo provedor; monitore o painel do Render.

## Histórico de teste

Para validar uma janela histórica, execute a API uma vez para cada data desejada. Exemplo para 14 dias:

```bash
for day in $(seq 0 13); do
  target=$(date -v-${day}d +%F) # macOS
  curl --fail-with-body -sS -X POST \
    -H "X-API-Key: $SCRAPE_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"date\":\"$target\"}" \
    "https://dou-leis-mps.onrender.com/api/scrape"
done
```

Itens históricos ainda não enviados também podem ser publicados no Telegram, pois a aplicação evita duplicatas usando a tabela `telegram_deliveries`.

Em 20/09/2026, a janela de 07/09/2026 a 20/09/2026 foi executada em produção: foram feitas 14 consultas, 4 publicações foram encontradas no DOU em 3 datas, nenhuma foi inserida como nova porque já estava no banco, e 2 entregas pendentes foram concluídas no Telegram. Isso confirmou o fluxo autenticado da aplicação sem republicar itens duplicados.

## Segurança

- Não commite `.env`, tokens, chaves de API ou URLs de banco com senha.
- Use `READ_API_KEY` e `SCRAPE_API_KEY` diferentes e longas.
- Mantenha o `TELEGRAM_BOT_TOKEN` apenas nos secrets do Render.
- Se um token for compartilhado ou exposto, revogue-o no @BotFather e gere outro.
- O endpoint de scraping é protegido por `X-API-Key`.
- O link publicado pelo bot aponta para o DOU; a fonte oficial deve ser lida antes de qualquer uso jurídico.

## Estrutura do projeto

```text
app/
  cli.py              # execução via terminal
  config.py           # configuração por ambiente
  db.py               # tabelas e persistência
  main.py             # FastAPI e agendamento
  models.py           # modelo de publicação
  scraper.py          # coleta e parsing do DOU
  telegram.py         # envio e deduplicação no Telegram
  static/index.html   # interface web
tests/                # testes automatizados
render.yaml           # configuração do Render
```
