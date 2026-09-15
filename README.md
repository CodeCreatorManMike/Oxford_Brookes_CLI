# Oxford Brookes CLI

A local, offline knowledge base and command-line search tool covering my BSc Artificial Intelligence course at Oxford Brookes University — built from scraped Moodle course content plus general university information (regulations, dates, support services). No API key, no network calls at query time: it's a self-contained corpus you can search from the terminal, or upload wholesale into a ChatGPT/Claude project as reference files.

## What this is

Two things live in this repo:

1. **`data/`** — a plain-text/markdown knowledge base: every Moodle course page I have access to (overview + full text of every handout, slide deck, module guide and past exam paper), plus researched general Oxford Brookes info (assessment regulations, semester dates, the AI programme structure, support services).
2. **`brookes_cli.py`** — a zero-dependency Python CLI that indexes all of `data/` and lets you search it, browse it by course, or read any document in full.

The goal: one place to ask "when's the exam period", "what's the resit policy", "what did the COMP4035 induction slides say", etc., without digging back through Moodle — and the same folder doubles as upload material for an AI assistant project.

## Requirements

- Python 3.9+ (standard library only — nothing to `pip install`)

## Usage

```bash
git clone https://github.com/CodeCreatorManMike/Oxford_Brookes_CLI.git
cd Oxford_Brookes_CLI

# Interactive mode — just start typing questions
python3 brookes_cli.py

# One-off search
python3 brookes_cli.py search "when is the semester 2 exam period"
python3 brookes_cli.py ask "what's the resit mark cap"          # "ask" is an alias for "search"

# List everything that's indexed, grouped by course
python3 brookes_cli.py list

# List just the general (non-course) Oxford Brookes topics
python3 brookes_cli.py topics

# Print a document in full (id from `list`/`topics`, or a partial match)
python3 brookes_cli.py show general/assessment_regulations
python3 brookes_cli.py show "MATH4004 - Mathematics for Computing/overview"
```

Interactive mode supports the same `list`, `topics`, and `show <id>` commands, plus free-text search on anything else you type, until you type `quit`/`exit`/`q`.

### How search works

Every `.md`/`.txt` file under `data/` is one document. At startup the CLI builds an in-memory inverted index (word → documents containing it) and scores matches with a TF-IDF-style weighting, so rarer/more specific words count for more than common ones. Typos in your query are fuzzy-corrected against the corpus vocabulary (`difflib`) before scoring, so "compnesation progresion" still finds the progression-requirements page. Results show a ranked list with the best-matching excerpt and a document id you can pass to `show` for the full text — no result is ever truncated in a way that loses the source, and nothing here is AI-generated at search time: it's plain keyword/relevance search over real scraped text, so answers are always traceable to a specific file.

There's no persistent index file — it rebuilds in memory each run, which is instant at this corpus size (~1MB, under 60 documents).

## What's covered

### Course content (`data/courses/`)
Scraped from Moodle on 2026-09-15, one folder per course, each with an `overview.md` (page structure, announcements, assessment breakdown, key contacts) and the full extracted text of every downloadable file:

| Folder | Course | Files |
|---|---|---|
| `01` | COMP4004 — Problem Solving and Programming | Module Handbook |
| `02` | COMP4009 — Foundations of Computer Systems | *(no materials posted yet)* |
| `03` | COMP4035 — Computer Science Applications | Module Guide, Lecture 1, Practical Week 1, XAI lecture slides |
| `04` | MATH4004 — Mathematics for Computing | Full Lecture Notes, Module Guide, Formula Booklet, 4 years of past exam papers + solutions |
| `05` | Computing Induction Materials (ECM) | All 6 induction slide decks (welcome talk, subject intros, careers, placements, computer session) |
| `06` | ECM Computing Events and Student Opportunities | 2 programme handbooks + archived 2016-19 programme specs/structure diagrams/learning outcomes for older Computing pathways (SD/SQ/RO/IC/NK/WB) — historical, doesn't map to the current AI course |
| `07` | Academic Integrity | *(self-paced online course, no files — complete once)* |
| `08` | Computing - Academic Advising | Year 1 tutor and academic advisor names |
| `09` | ECM Events | *(empty — announcements forum only)* |
| `10` | Use of AI — Ethical decision making | Full traffic-light AI-use guidance (annual requirement from Sept 2026) |

### General Oxford Brookes info (`data/general/`)
Researched from public brookes.ac.uk pages on 2026-09-15:

- **`programme_ai.md`** — BSc (Hons) Artificial Intelligence structure: entry requirements, year-by-year module list (indicative — the formal Programme Specification isn't publicly indexed), credits, teaching/assessment model, fees.
- **`semester_dates.md`** — Semester 1 & 2 dates for 2026-27, induction weeks, exam periods. Brookes runs no reading weeks.
- **`assessment_regulations.md`** — the marking scale (A+ to F), progression requirements between levels, resit/retake rules and the 40% resit cap, award classification bands and weighting (25% Level 5 / 75% Level 6), and the full Exceptional (Extenuating) Circumstances process — what counts, what doesn't, how and when to apply.
- **`student_support_services.md`** — Centre for Academic Development, Library services (referencing style, EndNote, Turnitin), IT Service Desk & eduroam, Wellbeing/Counselling/Inclusive Support, and the Timetabling system (TimeEdit).
- **`practical_info.md`** — Headington campus facilities (the new Headington Hill building housing Computing), the Students' Union, and the core online platforms (Student Information portal, Moodle, TimeEdit, student Gmail).

Known gaps are flagged inline in those files — mainly the formal (login-gated) Programme Specification document and the precise 2026-27 exam timetable, which wasn't published yet at research time.

## Using this with a ChatGPT / Claude project

The whole `data/` folder (or the repo as a whole) is small enough and clean enough to upload directly as project knowledge: every file is plain text/markdown, organized by topic, with no binary clutter. Point a project at the `data/courses/` and `data/general/` folders and you've got the same corpus this CLI searches, queryable in natural language instead of keyword search.

## Updating the knowledge base

Re-run the same extraction pipeline (PDF/DOCX/PPTX → `.txt`) whenever new Moodle content is posted, drop the new files into the matching `data/courses/<course>/` folder, and re-run the CLI — no index to rebuild by hand, no config to update.

## Notes

- The Moodle credentials used to originally pull this content are **not** stored anywhere in this repo.
- Course content was current as of 2026-09-15; re-scrape periodically as new material is posted (especially exam timetables and any COMP4009 materials once posted).
