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

`TELEGRAM_ACTIVITY_CHAT_ID` è opzionale: se impostata, il quiz viene saltato se quel gruppo ha avuto attività all'interno della finestra configurata. Default: `TELEGRAM_CHAT_ID`.

`TELEGRAM_ACTIVITY_WINDOW_MINUTES` è opzionale: durata in minuti della finestra di controllo attività. Default: `240` (= 4 ore). Variabile assente o stringa vuota sono equivalenti e cadono sul default (così GitHub Actions può iniettare `vars.*` non definite senza rompere il job).

## Workflow GitHub Actions

`quiz.yml` — si esegue ogni ora dalle 08:00 alle 17:00 UTC (cron `0 8-17 * * *`), oppure manualmente via `workflow_dispatch`. A ogni esecuzione `has_recent_activity` decide se pubblicare o saltare. Le variabili d'ambiente sensibili vengono passate come GitHub Secrets, le altre come GitHub Variables.

## Logica principale

- 75% delle esecuzioni: quiz generico su informatica/programmazione
- 25% delle esecuzioni: quiz basato su un episodio casuale del feed RSS (trascrizione + script GitHub se disponibile)
- Per i quiz basati su un episodio, dopo il poll viene pubblicato un messaggio separato (in reply al poll) con il riferimento all'episodio: titolo + link cliccabile alla pagina del sito (dal campo `link` del feed RSS), con anteprima. Se l'invio del messaggio fallisce, il quiz resta comunque pubblicato.
- Se il gruppo di riferimento ha avuto attività nella finestra configurata (default 240 minuti), il quiz viene saltato (`exit 0`)
