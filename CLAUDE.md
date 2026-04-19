# Botcaster Quiz Generator

Bot Telegram che pubblica quotidianamente un quiz basato sugli episodi del podcast Pensieri in Codice, generato da Claude AI (Haiku).

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

Vedi `.env.example`. Le variabili obbligatorie sono `TELEGRAM_CHAT_ID`, `TELEGRAM_BOT_TOKEN` e `ANTHROPIC_API_KEY`.

`TELEGRAM_ACTIVITY_CHAT_ID` è opzionale: se impostata, il quiz viene saltato se quel gruppo ha avuto attività all'interno della finestra configurata. Default: `TELEGRAM_CHAT_ID`.

`TELEGRAM_ACTIVITY_WINDOW_MINUTES` è opzionale: durata in minuti della finestra di controllo attività. Default: `240` (= 4 ore). Variabile assente o stringa vuota sono equivalenti e cadono sul default (così GitHub Actions può iniettare `vars.*` non definite senza rompere il job).

## Workflow GitHub Actions

`quiz.yml` — si esegue ogni giorno alle 09:00 UTC (o manualmente via `workflow_dispatch`). Tutte le variabili d'ambiente vengono passate come GitHub Secrets.

## Logica principale

- 75% dei giorni: quiz generico su informatica/programmazione
- 25% dei giorni: quiz basato su un episodio casuale del feed RSS (trascrizione + script GitHub se disponibile)
- Se il gruppo di riferimento ha avuto attività nella finestra configurata (default 240 minuti), il quiz viene saltato (`exit 0`)
