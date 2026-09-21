#!/usr/bin/env python3
"""
Oxford Brookes CLI — a local, offline knowledge-base search tool.

Indexes every .md/.txt file under data/ (course overviews, extracted file
text, and general university info) and lets you search or browse it from
the command line. No API key, no network calls, no external dependencies —
pure Python standard library.

Usage:
    python3 brookes_cli.py                       Interactive mode (REPL)
    python3 brookes_cli.py search "exam resits"  One-off search
    python3 brookes_cli.py ask "when is semester 2"   Alias for search
    python3 brookes_cli.py list                  List all courses/sections
    python3 brookes_cli.py show <doc-id>          Print a document in full
    python3 brookes_cli.py topics                 List general (non-course) topics
    python3 brookes_cli.py deadlines [course]     List every deadline-shaped sentence found
    python3 brookes_cli.py import <file> --course "01 COMP4004 - ..."
                                                   Ingest a real .docx/.txt/.md file

There is no live network access here on purpose — Moodle needs a login this
tool never handles. To bring in fresh content: download or export it
yourself (a Module Guide .docx, a saved page, etc) and run `import` — it's
re-indexed on every run, so re-importing a newer version just replaces it.

Run `python3 brookes_cli.py --help` for all options.
"""
from __future__ import annotations

import argparse
import difflib
import math
import os
import re
import sys
import textwrap
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

DEADLINE_KEYWORDS_RE = re.compile(
    r"\b(deadline|due (?:date|by|on|for|in)|submission date|hand-?in|submitted by|closing date|"
    r"uploaded?\b.{0,60}\bby\b|due at the end|due on|must be (?:uploaded|submitted)|final hand-in)\b",
    re.IGNORECASE,
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or", "is",
    "are", "was", "were", "be", "been", "being", "this", "that", "these",
    "those", "with", "as", "by", "from", "it", "its", "into", "do", "does",
    "did", "you", "your", "i", "will", "can", "not", "no", "if", "so",
}

WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9\-']+")


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


@dataclass
class Document:
    doc_id: str          # stable short id, e.g. "04/overview" or "06/extracted/foo.pdf"
    course: str           # top-level course folder name, or "general"
    rel_path: str         # path relative to data/
    title: str            # first heading / filename
    content: str
    tokens: list[str] = field(default_factory=list, repr=False)


class Index:
    """A tiny in-memory inverted index with TF-IDF style scoring."""

    def __init__(self, docs: list[Document]):
        self.docs = {d.doc_id: d for d in docs}
        self.postings: dict[str, Counter] = defaultdict(Counter)  # term -> {doc_id: count}
        self.doc_len: dict[str, int] = {}
        self.vocab: set[str] = set()

        for d in docs:
            d.tokens = tokenize(d.content)
            self.doc_len[d.doc_id] = max(len(d.tokens), 1)
            counts = Counter(d.tokens)
            for term, c in counts.items():
                self.postings[term][d.doc_id] += c
                self.vocab.add(term)

        self.n_docs = max(len(docs), 1)

    def idf(self, term: str) -> float:
        df = len(self.postings.get(term, {}))
        if df == 0:
            return 0.0
        return math.log((self.n_docs + 1) / (df + 0.5)) + 1

    def correct_term(self, term: str) -> str | None:
        """Fuzzy-correct a query term against the corpus vocabulary."""
        if term in self.vocab:
            return term
        matches = difflib.get_close_matches(term, self.vocab, n=1, cutoff=0.75)
        return matches[0] if matches else None

    def search(self, query: str, top_k: int = 8) -> list[tuple[Document, float, list[str]]]:
        raw_terms = [t for t in tokenize(query) if t not in STOPWORDS] or tokenize(query)
        terms = []
        corrected_notes = []
        for t in raw_terms:
            c = self.correct_term(t)
            if c is None:
                continue
            if c != t:
                corrected_notes.append((t, c))
            terms.append(c)

        if not terms:
            return []

        scores: Counter = Counter()
        for term in terms:
            weight = self.idf(term)
            for doc_id, count in self.postings.get(term, {}).items():
                tf = count / self.doc_len[doc_id]
                scores[doc_id] += tf * weight

        ranked = scores.most_common(top_k)
        return [(self.docs[doc_id], score, terms) for doc_id, score in ranked if score > 0]


def snippet(content: str, terms: list[str], width: int = 280) -> str:
    """Return the best-matching excerpt of a document for the given terms."""
    lower = content.lower()
    best_pos = -1
    for term in terms:
        pos = lower.find(term)
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos
    if best_pos == -1:
        excerpt = content[:width]
    else:
        start = max(0, best_pos - width // 3)
        excerpt = content[start:start + width]
    excerpt = " ".join(excerpt.split())
    return excerpt + ("…" if len(content) > width else "")


def load_documents() -> list[Document]:
    docs: list[Document] = []
    if not DATA_DIR.exists():
        return docs

    for path in sorted(DATA_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".md", ".txt"):
            continue

        rel = path.relative_to(DATA_DIR)
        parts = rel.parts
        course = parts[0] if parts[0] != "general" else "general"
        doc_id = str(rel.with_suffix(""))

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        if path.suffix.lower() == ".md":
            first_line = next((l.strip("# ").strip() for l in content.splitlines() if l.strip()), path.stem)
        else:
            # extracted .txt files: use the original filename (strip the .txt we appended)
            first_line = path.stem
        docs.append(Document(
            doc_id=doc_id,
            course=course,
            rel_path=str(rel),
            title=first_line,
            content=content,
        ))
    return docs


def print_results(results, show_snippets=True):
    if not results:
        print("No matches found. Try different or fewer words.")
        return
    for i, (doc, score, terms) in enumerate(results, 1):
        print(f"\n[{i}] {doc.title}")
        print(f"    course: {doc.course}    id: {doc.doc_id}    score: {score:.2f}")
        if show_snippets:
            snip = snippet(doc.content, terms)
            wrapped = textwrap.fill(snip, width=100, initial_indent="    > ", subsequent_indent="      ")
            print(wrapped)


def cmd_search(index: Index, query: str, top_k: int):
    results = index.search(query, top_k=top_k)
    print_results(results)
    if results:
        print(f"\nUse `show <id>` to read a document in full, e.g.: show {results[0][0].doc_id}")


def cmd_list(docs: list[Document]):
    by_course: dict[str, list[Document]] = defaultdict(list)
    for d in docs:
        by_course[d.course].append(d)
    for course in sorted(by_course):
        print(f"\n== {course} ==")
        for d in sorted(by_course[course], key=lambda x: x.rel_path):
            print(f"  {d.doc_id}")


def cmd_topics(docs: list[Document]):
    general = [d for d in docs if d.course == "general"]
    if not general:
        print("No general topics indexed.")
        return
    print("General (non-course) Oxford Brookes topics:\n")
    for d in sorted(general, key=lambda x: x.rel_path):
        print(f"  {d.doc_id:35s} — {d.title}")


def extract_docx_text(path: Path) -> str:
    """Pull plain text out of a .docx (it's a zip of XML) — stdlib only,
    no python-docx dependency."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    xml = xml.replace("</w:p>", "\n")
    text = re.sub(r"<[^>]+>", "", xml)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text


def cmd_import(path_str: str, course: str, out_name: str | None):
    """Ingest a real local file (currently .docx, .txt, .md) into
    data/courses/<course>/ so it becomes searchable. This is how content
    gets in when there's no live Moodle session available — drop the file
    you already have (a downloaded module guide, an exported page, etc)
    and import it once; re-run whenever you have a newer version."""
    src = Path(path_str).expanduser()
    if not src.is_file():
        print(f"No such file: {src}", file=sys.stderr)
        sys.exit(1)

    suffix = src.suffix.lower()
    if suffix == ".docx":
        text = extract_docx_text(src)
    elif suffix in (".txt", ".md"):
        text = src.read_text(encoding="utf-8", errors="replace")
    else:
        print(f"Unsupported file type '{suffix}'. Supported: .docx, .txt, .md", file=sys.stderr)
        sys.exit(1)

    if not text.strip():
        print("Extracted no text from that file — nothing to import.", file=sys.stderr)
        sys.exit(1)

    course_dir = DATA_DIR / "courses" / course
    course_dir.mkdir(parents=True, exist_ok=True)
    dest = course_dir / f"{out_name or src.stem}.txt"
    dest.write_text(text, encoding="utf-8")
    print(f"Imported {len(text):,} characters -> {dest.relative_to(DATA_DIR)}")
    print(f"Query it with: python3 brookes_cli.py search \"...\" or show {dest.relative_to(DATA_DIR).with_suffix('')}")


def subject_name(d: Document) -> str:
    """Document.course is always the generic top-level bucket ("courses" or
    "general") — this pulls out the actual subject/module folder name for
    display, e.g. "01 COMP4004 - Problem Solving and Programming"."""
    parts = Path(d.rel_path).parts
    return parts[1] if d.course == "courses" and len(parts) > 1 else d.course


def cmd_deadlines(docs: list[Document], course_filter: str | None):
    """Scan every indexed document for deadline-shaped sentences and list
    them grouped by course — the "what's outstanding" view."""
    by_course: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for d in docs:
        if course_filter and course_filter.lower() not in d.rel_path.lower():
            continue
        seen = set()
        flat = " ".join(d.content.split("\n"))
        for sentence in SENTENCE_SPLIT_RE.split(flat):
            sentence = sentence.strip()
            if len(sentence) < 15 or "PAGEREF" in sentence or not DEADLINE_KEYWORDS_RE.search(sentence):
                continue
            if sentence in seen:
                continue
            seen.add(sentence)
            by_course[subject_name(d)].append((d.title, sentence))

    if not by_course:
        print("No deadline-shaped sentences found." + (f" (filtered to '{course_filter}')" if course_filter else ""))
        return

    for course in sorted(by_course):
        print(f"\n== {course} ==")
        for title, line in by_course[course]:
            wrapped = textwrap.fill(line, width=96, initial_indent="  ", subsequent_indent="    ")
            print(f"  [{title}]")
            print(wrapped)


def cmd_show(docs_by_id: dict[str, Document], doc_id: str):
    doc = docs_by_id.get(doc_id)
    if doc is None:
        # try partial match
        matches = [d for did, d in docs_by_id.items() if doc_id.lower() in did.lower()]
        if len(matches) == 1:
            doc = matches[0]
        elif len(matches) > 1:
            print(f"Multiple documents match '{doc_id}':")
            for d in matches:
                print(f"  {d.doc_id}")
            return
    if doc is None:
        print(f"No document found matching '{doc_id}'. Try `list` to see all ids.")
        return
    print(f"# {doc.title}\n(id: {doc.doc_id}, course: {doc.course})\n")
    print(doc.content)


def repl(index: Index, docs_by_id: dict[str, Document]):
    print("Oxford Brookes CLI — interactive mode.")
    print("Type a question/topic to search, or a command: list, topics, deadlines [course], show <id>, quit\n")
    while True:
        try:
            line = input("brookes> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("quit", "exit", "q"):
            break
        elif line == "list":
            cmd_list(list(docs_by_id.values()))
        elif line == "topics":
            cmd_topics(list(docs_by_id.values()))
        elif line.startswith("show "):
            cmd_show(docs_by_id, line[len("show "):].strip())
        elif line == "deadlines" or line.startswith("deadlines "):
            cmd_deadlines(list(docs_by_id.values()), line[len("deadlines "):].strip() or None)
        else:
            cmd_search(index, line, top_k=6)


def main():
    parser = argparse.ArgumentParser(
        description="Search a local Oxford Brookes / course knowledge base.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    p_search = sub.add_parser("search", aliases=["ask"], help="Search the knowledge base")
    p_search.add_argument("query", nargs="+", help="Search terms / question")
    p_search.add_argument("-n", "--top", type=int, default=8, help="Number of results (default 8)")

    sub.add_parser("list", help="List all indexed documents by course")
    sub.add_parser("topics", help="List general (university-wide) topics")

    p_show = sub.add_parser("show", help="Print a document in full")
    p_show.add_argument("doc_id", help="Document id (or partial match), from `list`")

    p_import = sub.add_parser("import", help="Ingest a real local file (.docx/.txt/.md) into a course's knowledge base")
    p_import.add_argument("file", help="Path to the file, e.g. a downloaded Module Guide .docx")
    p_import.add_argument("--course", required=True, help='Course folder name, e.g. "01 COMP4004 - Problem Solving and Programming"')
    p_import.add_argument("--name", help="Output filename (without extension); defaults to the source filename")

    p_deadlines = sub.add_parser("deadlines", help="List every deadline-shaped sentence found across indexed documents")
    p_deadlines.add_argument("course", nargs="?", help="Optional course name filter (substring match)")

    args = parser.parse_args()

    if args.command == "import":
        cmd_import(args.file, args.course, args.name)
        return

    docs = load_documents()
    if not docs:
        print(f"No documents found under {DATA_DIR}. Nothing to search.", file=sys.stderr)
        sys.exit(1)

    index = Index(docs)
    docs_by_id = {d.doc_id: d for d in docs}

    if args.command in ("search", "ask"):
        cmd_search(index, " ".join(args.query), top_k=args.top)
    elif args.command == "list":
        cmd_list(docs)
    elif args.command == "topics":
        cmd_topics(docs)
    elif args.command == "show":
        cmd_show(docs_by_id, args.doc_id)
    elif args.command == "deadlines":
        cmd_deadlines(docs, args.course)
    else:
        repl(index, docs_by_id)


if __name__ == "__main__":
    main()
