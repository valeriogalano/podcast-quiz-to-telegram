import datetime
import json
import os
import random
import sys

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
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_SCRIPTS_PATH = os.environ.get("GITHUB_SCRIPTS_PATH", "")
SCRIPT_EXTENSIONS = tuple(
    ext.strip() for ext in os.environ.get("SCRIPT_EXTENSION", ".md").split(",")
)
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
# ─────────────────────────────────────────────────────────────────────────────

_JSON_SCHEMA = """\
Rispondi SOLO con un JSON valido, senza backtick, senza testo aggiuntivo:
{
  "question": "testo della domanda (max 300 caratteri)",
  "description": "snippet di codice o contesto in monospace (max 200 caratteri, ometti se non necessario)",
  "options": ["opzione A", "opzione B", "opzione C", "opzione D"],
  "correct_option_ids": [0],
  "explanation": "spiegazione breve della risposta corretta (max 200 caratteri)"
}
correct_option_ids è una lista di indici 0-based. Domande concrete e specifiche, non generiche."""

_EPISODE_SYSTEM = """\
Sei un assistente che genera quiz in italiano per un canale Telegram di un podcast di informatica.

Genera UN SOLO quiz dal contenuto fornito. Scegli casualmente tra:

TIPOLOGIA A — Argomento del podcast: concetto, opinione, fatto o tema dell'episodio. Adatta a un pubblico appassionato ma non sviluppatore professionista.

TIPOLOGIA B — Programmazione/tech: snippet da interpretare, completamento di codice, LLM/AI, linguaggi o framework. Accessibile: stimola la curiosità, non la competenza specializzata.

""" + _JSON_SCHEMA

_GENERIC_SYSTEM = """\
Sei un assistente che genera quiz in italiano per un canale Telegram di un podcast di informatica.

Genera UN SOLO quiz su informatica/programmazione. Scegli casualmente tra:
- Best practice Python, OOP, funzioni, tipi, scope
- Docker, Git, REST API, database SQL/NoSQL
- LLM, AI generativa, framework open source
- Snippet Python da interpretare
- Curiosità tecnologiche accessibili

Stimola la curiosità, evita algoritmi avanzati.

""" + _JSON_SCHEMA


def fetch_random_episode() -> dict:
    feed = feedparser.parse(FEED_RSS_URL)
    if not feed.entries:
        print("Errore: nessun episodio trovato nel feed RSS.", file=sys.stderr)
        sys.exit(1)
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

    keywords = [w.lower() for w in title.split() if len(w) > 3]
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


def main() -> None:
    print("Scarico il feed RSS...")
    episode = fetch_random_episode()
    title = episode.get("title", "Episodio senza titolo")
    print(f"Episodio selezionato: {title}")

    episode_ref = None
    if random.random() < 0.25:
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
            quiz = call_claude(_EPISODE_SYSTEM, f"Titolo: {title}\n\n{content}")
            episode_ref = title
        else:
            print("Nessun contenuto episodio disponibile, passo al quiz generico...")

    if episode_ref is None:
        print("Genero un quiz generico...")
        quiz = call_claude(_GENERIC_SYSTEM, "Genera un quiz su informatica o programmazione.")

    print("Invio il poll su Telegram...")
    poll_message_id = send_poll(quiz)["result"]["message_id"]

    print(
        f"[{datetime.datetime.utcnow().isoformat()}Z] "
        f"type={'episodio' if episode_ref else 'generico'} "
        f"episode={episode_ref!r} poll_id={poll_message_id} status=success"
    )
    print("Quiz pubblicato con successo!")


if __name__ == "__main__":
    main()
