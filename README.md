<div align="center">
  <img src="https://cdn.pensieriincodice.it/images/pensieriincodice-locandina.png" alt="Logo Progetto" width="150"/>
  <h1>Pensieri In Codice — Quiz Generator</h1>
  <p>Pubblica automaticamente un quiz giornaliero nel canale Telegram del podcast, generato da Claude AI a partire dagli episodi.</p>
  <p>
    <img src="https://img.shields.io/github/stars/valeriogalano/botcaster-quiz-generator?style=for-the-badge" alt="GitHub Stars"/>
    <img src="https://img.shields.io/github/forks/valeriogalano/botcaster-quiz-generator?style=for-the-badge" alt="GitHub Forks"/>
    <img src="https://img.shields.io/github/last-commit/valeriogalano/botcaster-quiz-generator?style=for-the-badge" alt="Last Commit"/>
    <img src="https://img.shields.io/github/actions/workflow/status/valeriogalano/botcaster-quiz-generator/quiz.yml?style=for-the-badge&label=daily%20quiz" alt="GitHub Actions Status"/>
    <a href="https://pensieriincodice.it/sostieni" target="_blank" rel="noopener noreferrer">
      <img src="https://img.shields.io/badge/sostieni-Pensieri_in_codice-fb6400?style=for-the-badge" alt="Sostieni Pensieri in codice"/>
    </a>
  </p>
</div>

---

## Come funziona

Lo script scarica il feed RSS del podcast, seleziona un episodio casuale ed estrae la trascrizione disponibile. Prova poi a recuperare il file script dell'episodio dal repo GitHub corrispondente. Con il contenuto raccolto chiama l'API di Anthropic (Claude Haiku) per generare un quiz in italiano, scegliendo casualmente tra domande sull'argomento dell'episodio e quiz di programmazione/tech. Il quiz viene quindi pubblicato nel canale Telegram come poll nativo, con spiegazione della risposta corretta e un disclaimer di trasparenza.

---

## Requisiti

- Python 3.11+
- Un bot Telegram (creabile tramite [@BotFather](https://t.me/botfather))
- Una chiave API Anthropic

---

## Configurazione

### 1. Variabili nello script

Apri `quiz_bot.py` e sostituisci i segnaposto nella sezione **Configurazione** in cima al file:

| Variabile | Descrizione |
|---|---|
| `FEED_RSS_URL` | URL del feed RSS del podcast |
| `GITHUB_REPO` | Repo GitHub degli script (es. `utente/repo`) |
| `GITHUB_SCRIPTS_PATH` | Cartella degli script nel repo (es. `scripts/` o `.`) |
| `SCRIPT_EXTENSION` | Estensione dei file script (es. `.md` o `.txt`) |
| `TELEGRAM_CHAT_ID` | Chat ID o username del canale/gruppo Telegram |

### 2. Segreti GitHub Actions

Nel repository GitHub, vai su **Settings → Secrets and variables → Actions** e aggiungi:

| Segreto | Descrizione |
|---|---|
| `ANTHROPIC_API_KEY` | Chiave API di Anthropic |
| `TELEGRAM_BOT_TOKEN` | Token del bot Telegram |

---

## Installazione e avvio locale

```bash
pip install anthropic feedparser requests
python quiz_bot.py
```

Per testare in locale, imposta le variabili d'ambiente prima di eseguire lo script:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export TELEGRAM_BOT_TOKEN="123456:ABC-..."
python quiz_bot.py
```

Su Windows (PowerShell):

```powershell
$env:ANTHROPIC_API_KEY="sk-ant-..."
$env:TELEGRAM_BOT_TOKEN="123456:ABC-..."
python quiz_bot.py
```

---

## Trasparenza

I quiz pubblicati nel canale sono **generati automaticamente da Claude AI** (Anthropic) sulla base delle trascrizioni e degli script degli episodi. Nonostante le istruzioni mirate, le risposte potrebbero contenere imprecisioni o errori. Per qualsiasi dubbio, fai sempre riferimento alle fonti originali degli episodi.

---

## Contributi

Se noti qualche problema o hai suggerimenti, sentiti libero di aprire una **Issue** e successivamente una **Pull Request**. Ogni contributo è ben accetto!

---

## Importante

Vorremmo mantenere questo repository aperto e gratuito per tutti, ma lo scraping del contenuto di questo repository **NON È CONSENTITO**. Se ritieni che questo lavoro ti sia utile e vuoi utilizzare qualche risorsa, ti preghiamo di citare come fonte il podcast e/o questo repository.

---

<div align="center">
  <p>Realizzato con ❤️ da <strong>Valerio Galano</strong></p>
  <p>
    <a href="https://valeriogalano.it/">Sito Web</a> |
    <a href="https://daredevel.com/">Blog</a> |
    <a href="https://pensieriincodice.it/">Podcast</a>
  </p>
</div>
