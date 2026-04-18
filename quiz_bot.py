import datetime
import json
import os
import re
import random
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import anthropic
import feedparser
import requests

# ── Configurazione ────────────────────────────────────────────────────────────
FEED_RSS_URL = os.environ.get("FEED_RSS_URL", "")
GITHUB_REPO = os.environ.get("GH_REPO", "")
GITHUB_SCRIPTS_PATH = os.environ.get("GH_SCRIPTS_PATH", "")
SCRIPT_EXTENSIONS = tuple(
    ext.strip() for ext in os.environ.get("SCRIPT_EXTENSION", ".md").split(",")
)
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TELEGRAM_ACTIVITY_CHAT_ID = os.environ.get("TELEGRAM_ACTIVITY_CHAT_ID", TELEGRAM_CHAT_ID)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
# ─────────────────────────────────────────────────────────────────────────────

_JSON_SCHEMA = """\
Rispondi SOLO con un JSON valido, senza backtick, senza testo aggiuntivo:
{
  "question": "testo della domanda (max 300 caratteri)",
  "description": "snippet di codice o contesto in monospace (max 200 caratteri, ometti se non necessario)",
  "options": ["opzione A", "opzione B", "opzione C"],
  "correct_option_ids": [0],
  "explanation": "spiegazione breve della risposta corretta (max 200 caratteri)"
}
correct_option_ids è una lista di indici 0-based. Il numero di opzioni deve essere tra 2 e 6, scegli quello più adatto alla domanda. Domande concrete e specifiche, non generiche."""

_GENERIC_TOPICS = [
    "storia dell'informatica: personaggi, invenzioni, aneddoti",
    "reti e protocolli: HTTP, DNS, TCP/IP, TLS, WebSocket",
    "sicurezza informatica: vulnerabilità comuni, crittografia, attacchi noti",
    "sistemi operativi: processi, file system, permessi, shell",
    "Git e controllo versione: comandi, workflow, conflitti",
    "Docker e containerizzazione: immagini, volumi, networking",
    "database SQL: query, JOIN, indici, transazioni",
    "database NoSQL: Redis, MongoDB, casi d'uso",
    "API REST: metodi HTTP, status code, autenticazione",
    "LLM e AI generativa: token, prompt, RAG, fine-tuning, limitazioni",
    "cloud e infrastruttura: DNS, CDN, load balancer, serverless",
    "algoritmi e strutture dati di base: stack, queue, hash map, complessità",
    "web e browser: cookie, localStorage, CORS, rendering",
    "privacy e GDPR: dati personali, consenso, diritti dell'utente",
    "open source: licenze, community, modello di sviluppo",
    "terminale e scripting: bash, pipe, redirect, variabili d'ambiente",
    "debugging e testing: unit test, stack trace, TDD",
    "Python: comportamenti inattesi, decoratori, GIL, gestione memoria",
    "JavaScript: event loop, closure, Promise, hoisting, this",
    "TypeScript: tipi, interfacce, generici, narrowing",
    "Go: goroutine, channel, defer, garbage collector",
    "Rust: ownership, borrow checker, lifetimes, sicurezza della memoria",
    "Java: JVM, garbage collection, interfacce, generici",
    "C: puntatori, gestione manuale della memoria, undefined behavior",
    "SQL avanzato: window function, CTE, explain, ottimizzazione query",
    "PHP: storia, evoluzione, usi moderni, differenze con altri linguaggi",
    "Ruby: filosofia del linguaggio, convenzioni, Rails",
    "Kotlin: null safety, coroutine, interoperabilità con Java",
    "Swift: optionals, protocolli, ARC, differenze con Objective-C",
]

_EPISODE_SYSTEM = """\
Sei un assistente che genera quiz in italiano per un canale Telegram di un podcast di informatica.

Genera UN SOLO quiz dal contenuto fornito. Scegli casualmente tra:

TIPOLOGIA A — Argomento del podcast: concetto, opinione, fatto o tema dell'episodio. Adatta a un pubblico appassionato ma non sviluppatore professionista.

TIPOLOGIA B — Programmazione/tech: snippet da interpretare, completamento di codice, LLM/AI, linguaggi o framework. Accessibile: stimola la curiosità, non la competenza specializzata.

""" + _JSON_SCHEMA

_GENERIC_SYSTEM = """\
Sei un assistente che genera quiz in italiano per un canale Telegram di un podcast di informatica.

Genera UN SOLO quiz sul tema specificato dall'utente. \
Il quiz deve essere accessibile a un pubblico appassionato di tech ma non necessariamente sviluppatore. \
Stimola la curiosità, evita algoritmi avanzati. \
Preferisci domande su comportamenti inattesi, curiosità, errori comuni o concetti fondamentali.

""" + _JSON_SCHEMA


def has_recent_activity(minutes: float | None = None) -> bool:
    """Ritorna True se c'è stata attività nel gruppo di riferimento negli ultimi `minutes` minuti.

    Usa `getUpdates` con offset negativo: Telegram ritorna gli ultimi N update senza
    confermarli, così non vengono rimossi dalla coda e restano visibili alle run successive.
    """
    if minutes is None:
        minutes = float(os.environ.get("TELEGRAM_ACTIVITY_WINDOW_MINUTES", "240"))
    threshold = time.time() - minutes * 60
    activity_id = TELEGRAM_ACTIVITY_CHAT_ID.lstrip("@")
    try:
        resp = requests.get(
            f"{TELEGRAM_API}/getUpdates",
            params={"offset": -100, "limit": 100, "timeout": 0},
            timeout=10,
        )
        resp.raise_for_status()
        updates = resp.json().get("result", [])
        matched = 0
        last_ts: float | None = None
        for update in updates:
            msg = update.get("message") or update.get("channel_post")
            if not msg:
                continue
            chat = msg.get("chat", {})
            if str(chat.get("id")) == activity_id or chat.get("username") == activity_id:
                matched += 1
                ts = msg.get("date", 0)
                if last_ts is None or ts > last_ts:
                    last_ts = ts
        print(f"getUpdates: {len(updates)} update totali, {matched} per {activity_id}")
        if last_ts is not None:
            iso = datetime.datetime.fromtimestamp(last_ts, tz=datetime.timezone.utc).astimezone().isoformat()
            print(f"Ultimo messaggio rilevato alle: {iso}")
            return last_ts >= threshold
        return False
    except Exception as e:
        print(f"Avviso: impossibile verificare l'attività ({e}). Salto il quiz per sicurezza.", file=sys.stderr)
        return True


def fetch_random_episode() -> dict:
    feed = feedparser.parse(FEED_RSS_URL)
    if not feed.entries:
        raise RuntimeError("nessun episodio trovato nel feed RSS")
    return random.choice(feed.entries)


def extract_transcript(episode: dict) -> str:
    if hasattr(episode, "content") and episode.content:
        return episode.content[0].get("value", "")
    return episode.get("summary") or episode.get("itunes_transcript") or ""


def fetch_github_script(title: str) -> str:
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_SCRIPTS_PATH}",
            timeout=10,
        )
        resp.raise_for_status()
        files = resp.json()
    except Exception as e:
        print(f"Avviso: impossibile accedere al repo GitHub ({e}).", file=sys.stderr)
        return ""

    keywords = re.findall(r"\b\w{4,}\b", title.lower())
    best_match, best_score = None, 0
    for item in files:
        if not item.get("name", "").endswith(SCRIPT_EXTENSIONS):
            continue
        score = sum(1 for kw in keywords if kw in item["name"].lower())
        if score > best_score:
            best_score, best_match = score, item

    if not best_match:
        return ""

    try:
        resp = requests.get(best_match["download_url"], timeout=10)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"Avviso: impossibile scaricare il file script ({e}).", file=sys.stderr)
        return ""


def call_claude(system: str, user: str) -> dict:
    message = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY).messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Errore: risposta di Claude non è un JSON valido.\n{raw}\n{e}", file=sys.stderr)
        sys.exit(1)


def send_poll(quiz: dict) -> dict:
    question = quiz["question"]
    if quiz.get("description"):
        question = f"{question}\n\n{quiz['description']}"
    resp = requests.post(
        f"{TELEGRAM_API}/sendPoll",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "question": question,
            "options": quiz["options"],
            "type": "quiz",
            "correct_option_id": quiz["correct_option_ids"][0],
            "explanation": quiz.get("explanation", ""),
            "shuffle_options": True,
            "is_anonymous": True,
            "open_period": 86400,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def generate_quiz_content() -> tuple[dict, str | None]:
    """Genera il quiz e ritorna (quiz, episode_ref)."""
    if FEED_RSS_URL and random.random() < 0.25:
        try:
            episode = fetch_random_episode()
        except RuntimeError as e:
            print(f"Avviso: impossibile usare il feed RSS ({e}). Passo al quiz generico.", file=sys.stderr)
            episode = None
        if episode is not None:
            title = episode.get("title", "Episodio senza titolo")
            print(f"Episodio selezionato: {title}")
            print("Estraggo la trascrizione...")
            transcript = extract_transcript(episode)
            print("Cerco lo script nel repo GitHub...")
            script = fetch_github_script(title)
            if transcript or script:
                content = "\n\n".join(filter(None, [
                    f"TRASCRIZIONE:\n{transcript[:4000]}" if transcript else "",
                    f"SCRIPT:\n{script[:2000]}" if script else "",
                ]))
                print("Genero il quiz basato sull'episodio...")
                return call_claude(_EPISODE_SYSTEM, f"Titolo: {title}\n\n{content}"), title
            print("Nessun contenuto episodio disponibile, passo al quiz generico...")

    topic = random.choice(_GENERIC_TOPICS)
    print(f"Genero un quiz generico (tema: {topic})...")
    return call_claude(_GENERIC_SYSTEM, f"Genera un quiz sul tema: {topic}"), None


def validate_quiz(quiz: dict) -> list[str]:
    """Controlla i limiti Telegram. Ritorna lista di errori, vuota se valido."""
    errors = []
    question = quiz.get("question", "")
    description = quiz.get("description", "")
    full_question = f"{question}\n\n{description}" if description else question
    if len(full_question) > 300:
        errors.append(f"question+description troppo lunga: {len(full_question)}/300 caratteri")
    for i, opt in enumerate(quiz.get("options", [])):
        if len(opt) > 100:
            errors.append(f"opzione {i} troppo lunga: {len(opt)}/100 caratteri")
    explanation = quiz.get("explanation", "")
    if len(explanation) > 200:
        errors.append(f"explanation troppo lunga: {len(explanation)}/200 caratteri")
    return errors


_MAX_QUIZ_RETRIES = 3


def generate_valid_quiz() -> tuple[dict, str | None]:
    """Genera un quiz valido rispetto ai limiti Telegram, con al massimo 3 tentativi."""
    for attempt in range(1, _MAX_QUIZ_RETRIES + 1):
        quiz, episode_ref = generate_quiz_content()
        print_quiz(quiz, episode_ref)
        errors = validate_quiz(quiz)
        if not errors:
            return quiz, episode_ref
        print(
            f"Quiz non valido (tentativo {attempt}/{_MAX_QUIZ_RETRIES}): {'; '.join(errors)}",
            file=sys.stderr,
        )
        if attempt < _MAX_QUIZ_RETRIES:
            print("Rigenero il quiz...")
    print(
        f"Errore: impossibile generare un quiz valido dopo {_MAX_QUIZ_RETRIES} tentativi.",
        file=sys.stderr,
    )
    sys.exit(1)


def print_quiz(quiz: dict, episode_ref: str | None, index: int | None = None) -> None:
    prefix = f"[{index}] " if index is not None else ""
    tipo = f"episodio ({episode_ref})" if episode_ref else "generico"
    print(f"\n{'─'*60}")
    print(f"{prefix}{tipo}")
    print(f"Q: {quiz['question']}")
    if quiz.get("description"):
        print(f"   {quiz['description']}")
    for i, opt in enumerate(quiz["options"]):
        mark = "✓" if i in quiz["correct_option_ids"] else " "
        print(f"  [{mark}] {opt}")
    print(f"💡 {quiz.get('explanation', '')}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Botcaster Quiz Generator")
    parser.add_argument("--dry-run", metavar="N", type=int, nargs="?", const=1,
                        help="Genera N quiz (default 1) senza inviarli su Telegram")
    args = parser.parse_args()

    if args.dry_run is not None:
        print("Scarico il feed RSS...")
        for i in range(1, args.dry_run + 1):
            quiz, episode_ref = generate_quiz_content()
            print_quiz(quiz, episode_ref, index=i if args.dry_run > 1 else None)
        return

    print(f"Verifico attività recente in {TELEGRAM_ACTIVITY_CHAT_ID}...")
    if has_recent_activity():
        print(f"Attività recente rilevata in {TELEGRAM_ACTIVITY_CHAT_ID}. Quiz saltato per non interrompere la conversazione.")
        sys.exit(0)

    print("Scarico il feed RSS...")
    quiz, episode_ref = generate_valid_quiz()

    print("Invio il poll su Telegram...")
    poll_message_id = send_poll(quiz)["result"]["message_id"]

    correct = quiz["options"][quiz["correct_option_ids"][0]]
    print(
        f"[{datetime.datetime.now(datetime.timezone.utc).isoformat()}] "
        f"type={'episodio' if episode_ref else 'generico'} "
        f"episode={episode_ref!r} poll_id={poll_message_id} status=success\n"
        f"  Q: {quiz['question']}\n"
        f"  A: {correct}\n"
        f"  💡 {quiz.get('explanation', '')}"
    )
    print("Quiz pubblicato con successo!")


if __name__ == "__main__":
    main()
