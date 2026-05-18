#!/usr/bin/env python3
"""Stuur gewijzigde .md/.mdx bestanden naar Claude voor een didactische review.

Aanroep: python ai_doc_review.py <changed_files.txt> <output.md>

Voorwaarden:
- ANTHROPIC_API_KEY in de omgeving.
- `anthropic` SDK >= 0.40 geinstalleerd.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from anthropic import Anthropic

MODEL = "claude-sonnet-4-6"
MAX_FILES = 20
MAX_CHARS_PER_FILE = 12_000

SYSTEM_PROMPT = """Je bent een didactische redacteur voor Coderius College documentatie.
Doelgroep: middelbare scholieren die net beginnen met programmeren.
Taal: Nederlands.

Je toetst gewijzigde lespagina's tegen de schrijfgids en het PRIMM-model.

**Schrijfgids samengevat:**
- Stem: vriendelijk, direct, "je" (nooit "u"), geen uitroeptekens, geen vulwoorden
  (eigenlijk, gewoon, simpelweg, even, toch).
- Lengte: kort en concreet, een concept per paragraaf, geen samenvatting aan het einde.
- Voorbeeld voor abstractie: eerst werkende code, daarna definitie.
- Code: compleet en runnable, begint met `import`, Nederlandse variabelen
  (cirkel, blok, kopie), Engelse keywords en methodenamen.
- Opdrachten: korte beschrijving, tip in <details>, oplossing in tweede <details>.
- Cognitive load: maximaal 1-2 nieuwe concepten per pagina.
- Hoofdstuktitels `# <H>.<S> Titel`, opdrachten `## Opdracht <H>.<S>.<letter>: ...`.

**Jouw output:** een markdown PR-comment met:
1. Een korte intro (1 zin).
2. Per gewijzigd bestand een tabel met cijfers (1-10) voor:
   Toon | PRIMM | Cognitive load | Opdracht-scaffolding | Code-kwaliteit
3. Per bestand 1-3 concrete verbeterpunten (citeer regels of secties).
4. Een totaalcijfer (1-10) onderaan.

Geef geen complimenten zonder onderbouwing. Wees specifiek en kort.
"""

USER_TEMPLATE = """Hieronder de gewijzigde lespagina's. Beoordeel ze volgens de schrijfgids.

{files}
"""


def read_files(list_path: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in list_path.read_text().splitlines():
        path = line.strip()
        if not path:
            continue
        p = Path(path)
        if not p.exists() or not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if len(content) > MAX_CHARS_PER_FILE:
            content = content[:MAX_CHARS_PER_FILE] + "\n\n... [afgekapt voor review] ..."
        out.append((path, content))
        if len(out) >= MAX_FILES:
            break
    return out


def build_user_message(files: list[tuple[str, str]]) -> str:
    blocks = []
    for path, content in files:
        blocks.append(f"### `{path}`\n\n```markdown\n{content}\n```\n")
    return USER_TEMPLATE.format(files="\n".join(blocks))


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: ai_doc_review.py <changed_files.txt> <output.md>", file=sys.stderr)
        return 2

    list_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    files = read_files(list_path)
    if not files:
        out_path.write_text("")
        print("Geen leesbare bestanden gevonden.")
        return 0

    client = Anthropic()
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_message(files)}],
    )

    parts = [b.text for b in message.content if getattr(b, "type", "") == "text"]
    review = "\n".join(parts).strip()
    if not review:
        out_path.write_text("")
        print("Claude gaf een lege response.")
        return 0

    header = (
        "## AI Docs Review (Claude)\n\n"
        f"_Geautomatiseerde beoordeling op basis van {len(files)} gewijzigd(e) bestand(en)._ "
        f"_Model: `{MODEL}`._\n\n"
    )
    out_path.write_text(header + review + "\n")
    print(f"Review geschreven naar {out_path} ({len(review)} chars).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
