#!/usr/bin/env python3
"""
pdf_to_anki.py — Pipeline end-to-end: PDF → Flashcard Anki (.apkg)

Requisiti:
    pip install pdfplumber genanki openai

Uso:
    # Con OpenAI (GPT)
    python pdf_to_anki.py --pdf appunti.pdf --llm openai --api-key sk-...

    # Con Ollama locale (gratuito al 100%)
    python pdf_to_anki.py --pdf appunti.pdf --llm ollama --model llama3

    # Con Anthropic (Claude)
    python pdf_to_anki.py --pdf appunti.pdf --llm anthropic --api-key sk-ant-...

    # Solo estrazione + CSV (senza LLM, flashcard manuali)
    python pdf_to_anki.py --pdf appunti.pdf --llm none

    # Importa un CSV già pronto
    python pdf_to_anki.py --csv flashcards.csv

Opzioni:
    --pdf           Path al file PDF sorgente
    --csv           Path a un CSV già pronto (colonne: question,answer)
    --output        Nome file .apkg di output (default: output.apkg)
    --deck-name     Nome del mazzo Anki (default: nome del PDF)
    --llm           Provider LLM: openai | anthropic | ollama | none
    --model         Modello specifico (default: gpt-4o-mini / claude-3-haiku / llama3)
    --api-key       API key (non serve per ollama)
    --ollama-url    URL di Ollama (default: http://localhost:11434)
    --max-cards     Numero massimo di flashcard per chunk (default: 10)
    --language      Lingua delle flashcard (default: italiano)
    --tags          Tag Anki separati da virgola (default: nessuno)
    --pages         Range di pagine, es. 1-5,8,10-12 (default: tutte)
    --chunk-size    Caratteri per chunk di testo (default: 3000)
    --verbose       Mostra output dettagliato
"""

import argparse
import csv
import json
import logging
import random
import re
import sys
import textwrap
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

try:
    import pdfplumber
except ImportError:
    sys.exit("❌ Installa pdfplumber: pip install pdfplumber")

try:
    import genanki
except ImportError:
    sys.exit("❌ Installa genanki: pip install genanki")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------
ANKI_MODEL = genanki.Model(
    model_id=1607392319,
    name="PDF2Anki Basic",
    fields=[
        {"name": "Front"},
        {"name": "Back"},
    ],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "<div style='font-size:20px;'>{{Front}}</div>",
            "afmt": (
                "{{FrontSide}}"
                "<hr id='answer'>"
                "<div style='font-size:18px;'>{{Back}}</div>"
            ),
        },
    ],
    css=(
        ".card { font-family: 'Segoe UI', Arial, sans-serif; "
        "text-align: center; padding: 20px; }"
    ),
)

SYSTEM_PROMPT = textwrap.dedent("""\
    Sei un esperto nella creazione di flashcard per lo studio.
    Dato un testo, genera flashcard in formato JSON.

    REGOLE:
    1. Ogni flashcard ha una "question" (domanda chiara e specifica) e una "answer" (risposta concisa ma completa).
    2. Copri i concetti chiave, definizioni, formule, date, relazioni causa-effetto.
    3. Evita domande troppo generiche o banali.
    4. Le risposte devono essere auto-contenute (comprensibili senza il testo originale).
    5. Usa la lingua specificata.
    6. Rispondi SOLO con un array JSON valido, senza markdown o altro testo.

    Formato output:
    [
      {"question": "...", "answer": "..."},
      {"question": "...", "answer": "..."}
    ]
""")


# ---------------------------------------------------------------------------
# 1. Estrazione testo dal PDF
# ---------------------------------------------------------------------------
def parse_page_ranges(pages_str: str, max_page: int) -> list[int]:
    """Parsa range di pagine tipo '1-5,8,10-12' → [0,1,2,3,4,7,9,10,11]."""
    pages: list[int] = []
    for part in pages_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            start_i = max(1, int(start))
            end_i = min(max_page, int(end))
            pages.extend(range(start_i - 1, end_i))
        else:
            p = int(part) - 1
            if 0 <= p < max_page:
                pages.append(p)
    return sorted(set(pages))


def extract_text_from_pdf(
    pdf_path: str,
    pages: Optional[str] = None,
) -> str:
    """Estrae testo da un PDF usando pdfplumber."""
    log.info("📄 Estrazione testo da: %s", pdf_path)
    text_parts: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        log.info("   Pagine totali: %d", total)

        if pages:
            page_indices = parse_page_ranges(pages, total)
            log.info("   Pagine selezionate: %s", [i + 1 for i in page_indices])
        else:
            page_indices = list(range(total))

        for i in page_indices:
            page = pdf.pages[i]
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(f"--- Pagina {i + 1} ---\n{page_text}")

    full_text = "\n\n".join(text_parts)
    log.info("   Caratteri estratti: %d", len(full_text))

    if not full_text.strip():
        sys.exit("❌ Nessun testo estratto dal PDF. Potrebbe essere un PDF scansionato (immagini).")

    return full_text


# ---------------------------------------------------------------------------
# 2. Chunking del testo
# ---------------------------------------------------------------------------
def chunk_text(text: str, chunk_size: int = 3000) -> list[str]:
    """Divide il testo in chunk gestibili per l'LLM."""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = ""
        current_chunk += para + "\n\n"

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    log.info("📦 Testo diviso in %d chunk (max %d char)", len(chunks), chunk_size)
    return chunks


# ---------------------------------------------------------------------------
# 3. Generazione flashcard via LLM
# ---------------------------------------------------------------------------
def _build_user_prompt(text: str, max_cards: int, language: str) -> str:
    return (
        f"Genera fino a {max_cards} flashcard in {language} dal seguente testo.\n"
        f"Rispondi SOLO con un array JSON valido.\n\n"
        f"TESTO:\n{text}"
    )


def _parse_json_response(raw: str) -> list[dict]:
    """Estrae l'array JSON dalla risposta LLM, gestendo markdown fences."""
    # Rimuovi eventuale ```json ... ```
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = cleaned.strip().rstrip("`")

    # Trova il primo [ e l'ultimo ]
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1:
        log.warning("⚠️  Nessun array JSON trovato nella risposta")
        return []

    try:
        cards = json.loads(cleaned[start : end + 1])
        return [c for c in cards if "question" in c and "answer" in c]
    except json.JSONDecodeError as e:
        log.warning("⚠️  JSON non valido: %s", e)
        return []


def generate_via_openai(
    chunks: list[str],
    api_key: str,
    model: str,
    max_cards: int,
    language: str,
) -> list[dict]:
    """Chiama OpenAI API (compatibile anche con provider OpenAI-like)."""
    try:
        import openai
    except ImportError:
        sys.exit("❌ Installa openai: pip install openai")

    client = openai.OpenAI(api_key=api_key)
    all_cards: list[dict] = []

    for i, chunk in enumerate(chunks, 1):
        log.info("🤖 [OpenAI] Chunk %d/%d → modello %s", i, len(chunks), model)
        resp = client.chat.completions.create(
            model=model,
            temperature=0.3,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(chunk, max_cards, language)},
            ],
        )
        raw = resp.choices[0].message.content or ""
        cards = _parse_json_response(raw)
        log.info("   → %d flashcard generate", len(cards))
        all_cards.extend(cards)

    return all_cards


def generate_via_anthropic(
    chunks: list[str],
    api_key: str,
    model: str,
    max_cards: int,
    language: str,
) -> list[dict]:
    """Chiama Anthropic API (Claude)."""
    try:
        import anthropic
    except ImportError:
        sys.exit("❌ Installa anthropic: pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)
    all_cards: list[dict] = []

    for i, chunk in enumerate(chunks, 1):
        log.info("🤖 [Anthropic] Chunk %d/%d → modello %s", i, len(chunks), model)
        resp = client.messages.create(
            model=model,
            max_tokens=4096,
            temperature=0.3,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": _build_user_prompt(chunk, max_cards, language)},
            ],
        )
        raw = resp.content[0].text
        cards = _parse_json_response(raw)
        log.info("   → %d flashcard generate", len(cards))
        all_cards.extend(cards)

    return all_cards


def generate_via_ollama(
    chunks: list[str],
    model: str,
    ollama_url: str,
    max_cards: int,
    language: str,
) -> list[dict]:
    """Chiama Ollama locale (100% gratuito, nessuna API key)."""
    all_cards: list[dict] = []
    endpoint = f"{ollama_url.rstrip('/')}/api/chat"

    for i, chunk in enumerate(chunks, 1):
        log.info("🤖 [Ollama] Chunk %d/%d → modello %s", i, len(chunks), model)
        payload = json.dumps({
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(chunk, max_cards, language)},
            ],
        }).encode("utf-8")

        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                raw = body.get("message", {}).get("content", "")
        except urllib.error.URLError as e:
            log.error("❌ Ollama non raggiungibile (%s). È in esecuzione?", e)
            sys.exit(1)

        cards = _parse_json_response(raw)
        log.info("   → %d flashcard generate", len(cards))
        all_cards.extend(cards)

    return all_cards


# ---------------------------------------------------------------------------
# 4. Deduplica e pulizia
# ---------------------------------------------------------------------------
def deduplicate_cards(cards: list[dict]) -> list[dict]:
    """Rimuove flashcard duplicate basandosi sulla domanda normalizzata."""
    seen: set[str] = set()
    unique: list[dict] = []
    for card in cards:
        key = card["question"].strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(card)
    removed = len(cards) - len(unique)
    if removed:
        log.info("🧹 Rimosse %d flashcard duplicate", removed)
    return unique


# ---------------------------------------------------------------------------
# 5. Export CSV (backup intermedio)
# ---------------------------------------------------------------------------
def save_csv(cards: list[dict], csv_path: str) -> None:
    """Salva le flashcard in CSV come backup."""
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["question", "answer"])
        writer.writeheader()
        writer.writerows(cards)
    log.info("💾 CSV salvato: %s (%d righe)", csv_path, len(cards))


def load_csv(csv_path: str) -> list[dict]:
    """Carica flashcard da un CSV esistente."""
    cards: list[dict] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            q = row.get("question", row.get("front", row.get("domanda", ""))).strip()
            a = row.get("answer", row.get("back", row.get("risposta", ""))).strip()
            if q and a:
                cards.append({"question": q, "answer": a})
    log.info("📂 CSV caricato: %s (%d flashcard)", csv_path, len(cards))
    return cards


# ---------------------------------------------------------------------------
# 6. Creazione file .apkg
# ---------------------------------------------------------------------------
def create_apkg(
    cards: list[dict],
    output_path: str,
    deck_name: str,
    tags: Optional[list[str]] = None,
) -> None:
    """Crea il file .apkg da una lista di flashcard."""
    deck_id = random.randrange(1 << 30, 1 << 31)
    deck = genanki.Deck(deck_id, deck_name)

    for card in cards:
        note = genanki.Note(
            model=ANKI_MODEL,
            fields=[card["question"], card["answer"]],
            tags=tags or [],
        )
        deck.add_note(note)

    package = genanki.Package(deck)
    package.write_to_file(output_path)
    log.info("✅ File Anki creato: %s (%d flashcard)", output_path, len(cards))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="PDF → Anki Flashcards (.apkg) — Pipeline end-to-end",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Esempi:
              # Ollama locale (100%% gratuito)
              python pdf_to_anki.py --pdf libro.pdf --llm ollama --model llama3

              # OpenAI
              python pdf_to_anki.py --pdf libro.pdf --llm openai --api-key sk-...

              # Solo estrazione testo → CSV (modifica manualmente, poi importa)
              python pdf_to_anki.py --pdf libro.pdf --llm none
              python pdf_to_anki.py --csv flashcards.csv

              # Pagine specifiche + tag
              python pdf_to_anki.py --pdf libro.pdf --llm ollama --pages 1-5,10 --tags "storia,esame"
        """),
    )
    p.add_argument("--pdf", type=str, help="Path al file PDF sorgente")
    p.add_argument("--csv", type=str, help="Path a un CSV già pronto (question,answer)")
    p.add_argument("--output", type=str, default=None, help="Nome file .apkg output")
    p.add_argument("--deck-name", type=str, default=None, help="Nome del mazzo Anki")
    p.add_argument(
        "--llm",
        choices=["openai", "anthropic", "ollama", "none"],
        default="ollama",
        help="Provider LLM (default: ollama)",
    )
    p.add_argument("--model", type=str, default=None, help="Modello LLM specifico")
    p.add_argument("--api-key", type=str, default=None, help="API key (non serve per ollama)")
    p.add_argument(
        "--ollama-url",
        type=str,
        default="http://localhost:11434",
        help="URL di Ollama (default: http://localhost:11434)",
    )
    p.add_argument("--max-cards", type=int, default=10, help="Max flashcard per chunk (default: 10)")
    p.add_argument("--language", type=str, default="italiano", help="Lingua flashcard (default: italiano)")
    p.add_argument("--tags", type=str, default=None, help="Tag Anki separati da virgola")
    p.add_argument("--pages", type=str, default=None, help="Range pagine, es. 1-5,8,10-12")
    p.add_argument("--chunk-size", type=int, default=3000, help="Caratteri per chunk (default: 3000)")
    p.add_argument("--verbose", action="store_true", help="Output dettagliato")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    log.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    if not args.pdf and not args.csv:
        parser.error("Specifica almeno --pdf o --csv")

    # --- Default dinamici ---
    pdf_stem = Path(args.pdf).stem if args.pdf else "flashcards"
    deck_name = args.deck_name or pdf_stem.replace("_", " ").replace("-", " ").title()
    output_path = args.output or f"{pdf_stem}.apkg"
    csv_backup = f"{pdf_stem}_flashcards.csv"
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []

    default_models = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-haiku-20240307",
        "ollama": "llama3",
    }
    model = args.model or default_models.get(args.llm, "")

    # --- Pipeline ---
    cards: list[dict] = []

    if args.csv:
        # Modalità: importa CSV esistente
        cards = load_csv(args.csv)
    elif args.pdf:
        # Step 1: Estrai testo
        text = extract_text_from_pdf(args.pdf, pages=args.pages)

        if args.llm == "none":
            # Modalità: solo estrazione → salva testo grezzo per editing manuale
            txt_path = f"{pdf_stem}_testo.txt"
            Path(txt_path).write_text(text, encoding="utf-8")
            log.info("📝 Testo salvato in: %s", txt_path)
            log.info("ℹ️  Crea un CSV con colonne 'question,answer' e riesegui con --csv")
            # Genera un CSV template vuoto
            with open(csv_backup, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["question", "answer"])
                writer.writerow(["Esempio: Cos'è X?", "X è ..."])
            log.info("📝 Template CSV creato: %s", csv_backup)
            return

        # Step 2: Chunking
        chunks = chunk_text(text, chunk_size=args.chunk_size)

        # Step 3: Genera flashcard via LLM
        if args.llm == "openai":
            if not args.api_key:
                sys.exit("❌ --api-key richiesta per OpenAI")
            cards = generate_via_openai(chunks, args.api_key, model, args.max_cards, args.language)

        elif args.llm == "anthropic":
            if not args.api_key:
                sys.exit("❌ --api-key richiesta per Anthropic")
            cards = generate_via_anthropic(chunks, args.api_key, model, args.max_cards, args.language)

        elif args.llm == "ollama":
            cards = generate_via_ollama(chunks, model, args.ollama_url, args.max_cards, args.language)

        # Step 4: Deduplica
        cards = deduplicate_cards(cards)

        # Step 5: Salva CSV backup
        if cards:
            save_csv(cards, csv_backup)

    # --- Step 6: Crea .apkg ---
    if not cards:
        sys.exit("❌ Nessuna flashcard generata. Controlla il PDF o i parametri LLM.")

    create_apkg(cards, output_path, deck_name, tags)

    # --- Riepilogo ---
    print("\n" + "=" * 50)
    print(f"🎉 FATTO!")
    print(f"   📦 File:       {output_path}")
    print(f"   🃏 Flashcard:  {len(cards)}")
    print(f"   📚 Mazzo:      {deck_name}")
    if tags:
        print(f"   🏷️  Tag:        {', '.join(tags)}")
    print(f"   💾 CSV backup: {csv_backup}")
    print(f"\n   Apri {output_path} con Anki per importare il mazzo!")
    print("=" * 50)


if __name__ == "__main__":
    main()

