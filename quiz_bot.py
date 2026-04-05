import json
import os
import random
import sys

import anthropic
import feedparser
import requests

# ── Configurazione ────────────────────────────────────────────────────────────
FEED_RSS_URL = "FEED_RSS_URL"
GITHUB_REPO = "GITHUB_REPO"            # es. "utente/repo"
GITHUB_SCRIPTS_PATH = "GITHUB_SCRIPTS_PATH"  # es. "scripts/" o "."
SCRIPT_EXTENSION = "SCRIPT_EXTENSION"  # es. ".md" o ".txt"
TELEGRAM_CHAT_ID = "TELEGRAM_CHAT_ID"

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
# ─────────────────────────────────────────────────────────────────────────────


def fetch_random_episode(feed_url: str) -> dict:
    feed = feedparser.parse(feed_url)
    if not feed.entries:
        print("Errore: nessun episodio trovato nel feed RSS.", file=sys.stderr)
        sys.exit(1)
    episode = random.choice(feed.entries)
    return episode


def extract_transcript(episode: dict) -> str:
    # Prova content → summary → itunes_transcript
    if hasattr(episode, "content") and episode.content:
        return episode.content[0].get("value", "")
    if episode.get("summary"):
        return episode["summary"]
    if episode.get("itunes_transcript"):
        return episode["itunes_transcript"]
    return ""


def fetch_github_script(title: str) -> str:
    """Cerca nel repo GitHub un file il cui nome contenga parole chiave del titolo."""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_SCRIPTS_PATH}"
    try:
        resp = requests.get(api_url, timeout=10)
        resp.raise_for_status()
        files = resp.json()
    except Exception as e:
        print(f"Avviso: impossibile accedere al repo GitHub ({e}).", file=sys.stderr)
        return ""

    keywords = [w.lower() for w in title.split() if len(w) > 3]
    best_match = None
    best_score = 0

    for item in files:
        if not item.get("name", "").endswith(SCRIPT_EXTENSION):
            continue
        name_lower = item["name"].lower()
        score = sum(1 for kw in keywords if kw in name_lower)
        if score > best_score:
            best_score = score
            best_match = item

    if not best_match or best_score == 0:
        return ""

    try:
        file_resp = requests.get(best_match["download_url"], timeout=10)
        file_resp.raise_for_status()
        return file_resp.text
    except Exception as e:
        print(f"Avviso: impossibile scaricare il file script ({e}).", file=sys.stderr)
        return ""


def generate_quiz(title: str, transcript: str, script: str) -> dict:
    content_parts = []
    if transcript:
        content_parts.append(f"TRASCRIZIONE DELL'EPISODIO:\n{transcript[:4000]}")
    if script:
        content_parts.append(f"SCALETTA/SCRIPT DELL'EPISODIO:\n{script[:2000]}")
    content = "\n\n".join(content_parts) if content_parts else f"Titolo episodio: {title}"

    system_prompt = """Sei un assistente che genera quiz in italiano per un canale Telegram legato a un podcast di informatica e tecnologia.

Devi generare UN SOLO quiz basato sul contenuto fornito. Scegli casualmente UNA delle due seguenti tipologie:

TIPOLOGIA A — Argomento del podcast:
Domanda su un concetto, un'opinione, un fatto o un tema trattato nell'episodio. Non necessariamente tecnica. Adatta a un pubblico generalista appassionato di informatica, curioso ma non sviluppatore professionista.

TIPOLOGIA B — Quiz di programmazione/tech:
Scegli casualmente tra:
- Un piccolo snippet di codice da interpretare o il cui output va indovinato
- Completamento di codice (quale riga manca?)
- Domanda sul funzionamento di un LLM o framework AI open source
- Domanda su caratteristiche di un linguaggio di programmazione o framework

Anche la tipologia B deve essere accessibile: niente algoritmi avanzati, preferire domande che stimolino curiosità più che competenza tecnica specializzata.

Rispondi SOLO con un JSON valido, senza backtick, senza testo aggiuntivo, con questa struttura:
{
  "question": "testo della domanda (max 300 caratteri)",
  "description": "snippet di codice o contesto rilevante in monospace (max 200 caratteri, opzionale, ometti se non necessario)",
  "options": ["opzione A", "opzione B", "opzione C", "opzione D"],
  "correct_option_ids": [0],
  "explanation": "spiegazione breve della risposta corretta (max 200 caratteri)"
}

Dove correct_option_ids è una lista di indici 0-based delle opzioni corrette.
Fai domande concrete e specifiche, non generiche."""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"Titolo episodio: {title}\n\n{content}",
            }
        ],
    )

    raw = message.content[0].text.strip()
    try:
        quiz = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Errore: risposta di Claude non è un JSON valido.\nRisposta: {raw}\nErrore: {e}", file=sys.stderr)
        sys.exit(1)

    return quiz


def send_message(text: str, parse_mode: str = "Markdown") -> dict:
    resp = requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def send_poll(quiz: dict) -> dict:
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "question": quiz["question"],
        "options": quiz["options"],
        "type": "quiz",
        "correct_option_id": quiz["correct_option_ids"][0],
        "explanation": quiz.get("explanation", ""),
        "shuffle_options": True,
        "is_anonymous": True,
        "open_period": 86400,
    }
    if quiz.get("description"):
        payload["question"] = f"{quiz['question']}\n\n{quiz['description']}"

    resp = requests.post(f"{TELEGRAM_API}/sendPoll", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def send_disclaimer(reply_to_message_id: int) -> None:
    resp = requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": "🤖 Quiz generato da Claude AI — le risposte potrebbero contenere errori. Verifica sempre dalle fonti originali.",
            "reply_to_message_id": reply_to_message_id,
        },
        timeout=10,
    )
    resp.raise_for_status()


def main() -> None:
    print("Scarico il feed RSS...")
    episode = fetch_random_episode(FEED_RSS_URL)
    title = episode.get("title", "Episodio senza titolo")
    print(f"Episodio selezionato: {title}")

    print("Estraggo la trascrizione...")
    transcript = extract_transcript(episode)

    print("Cerco lo script nel repo GitHub...")
    script = fetch_github_script(title)
    if script:
        print("Script trovato nel repo.")
    else:
        print("Script non trovato, uso solo la trascrizione.")

    if not transcript and not script:
        print("Errore: nessun contenuto disponibile per generare il quiz.", file=sys.stderr)
        sys.exit(1)

    print("Genero il quiz con Claude...")
    quiz = generate_quiz(title, transcript, script)

    print("Invio il messaggio con il titolo dell'episodio...")
    send_message(f"🎙️ Quiz dall'episodio: *{title}*")

    print("Invio il poll su Telegram...")
    poll_response = send_poll(quiz)
    poll_message_id = poll_response["result"]["message_id"]

    print("Invio il disclaimer...")
    send_disclaimer(poll_message_id)

    print("Quiz pubblicato con successo!")


if __name__ == "__main__":
    main()
