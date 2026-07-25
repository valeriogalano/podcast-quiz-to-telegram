# Botcaster Quiz Generator

Bot Telegram che pubblica quotidianamente un quiz basato sugli episodi del podcast Pensieri in Codice, generato da un LLM (Google Gemini o Anthropic Claude, configurabile via `QUIZ_PROVIDER`).

## Setup locale

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # compila i valori reali
python quiz_bot.py
```

## Test

```bash
source .venv/bin/activate
python -m pytest test_quiz_bot.py -v
```

## Variabili d'ambiente

Vedi `.env.example`. Le variabili obbligatorie sono `TELEGRAM_CHAT_ID`, `TELEGRAM_BOT_TOKEN` e la chiave del provider AI scelto (`ANTHROPIC_API_KEY` e/o `GOOGLE_API_KEY`).

`QUIZ_PROVIDER` è opzionale: provider AI da usare, `google`/`gemini` o `anthropic`/`claude`, anche più di uno separato da virgola come fallback. Default: `google`.

## Workflow GitHub Actions

`quiz.yml` — si esegue alle 11:00 e alle 15:00 UTC (cron `0 11,15 * * *`), oppure manualmente via `workflow_dispatch`. Ogni esecuzione pubblica un quiz. Le variabili d'ambiente sensibili vengono passate come GitHub Secrets, le altre come GitHub Variables.

## Logica principale

- 75% delle esecuzioni: quiz generico su informatica/programmazione
- 25% delle esecuzioni: quiz basato su un episodio casuale del feed RSS (trascrizione + script GitHub se disponibile)
- Per i quiz basati su un episodio, dopo il poll viene pubblicato un messaggio separato (in reply al poll) con il riferimento all'episodio: titolo + link cliccabile alla pagina del sito (dal campo `link` del feed RSS), con anteprima. Se l'invio del messaggio fallisce, il quiz resta comunque pubblicato.
