import datetime
import html
import json
import os
import re
import random
import sys
from html.parser import HTMLParser

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import anthropic
from google import genai
from google.genai import types as genai_types
import feedparser
import requests

# ── Configurazione ────────────────────────────────────────────────────────────
# Su Actions una `vars.X` non definita arriva come stringa vuota, non come
# variabile assente: `or` fa valere il default anche in quel caso.
FEED_RSS_URL = os.environ.get("FEED_RSS_URL") or ""
GITHUB_REPO = os.environ.get("GH_REPO") or ""
GITHUB_SCRIPTS_PATH = os.environ.get("GH_SCRIPTS_PATH") or ""


def _script_extensions(raw: str | None) -> tuple[str, ...]:
    # un'estensione vuota renderebbe compatibile qualunque file ("x".endswith(""))
    extensions = tuple(ext.strip() for ext in (raw or "").split(",") if ext.strip())
    return extensions or (".md",)


SCRIPT_EXTENSIONS = _script_extensions(os.environ.get("SCRIPT_EXTENSION"))
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
QUIZ_PROVIDER = (os.environ.get("QUIZ_PROVIDER") or "google").lower()
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Identificatori dei modelli AI usati per generare i quiz. Vengono propagati in
# `quiz["model"]` e mostrati nella `description` del poll su Telegram per
# trasparenza verso il pubblico del canale.
# Cfr. https://docs.anthropic.com/en/docs/about-claude/models/overview
# e https://ai.google.dev/gemini-api/docs/models.
_CLAUDE_MODEL = "claude-sonnet-5-5"
_GEMINI_MODEL = "gemini-3.8-flash"

# Limiti dell'API Telegram Bot per i poll di tipo quiz.
# Cfr. https://core.telegram.org/bots/api#sendpoll
_TELEGRAM_QUESTION_MAX = 300
_TELEGRAM_DESCRIPTION_MAX = 200
_TELEGRAM_OPTION_MAX = 100
_TELEGRAM_EXPLANATION_MAX = 200
_TELEGRAM_EXPLANATION_MAX_NEWLINES = 2
# Il prompt chiede fra 2 e 6 opzioni: Telegram ne ammette di più, ma un quiz
# fuori da questo range è un quiz che il modello non ha scritto come richiesto.
_MIN_OPTIONS = 2
_MAX_OPTIONS = 6
# ─────────────────────────────────────────────────────────────────────────────


class QuizProviderError(RuntimeError):
    """Errore recuperabile durante la generazione del quiz via provider AI."""


class TelegramError(RuntimeError):
    """Telegram ha rifiutato la richiesta. Il messaggio riporta stato e motivo,
    mai l'URL: contiene il token del bot, che finirebbe in chiaro nei log."""

    def __init__(self, status_code: int, description: str):
        super().__init__(f"Telegram ha rifiutato sendPoll: HTTP {status_code} — {description}")
        self.status_code = status_code
        self.description = description


def _raise_for_telegram(resp) -> None:
    """Al posto di resp.raise_for_status(), il cui messaggio contiene l'URL."""
    if resp.ok:
        return
    try:
        description = resp.json().get("description", "")
    except ValueError:
        description = (resp.text or "")[:200]
    raise TelegramError(resp.status_code, description)


_JSON_SCHEMA = """\
Rispondi SOLO con un JSON valido, senza backtick, senza testo aggiuntivo:
{
  "question": "testo della domanda (max 300 caratteri)",
  "description": "snippet di codice o contesto opzionale (max 140 caratteri: i restanti caratteri della description del poll Telegram sono riservati al footer di trasparenza sul modello)",
  "options": ["opzione A", "opzione B", "opzione C"],
  "correct_option_ids": [0],
  "explanation": "spiegazione MOLTO BREVE della risposta corretta — massimo assoluto 200 caratteri, idealmente 150. Conta ogni lettera, spazio e segno di punteggiatura. Una o due frasi essenziali."
}
correct_option_ids è una lista di indici 0-based delle risposte corrette: usa UN solo indice per quiz a risposta singola, oppure 2-3 indici per quiz a risposta multipla (in tal caso formula la domanda in modo che sia chiaro che più risposte sono corrette, es. "Quali di queste affermazioni sono vere?"). Il numero di opzioni deve essere tra 2 e 6, scegli quello più adatto alla domanda. Domande concrete e specifiche, non generiche. Ometti `description` se non è necessaria.

ATTENZIONE LIMITI: il sistema rifiuta il quiz se la `explanation` supera 200 caratteri, quindi sii sintetico. Meglio una spiegazione di 120 caratteri che chiara ma incompleta, piuttosto che 220 che debordi."""

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

# Voce di Engram, derivata a mano da agent-skills/engram (engram-identita.md +
# roles/quiz.md). La fonte di verità è la skill: se cambia lì, va rigenerato qui.
# Lo schema JSON e i limiti restano sotto, perché sono contratto tecnico di Telegram.
_ENGRAM_VOICE = """\
Sei Engram, l'assistente di Pensieri in codice, e scrivi un quiz per la community del podcast.

Il tono: italiano, dai del tu, frasi brevi, ironia asciutta. Niente entusiasmo, niente punti esclamativi, niente complimenti di rito ("Bravo!", "Incredibile!"), niente superlativi. Non presentarti e non dire di essere una IA.
Una domanda concreta e specifica, non una definizione da manuale. Gli errori nelle opzioni devono essere quelli che una persona ragionevole farebbe davvero. La spiegazione dice il perché, non ripete la risposta.
Non hai visto i quiz precedenti: nessun riferimento a quiz passati.
"""

_EPISODE_SYSTEM = _ENGRAM_VOICE + """

Genera UN SOLO quiz dal contenuto fornito. Scegli casualmente tra:

TIPOLOGIA A — Argomento del podcast: concetto, opinione, fatto o tema dell'episodio. Adatta a un pubblico appassionato ma non sviluppatore professionista.

TIPOLOGIA B — Programmazione/tech: snippet da interpretare, completamento di codice, LLM/AI, linguaggi o framework. Accessibile: stimola la curiosità, non la competenza specializzata.

""" + _JSON_SCHEMA

_GENERIC_SYSTEM = _ENGRAM_VOICE + """

Genera UN SOLO quiz sul tema specificato dall'utente. \
Il quiz deve essere accessibile a un pubblico appassionato di tech ma non necessariamente sviluppatore. \
Stimola la curiosità, evita algoritmi avanzati. \
Preferisci domande su comportamenti inattesi, curiosità, errori comuni o concetti fondamentali.

""" + _JSON_SCHEMA


def fetch_random_episode() -> dict:
    feed = feedparser.parse(FEED_RSS_URL)
    if not feed.entries:
        raise RuntimeError("nessun episodio trovato nel feed RSS")
    return random.choice(feed.entries)


class _TextExtractor(HTMLParser):
    _BLOCKS = {"p", "br", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "tr", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(value: str) -> str:
    """Le note degli episodi nel feed sono HTML: i tag consumerebbero parte dei
    caratteri mandati al modello. Resta il testo, con un a capo per blocco."""
    if "<" not in value:
        return html.unescape(value).strip()
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    text = "".join(parser.parts)
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def extract_transcript(episode: dict) -> str:
    if hasattr(episode, "content") and episode.content:
        return html_to_text(episode.content[0].get("value", ""))
    return html_to_text(episode.get("summary") or episode.get("itunes_transcript") or "")


# Parole che compaiono nei titoli di episodi diversi e non dicono nulla sul tema.
_STOPWORDS = {
    "della", "delle", "dello", "degli", "nella", "nelle", "nello", "negli", "dalla",
    "dalle", "alla", "alle", "sulla", "sulle", "come", "cosa", "sono", "anche", "quando",
    "perché", "perche", "questo", "questa", "quello", "quella", "episodio", "puntata",
}


def _episode_number(link: str) -> int | None:
    """Il sito pubblica gli episodi su /episodes/NNN-slug: NNN identifica lo script."""
    match = re.search(r"/episodes?/(\d+)", link or "")
    return int(match.group(1)) if match else None


def _pick_script(files: list[dict], title: str, link: str = "") -> dict | None:
    """Sceglie lo script dell'episodio, o nessuno.

    Prima per numero (gli script si chiamano PICNNN.yml); altrimenti per parole
    del titolo, ma solo se ne coincide più della metà e senza pareggi: con una
    parola in comune ("futuro") si sceglieva lo script di un altro episodio.
    """
    candidates = [f for f in files if f.get("name", "").endswith(SCRIPT_EXTENSIONS)]

    number = _episode_number(link)
    if number is not None:
        for item in candidates:
            digits = re.findall(r"\d+", item["name"])
            if digits and int(digits[0]) == number:
                return item

    keywords = [kw for kw in set(re.findall(r"\b\w{4,}\b", title.lower())) if kw not in _STOPWORDS]
    if not keywords:
        return None
    scored = sorted(
        ((sum(1 for kw in keywords if kw in item["name"].lower()), item) for item in candidates),
        key=lambda pair: pair[0], reverse=True,
    )
    if not scored or scored[0][0] * 2 <= len(keywords):
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]


def fetch_github_script(title: str, link: str = "") -> str:
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

    best_match = _pick_script(files, title, link)
    if not best_match:
        return ""

    try:
        resp = requests.get(best_match["download_url"], timeout=10)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"Avviso: impossibile scaricare il file script ({e}).", file=sys.stderr)
        return ""


def _parse_quiz_json(raw: str, model: str, provider_name: str) -> dict:
    """Testo del modello -> quiz: toglie un eventuale blocco ``` e annota il modello."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise QuizProviderError(f"risposta di {provider_name} non è un JSON valido: {e}\n{raw}") from e
    if not isinstance(result, dict):
        raise QuizProviderError(f"risposta di {provider_name} non è un oggetto JSON: {raw}")
    result["model"] = model
    return result


def call_claude(system: str, user: str) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=_CLAUDE_MODEL,
        # Il ragionamento del modello consuma lo stesso budget della risposta.
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    # Il modello può mettere in testa un blocco di ragionamento: conta solo il testo.
    raw = "".join(b.text for b in message.content if b.type == "text")
    return _parse_quiz_json(raw, _CLAUDE_MODEL, "Claude")


def get_quiz_providers() -> list[str]:
    providers = [item.strip().lower() for item in QUIZ_PROVIDER.split(",") if item.strip()]
    return providers or ["google"]


def call_ai(system: str, user: str, provider: str | None = None) -> dict:
    selected = (provider or get_quiz_providers()[0]).lower()
    if selected in {"anthropic", "claude"}:
        return call_claude(system, user)
    if selected in {"google", "gemini"}:
        return call_gemini(system, user)
    raise QuizProviderError(
        f"provider AI non supportato: {selected!r}. Usa google/gemini oppure anthropic/claude."
    )


def call_gemini(system: str, user: str) -> dict:
    client = genai.Client(api_key=GOOGLE_API_KEY)
    response = client.models.generate_content(
        model=_GEMINI_MODEL,
        config=genai_types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=4096,
        ),
        contents=user,
    )
    return _parse_quiz_json(response.text or "", _GEMINI_MODEL, "Gemini")


def build_poll_description(quiz: dict) -> str:
    """Costruisce il valore del campo `description` del poll Telegram.

    Combina (in ordine):
    - l'eventuale `description` del quiz (snippet di codice, contesto)
    - un footer di trasparenza che indica il modello AI usato per generarlo

    Ritorna stringa vuota se non c'è nulla da mostrare. Estratta come funzione
    per essere riusata da `validate_quiz` (così la convalida controlla la stessa
    stringa che verrà effettivamente inviata a Telegram).
    """
    parts: list[str] = []
    if quiz.get("description"):
        parts.append(quiz["description"])
    if quiz.get("model"):
        parts.append(f"Generato con {quiz['model']}")
    return "\n\n".join(parts)


def send_poll(quiz: dict, episode_ref: dict | None = None) -> dict:
    correct_ids = quiz["correct_option_ids"]
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "question": quiz["question"],
        "options": quiz["options"],
        "type": "quiz",
        # Bot API 9.0 (apr 2025): correct_option_id (sing.) è deprecato; ora
        # i quiz supportano più risposte corrette tramite correct_option_ids.
        "correct_option_ids": correct_ids,
        "explanation": quiz.get("explanation", ""),
        "shuffle_options": True,
        "is_anonymous": True,
        "open_period": 86400,
    }
    description = build_poll_description(quiz)
    if description:
        # Bot API 9.0: campo `description` nativo, separato dalla `question`,
        # con budget di 200 caratteri indipendente dai 300 della domanda.
        payload["description"] = description
    if len(correct_ids) > 1:
        # Bot API 9.0: i quiz multi-risposta richiedono allows_multiple_answers.
        payload["allows_multiple_answers"] = True
    link = (episode_ref or {}).get("link") or ""
    if link.startswith(("http://", "https://")):
        # Il link all'episodio va in un pulsante URL sotto il poll: i poll non
        # rendono link cliccabili, e il pulsante non richiede un backend che
        # risponda ai callback (il bot gira su Actions ed esce subito).
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": "🎧 Ascolta l'episodio", "url": link}]]
        }
    resp = requests.post(f"{TELEGRAM_API}/sendPoll", json=payload, timeout=10)
    if "reply_markup" in payload and 400 <= resp.status_code < 500:
        # Un 4xx vuol dire che il poll non è partito: se la colpa è del
        # pulsante, il quiz va pubblicato comunque, senza.
        print(f"Avviso: poll rifiutato col pulsante ({resp.text}), riprovo senza.", file=sys.stderr)
        # una copia, non il dict già inviato: chi lo ha ricevuto (e un mock nei
        # test) deve continuare a vedere il pulsante del primo invio
        payload = {k: v for k, v in payload.items() if k != "reply_markup"}
        resp = requests.post(f"{TELEGRAM_API}/sendPoll", json=payload, timeout=10)
    _raise_for_telegram(resp)
    return resp.json()


def generate_quiz_content(provider: str | None = None) -> tuple[dict, dict | None]:
    """Genera il quiz e ritorna (quiz, episode_ref).

    Per i quiz basati su un episodio, `episode_ref` è un dict con `title` e
    `link` (la pagina dell'episodio sul sito, se presente nel feed RSS), usato
    poi per pubblicare il riferimento all'episodio nel canale. Per i quiz
    generici è `None`.
    """
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
            script = fetch_github_script(title, episode.get("link") or "")
            if transcript or script:
                content = "\n\n".join(filter(None, [
                    f"TRASCRIZIONE:\n{transcript[:4000]}" if transcript else "",
                    f"SCRIPT:\n{script[:2000]}" if script else "",
                ]))
                print("Genero il quiz basato sull'episodio...")
                episode_ref = {"title": title, "link": episode.get("link")}
                return call_ai(_EPISODE_SYSTEM, f"Titolo: {title}\n\n{content}", provider), episode_ref
            print("Nessun contenuto episodio disponibile, passo al quiz generico...")

    topic = random.choice(_GENERIC_TOPICS)
    print(f"Genero un quiz generico (tema: {topic})...")
    return call_ai(_GENERIC_SYSTEM, f"Genera un quiz sul tema: {topic}", provider), None


def _structure_errors(quiz: dict) -> list[str]:
    """Forma del quiz: tipi, opzioni e indici. Un quiz che non la rispetta
    viene rifiutato da Telegram (indici fuori range, opzioni vuote) oppure
    esce ambiguo (opzioni duplicate) o banale (tutte le opzioni corrette)."""
    errors = []
    question = quiz.get("question")
    if not isinstance(question, str) or not question.strip():
        errors.append("question mancante o vuota")

    options = quiz.get("options")
    if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
        return errors + ["options deve essere una lista di stringhe"]
    if not _MIN_OPTIONS <= len(options) <= _MAX_OPTIONS:
        errors.append(f"numero di opzioni fuori range: {len(options)} (ammesse {_MIN_OPTIONS}-{_MAX_OPTIONS})")
    if any(not o.strip() for o in options):
        errors.append("opzione vuota")
    normalized = [o.strip().casefold() for o in options]
    if len(set(normalized)) != len(normalized):
        errors.append("opzioni duplicate")

    ids = quiz.get("correct_option_ids")
    if (not isinstance(ids, list) or not ids
            or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids)):
        return errors + ["correct_option_ids deve essere una lista non vuota di interi"]
    if len(set(ids)) != len(ids):
        errors.append("correct_option_ids contiene indici ripetuti")
    if any(not 0 <= i < len(options) for i in ids):
        errors.append(f"correct_option_ids fuori range: {ids} con {len(options)} opzioni")
    if len(set(ids)) >= len(options):
        errors.append("tutte le opzioni sono marcate come corrette")

    explanation = quiz.get("explanation", "")
    if not isinstance(explanation, str):
        errors.append("explanation deve essere una stringa")
    elif explanation.count("\n") > _TELEGRAM_EXPLANATION_MAX_NEWLINES:
        errors.append(f"explanation con più di {_TELEGRAM_EXPLANATION_MAX_NEWLINES} a capo")
    return errors


def validate_quiz(quiz: dict) -> list[str]:
    """Controlla forma e limiti Telegram. Ritorna lista di errori, vuota se valido."""
    errors = _structure_errors(quiz)
    if errors:
        # i limiti di lunghezza presuppongono campi del tipo giusto
        return errors
    question = quiz.get("question", "")
    if len(question) > _TELEGRAM_QUESTION_MAX:
        errors.append(
            f"question troppo lunga: {len(question)}/{_TELEGRAM_QUESTION_MAX} caratteri"
        )
    # La description del poll include lo snippet del quiz + il footer di
    # trasparenza sul modello. Controlliamo la stringa finale che verrà inviata
    # a Telegram, non solo `quiz["description"]`.
    description = build_poll_description(quiz)
    if len(description) > _TELEGRAM_DESCRIPTION_MAX:
        errors.append(
            f"description troppo lunga: {len(description)}/{_TELEGRAM_DESCRIPTION_MAX} caratteri"
        )
    for i, opt in enumerate(quiz.get("options", [])):
        if len(opt) > _TELEGRAM_OPTION_MAX:
            errors.append(
                f"opzione {i} troppo lunga: {len(opt)}/{_TELEGRAM_OPTION_MAX} caratteri"
            )
    explanation = quiz.get("explanation", "")
    if len(explanation) > _TELEGRAM_EXPLANATION_MAX:
        errors.append(
            f"explanation troppo lunga: {len(explanation)}/{_TELEGRAM_EXPLANATION_MAX} caratteri"
        )
    return errors


_MAX_QUIZ_RETRIES = 5

# Codice d'uscita quando non si sa se il poll è uscito: diverso da 1 (fallito
# di sicuro), perché rilanciare il run potrebbe pubblicare un secondo quiz.
EXIT_UNCERTAIN = 3


def generate_valid_quiz() -> tuple[dict, dict | None]:
    """Genera un quiz valido rispetto ai limiti Telegram provando i provider configurati."""
    providers = get_quiz_providers()
    for provider_index, provider in enumerate(providers, start=1):
        if len(providers) > 1:
            print(f"Uso provider AI {provider_index}/{len(providers)}: {provider}")
        for attempt in range(1, _MAX_QUIZ_RETRIES + 1):
            try:
                quiz, episode_ref = generate_quiz_content(provider)
            except Exception as e:
                print(
                    f"Errore provider {provider} (tentativo {attempt}/{_MAX_QUIZ_RETRIES}): {e}",
                    file=sys.stderr,
                )
                if attempt < _MAX_QUIZ_RETRIES:
                    print("Riprovo con lo stesso provider...")
                continue

            # prima la validazione: print_quiz presuppone un quiz ben formato, e
            # un'eccezione qui fuori dal try fermerebbe il run senza fallback
            errors = validate_quiz(quiz)
            if not errors:
                print_quiz(quiz, episode_ref)
                return quiz, episode_ref
            print(
                f"Quiz non valido (tentativo {attempt}/{_MAX_QUIZ_RETRIES}): {'; '.join(errors)}",
                file=sys.stderr,
            )
            if attempt < _MAX_QUIZ_RETRIES:
                print("Rigenero il quiz...")
        if provider_index < len(providers):
            print(f"Provider {provider} esaurito, passo al prossimo provider...")
    print(
        f"Errore: impossibile generare un quiz valido dopo {_MAX_QUIZ_RETRIES} tentativi "
        f"per ciascun provider configurato: {', '.join(providers)}.",
        file=sys.stderr,
    )
    sys.exit(1)


def print_quiz(quiz: dict, episode_ref: dict | None, index: int | None = None) -> None:
    prefix = f"[{index}] " if index is not None else ""
    tipo = f"episodio ({episode_ref['title']})" if episode_ref else "generico"
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

    if not FEED_RSS_URL:
        print("Avviso: FEED_RSS_URL non impostata, solo quiz generici.", file=sys.stderr)

    if args.dry_run is not None:
        print("Scarico il feed RSS...")
        for i in range(1, args.dry_run + 1):
            quiz, episode_ref = generate_quiz_content()
            print_quiz(quiz, episode_ref, index=i if args.dry_run > 1 else None)
        return

    print("Scarico il feed RSS...")
    quiz, episode_ref = generate_valid_quiz()

    print("Invio il poll su Telegram...")
    try:
        poll_message_id = send_poll(quiz, episode_ref)["result"]["message_id"]
    except requests.exceptions.ReadTimeout:
        # La richiesta è partita e la risposta non è arrivata: Telegram può
        # averla accettata. Ripeterla rischia un doppione, quindi non si ripete.
        print(
            "Esito incerto: timeout in attesa della risposta di Telegram, il poll potrebbe "
            "essere stato pubblicato. Controlla il canale prima di rilanciare.",
            file=sys.stderr,
        )
        sys.exit(EXIT_UNCERTAIN)

    # il poll è uscito: un errore nel log non deve far sembrare fallito il run
    try:
        episode_title = episode_ref["title"] if episode_ref else None
        correct = quiz["options"][quiz["correct_option_ids"][0]]
        print(
            f"[{datetime.datetime.now(datetime.timezone.utc).isoformat()}] "
            f"type={'episodio' if episode_ref else 'generico'} "
            f"episode={episode_title!r} poll_id={poll_message_id} status=success\n"
            f"  Q: {quiz['question']}\n"
            f"  A: {correct}\n"
            f"  💡 {quiz.get('explanation', '')}"
        )
    except Exception as e:
        print(f"Avviso: log finale non riuscito ({e}).", file=sys.stderr)
    print("Quiz pubblicato con successo!")


if __name__ == "__main__":
    main()
