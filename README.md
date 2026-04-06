<div align="center">
  <img src="https://cdn.pensieriincodice.it/images/pensieriincodice-locandina.png" alt="Logo Progetto" width="150"/>
  <h1>Pensieri In Codice — Quiz Generator</h1>
  <p>Pubblica automaticamente un quiz giornaliero nel canale Telegram del podcast, generato da Claude AI a partire dagli episodi.</p>
  <p>
    <img src="https://img.shields.io/github/stars/valeriogalano/botcaster-quiz-generator?style=for-the-badge" alt="GitHub Stars"/>
    <img src="https://img.shields.io/github/forks/valeriogalano/botcaster-quiz-generator?style=for-the-badge" alt="GitHub Forks"/>
    <img src="https://img.shields.io/github/last-commit/valeriogalano/botcaster-quiz-generator?style=for-the-badge" alt="Last Commit"/>
    <img src="https://img.shields.io/github/actions/workflow/status/valeriogalano/botcaster-quiz-generator/quiz_publish.yml?style=for-the-badge&label=daily%20quiz" alt="GitHub Actions Status"/>
    <a href="https://pensieriincodice.it/sostieni" target="_blank" rel="noopener noreferrer">
      <img src="https://img.shields.io/badge/sostieni-Pensieri_in_codice-fb6400?style=for-the-badge" alt="Sostieni Pensieri in codice"/>
    </a>
  </p>
</div>

---

## Come funziona

Ad ogni esecuzione lo script:

1. Verifica che ci sia stata attività recente nel gruppo Telegram di riferimento (configurabile). Se non ci sono messaggi nelle ultime 6 ore, il quiz viene saltato.
2. Scarica il feed RSS del podcast e seleziona un episodio casuale.
3. Decide il tipo di quiz:
   - **75% delle volte** genera un quiz generico su un tema tech scelto casualmente tra oltre 30 categorie: linguaggi di programmazione (Python, JavaScript, Go, Rust, Java, PHP…), reti, sicurezza, database, Docker, Git, LLM, privacy, storia dell'informatica e altro.
   - **25% delle volte** tenta di generare un quiz basato sull'episodio selezionato, estraendo la trascrizione dal feed RSS e cercando il file script corrispondente nel repo GitHub. Se il contenuto non è disponibile, ricade sul quiz generico.
4. Chiama l'API Anthropic (Claude Haiku) con il contenuto scelto e riceve un quiz in formato JSON con domanda, 4 opzioni, risposta corretta e spiegazione.
5. Pubblica il quiz nel canale Telegram come **poll nativo di tipo quiz**, con la spiegazione visibile dopo aver risposto e apertura di 24 ore.

---

## Requisiti

- Python 3.11+
- Un bot Telegram (creabile tramite [@BotFather](https://t.me/botfather))
- Una chiave API Anthropic

---

## Configurazione

### 1. Variabili d'ambiente / `.env`

Copia `.env.example` in `.env` e compila i valori. In GitHub Actions le stesse variabili vanno aggiunte come **Secrets** in **Settings → Secrets and variables → Actions**.

| Variabile | Obbligatoria | Descrizione |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✓ | Chiave API di Anthropic |
| `TELEGRAM_BOT_TOKEN` | ✓ | Token del bot Telegram |
| `TELEGRAM_CHAT_ID` | ✓ | Chat ID o username del canale/gruppo dove pubblicare il quiz |
| `FEED_RSS_URL` | ✓ | URL del feed RSS del podcast |
| `GITHUB_REPO` | ✓ | Repo GitHub degli script (es. `utente/repo`) |
| `GITHUB_SCRIPTS_PATH` | ✓ | Cartella degli script nel repo (es. `scripts/`) |
| `SCRIPT_EXTENSION` | ✓ | Estensioni dei file script separate da virgola (es. `.json,.yml`) |
| `TELEGRAM_ACTIVITY_CHAT_ID` |  | Gruppo da monitorare per l'attività (default: `TELEGRAM_CHAT_ID`) |

---

## Installazione e avvio locale

```bash
pip install anthropic feedparser requests python-dotenv
```

Copia il file `.env.example` in `.env` e compila i valori:

```bash
cp .env.example .env
```

Poi esegui direttamente:

```bash
python quiz_bot.py
```

---

## Topic dei quiz generici

Il tema viene scelto casualmente a ogni esecuzione tra questi 29 argomenti:

| Categoria | Dettaglio |
|---|---|
| Storia dell'informatica | personaggi, invenzioni, aneddoti |
| Reti e protocolli | HTTP, DNS, TCP/IP, TLS, WebSocket |
| Sicurezza informatica | vulnerabilità comuni, crittografia, attacchi noti |
| Sistemi operativi | processi, file system, permessi, shell |
| Git | comandi, workflow, conflitti |
| Docker | immagini, volumi, networking |
| Database SQL | query, JOIN, indici, transazioni |
| Database NoSQL | Redis, MongoDB, casi d'uso |
| SQL avanzato | window function, CTE, explain, ottimizzazione query |
| API REST | metodi HTTP, status code, autenticazione |
| LLM e AI generativa | token, prompt, RAG, fine-tuning, limitazioni |
| Cloud e infrastruttura | DNS, CDN, load balancer, serverless |
| Algoritmi e strutture dati | stack, queue, hash map, complessità |
| Web e browser | cookie, localStorage, CORS, rendering |
| Privacy e GDPR | dati personali, consenso, diritti dell'utente |
| Open source | licenze, community, modello di sviluppo |
| Terminale e scripting | bash, pipe, redirect, variabili d'ambiente |
| Debugging e testing | unit test, stack trace, TDD |
| Python | comportamenti inattesi, decoratori, GIL, gestione memoria |
| JavaScript | event loop, closure, Promise, hoisting, this |
| TypeScript | tipi, interfacce, generici, narrowing |
| Go | goroutine, channel, defer, garbage collector |
| Rust | ownership, borrow checker, lifetimes, sicurezza della memoria |
| Java | JVM, garbage collection, interfacce, generici |
| C | puntatori, gestione manuale della memoria, undefined behavior |
| PHP | storia, evoluzione, usi moderni, differenze con altri linguaggi |
| Ruby | filosofia del linguaggio, convenzioni, Rails |
| Kotlin | null safety, coroutine, interoperabilità con Java |
| Swift | optionals, protocolli, ARC, differenze con Objective-C |

---

## Prompt Claude

### Quiz generico

```
Sei un assistente che genera quiz in italiano per un canale Telegram di un podcast di informatica.

Genera UN SOLO quiz sul tema specificato dall'utente.
Il quiz deve essere accessibile a un pubblico appassionato di tech ma non necessariamente sviluppatore.
Stimola la curiosità, evita algoritmi avanzati.
Preferisci domande su comportamenti inattesi, curiosità, errori comuni o concetti fondamentali.

[schema JSON]
```

### Quiz da episodio

```
Sei un assistente che genera quiz in italiano per un canale Telegram di un podcast di informatica.

Genera UN SOLO quiz dal contenuto fornito. Scegli casualmente tra:

TIPOLOGIA A — Argomento del podcast: concetto, opinione, fatto o tema dell'episodio.
Adatta a un pubblico appassionato ma non sviluppatore professionista.

TIPOLOGIA B — Programmazione/tech: snippet da interpretare, completamento di codice,
LLM/AI, linguaggi o framework. Accessibile: stimola la curiosità, non la competenza specializzata.

[schema JSON]
```

### Schema JSON richiesto

```json
{
  "question": "testo della domanda (max 300 caratteri)",
  "description": "snippet di codice o contesto in monospace (max 200 caratteri, opzionale)",
  "options": ["opzione A", "opzione B", "opzione C", "opzione D"],
  "correct_option_ids": [0],
  "explanation": "spiegazione breve della risposta corretta (max 200 caratteri)"
}
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
