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
GitHub Actions (diariamente às 10:00)
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

O serviço também possui um agendador interno diário. O workflow do GitHub Actions é a camada mais importante em produção gratuita, pois acorda o serviço do Render quando ele entra em estado de espera.

## Interface web

A página inicial está disponível em:

```text
https://dou-leis-mps.onrender.com/
```

Ela mostra:

- status do serviço;
- horário diário e fuso horário configurados;
- indicador de conexão com o Telegram;
- contador regressivo para a próxima verificação estimada;
- execução manual por data;
- lista de publicações salvas.

O contador é uma estimativa visual baseada no horário diário configurado. A execução real é feita pelo agendador interno e pelo workflow diário.

## Rodar localmente

Requisitos: Python 3.11+ e, opcionalmente, PostgreSQL. Para desenvolvimento, SQLite é usado automaticamente quando `DATABASE_URL` não é informado.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Abra `http://127.0.0.1:8000/`. A documentação interativa da API fica em `http://127.0.0.1:8000/docs`.

A documentação interativa fica desativada por padrão. Para habilitá-la localmente, defina `ENABLE_DOCS=true` no `.env` e reinicie o servidor. Não habilite essa opção em produção sem necessidade.

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
| `ALLOWED_HOSTS` | Não | Hosts aceitos pelo servidor. Inclua o domínio público e hosts locais separados por vírgula. |
| `READ_API_KEY` | Sim | Autoriza consultas em `/api/laws` e `/api/runs`. |
| `SCRAPE_API_KEY` | Sim | Autoriza execuções em `/api/scrape`. Deve ser diferente da READ key. |
| `TELEGRAM_BOT_TOKEN` | Para publicar | Token criado pelo @BotFather. |
| `TELEGRAM_CHAT_ID` | Para publicar | ID do canal/grupo, por exemplo `-100...`, ou `@username` em canal público. |
| `TELEGRAM_PUBLIC_URL` | Não | Link público ou convite `https://t.me/...` usado no botão da landing page. Se vazio, o sistema tenta obter o link pelo Bot API. |
| `SCRAPE_INTERVAL_MINUTES` | Compatibilidade | Mantida como `1440` para indicar um ciclo diário. O horário fixo é definido pelas duas variáveis abaixo. |
| `SCRAPE_HOUR` | Não | Hora da coleta no fuso configurado. Padrão: `8`. |
| `SCRAPE_MINUTE` | Não | Minuto da coleta. Padrão: `0`. |
| `ENABLE_DOCS` | Não | Habilita `/docs`, `/redoc` e `/openapi.json`. Padrão: `false`. |
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

A landing page tenta descobrir o endereço do grupo usando `getChat`, sem expor o token do bot ao navegador. O deploy atual usa `TELEGRAM_PUBLIC_URL=https://t.me/+81PSoHU2iPcwZWRh` para garantir que o botão “Entrar no grupo do Telegram” sempre apareça.

Para que novos integrantes vejam mensagens antigas, abra as informações do grupo no Telegram e acesse **Editar > Tipo do grupo > Histórico do chat para novos membros > Visível**. Essa opção pertence ao grupo e não pode ser alterada pela Bot API. Em canais, o histórico normalmente já fica disponível para novos inscritos.

## API

As rotas protegidas recebem a chave no cabeçalho `X-API-Key`. A chave nunca deve ser enviada na URL, pois URLs podem aparecer em históricos, logs e ferramentas de monitoramento.

### `GET /api/health`

Endpoint público de saúde e configuração não sensível:

```json
{
  "status": "ok",
  "scrape_interval_minutes": 1440,
  "schedule_hour": 8,
  "schedule_minute": 0,
  "schedule_label": "diariamente às 10:00 (America/Sao_Paulo)",
  "timezone": "America/Sao_Paulo",
  "auth_configured": true,
  "telegram_configured": true
}
```

### `GET /api/laws`

Lista publicações salvas. Exige `X-API-Key: READ_API_KEY`.

Parâmetros:

- `date=YYYY-MM-DD` filtra por data;
- `limit=100` limita o resultado, entre 1 e 500.

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

Lista as últimas execuções do scraper. Exige `X-API-Key: READ_API_KEY`. O parâmetro `limit` aceita valores entre 1 e 100.

As respostas da API usam `Cache-Control: no-store` para evitar que dados protegidos sejam armazenados por caches intermediários.

## Agendamento em produção

O workflow `.github/workflows/daily-scrape.yml` é executado uma vez por dia às 10:00 no horário de Brasília. Como o GitHub Actions usa UTC, o cron é `0 13 * * *`. Ele faz uma requisição autenticada para `/api/scrape`.

O serviço também agenda uma execução diária às 10:00 usando `CronTrigger` no fuso `America/Sao_Paulo`. Os dois mecanismos possuem a mesma finalidade; o workflow do GitHub funciona como despertador externo para o plano gratuito do Render.

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

O plano gratuito pode colocar o web service em espera após inatividade. Por isso o workflow diário do GitHub Actions deve permanecer ativo. O banco PostgreSQL gratuito também pode ter prazo ou limites definidos pelo provedor; monitore o painel do Render.

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

Medidas implementadas:

- `READ_API_KEY` e `SCRAPE_API_KEY` são distintas e comparadas com `secrets.compare_digest`.
- A coleta manual (`POST /api/scrape`) e as consultas (`/api/laws` e `/api/runs`) exigem `X-API-Key`.
- A documentação automática da FastAPI fica desativada por padrão em produção.
- O servidor valida o cabeçalho `Host` com `ALLOWED_HOSTS`.
- A aplicação envia `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` e HSTS quando acessada por HTTPS.
- Dados de API não são armazenados em cache.
- Links coletados e enviados ao Telegram são aceitos apenas quando usam HTTPS e pertencem a `in.gov.br` ou `www.in.gov.br`.
- O frontend escapa texto antes de inserir conteúdo retornado pela API e valida novamente o domínio do link.
- A aplicação não usa cookies de autenticação; por isso, o fluxo de API por cabeçalho não depende de sessão nem de CSRF.

Boas práticas operacionais:

- Não commite `.env`, tokens, chaves de API ou URLs de banco com senha.
- Use chaves longas, aleatórias e diferentes para leitura e scraping.
- Mantenha o `TELEGRAM_BOT_TOKEN` somente nos secrets do Render e do GitHub Actions quando necessário.
- Se uma chave ou token for compartilhado, revogue-o e gere outro. O token do Telegram que foi compartilhado durante a configuração deve ser rotacionado no `@BotFather` antes de uma operação pública.
- Revise periodicamente os logs do Render e as execuções do GitHub Actions.
- O link publicado pelo bot aponta para o DOU; a fonte oficial deve ser lida antes de qualquer uso jurídico.

### Dependências

`requirements.txt` contém apenas dependências de runtime. `requirements-dev.txt` adiciona ferramentas de teste e auditoria. Para verificar vulnerabilidades conhecidas:

```bash
pip install -r requirements-dev.txt
pip-audit -r requirements.txt
```

Atualize as dependências quando o auditor indicar uma versão corrigida e rode toda a suíte de testes antes do deploy.

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
