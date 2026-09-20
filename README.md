# DOU Leis e MPs

MVP em Python que consulta a seção 1 do Diário Oficial da União, identifica publicações de **Leis** e **Medidas Provisórias**, salva os resultados em SQLite e oferece uma API e uma interface web de teste.

## Rodar localmente

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Abra http://127.0.0.1:8000. A documentação da API fica em http://127.0.0.1:8000/docs.

Para executar uma coleta manual:

```bash
python -m app.cli scrape --date 2026-09-20
```

## API

- `GET /api/health`
- `GET /api/laws?date=YYYY-MM-DD&limit=100` com `X-API-Key: READ_API_KEY`
- `POST /api/scrape` com corpo opcional `{ "date": "YYYY-MM-DD" }` e `X-API-Key: SCRAPE_API_KEY`
- `GET /api/runs` com `X-API-Key: READ_API_KEY`

Cada item possui `title`, `kind`, `number`, `summary`, `published_date` e `source_url`. O link aponta para a publicação oficial; o scraper não republica o texto integral.

## Agendamento

O processo da API sobe um job interno que consulta o DOU a cada `SCRAPE_INTERVAL_MINUTES`. O padrão é **a cada 60 minutos**, no fuso de Brasília. Como a fonte não garante um horário fixo universal, a coleta periódica é mais segura que depender de uma única hora.

Configure `READ_API_KEY` e `SCRAPE_API_KEY` no `.env`. Use chaves diferentes; em produção, não publique nenhuma delas nem as coloque no código-fonte. `DATABASE_URL` deve apontar para PostgreSQL; SQLite fica apenas para desenvolvimento local.

Em produção, recomenda-se manter um único processo da API. Se preferir cron do sistema, use:

```cron
0 * * * * cd /caminho/do/projeto && .venv/bin/python -m app.cli scrape >> logs/scrape.log 2>&1
```

## Limitações conhecidas

O portal oficial pode alterar o HTML. O parser procura os blocos JSON publicados pela própria página e tem fallback para links de matérias. A cobertura deve ser validada em execução contra uma edição real antes de ativar o Telegram.

## Deploy gratuito sugerido

O arquivo `render.yaml` prepara a API para o Render. Configure `DATABASE_URL` usando um PostgreSQL externo e as duas chaves como secrets. O workflow `.github/workflows/hourly-scrape.yml` chama a API uma vez por hora; isso é necessário porque o serviço gratuito do Render pode dormir.
