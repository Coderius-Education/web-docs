#!/usr/bin/env python3
"""Coderius docs-linter: scoort gewijzigde lespagina's op de schrijfgids.

Aanroep: python docs_lint.py <changed_files.txt> <output.md>

Geen externe dependencies. Geen netwerkcalls. Pure regex + string-checks.

Categorieen (cijfer 1-10):
- Toon: 'u'/'uw', vulwoorden, uitroeptekens
- PRIMM-structuur: heading-discipline, code-voor-uitleg
- Cognitive load: zins- en paragraaflengte, aantal H2's
- Opdracht-scaffolding: tip + oplossing in <details>
- Code-kwaliteit: import-statements aanwezig, geen pseudo-code

Falen op fundamentele fouten (use 'u') verlaagt sterk; kleine afwijkingen
geven aftrek maar laten een redelijke baseline staan.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


VULWOORDEN = [
    "eigenlijk",
    "gewoon",
    "eenvoudigweg",
    "simpelweg",
    "juist",
]
INLEIDING_ANTIPATTERNS = [
    r"\bIn dit hoofdstuk\b",
    r"\bIn dit artikel\b",
    r"\bWe zullen\b",
    r"\bWe gaan\b",
    r"\bLaten we\b",
    r"\bZoals je waarschijnlijk al weet\b",
]
CODE_BLOCK_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]+`")
URL_RE = re.compile(r"https?://\S+")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
OPDRACHT_RE = re.compile(r"^##\s*Opdracht\b.*$", re.MULTILINE | re.IGNORECASE)
DETAILS_RE = re.compile(r"<details>(.*?)</details>", re.DOTALL | re.IGNORECASE)
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
ADMONITION_RE = re.compile(r":::(\w+)")


@dataclass
class FileReport:
    path: str
    scores: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    overall: int = 0


def strip_code(text: str) -> str:
    no_blocks = CODE_BLOCK_RE.sub(" ", text)
    no_inline = INLINE_CODE_RE.sub(" ", no_blocks)
    no_urls = URL_RE.sub(" ", no_inline)
    return no_urls


def grade_toon(text: str, prose: str, notes: list[str]) -> int:
    score = 10
    u_hits = len(re.findall(r"\b[Uu]w?\b", prose))
    if u_hits:
        score -= min(5, u_hits)
        notes.append(
            f"Toon: 'u' of 'uw' gevonden ({u_hits}x). Gebruik consequent **je** / **jouw**."
        )

    vulwoord_hits: list[tuple[str, int]] = []
    for w in VULWOORDEN:
        n = len(re.findall(rf"\b{w}\b", prose, flags=re.IGNORECASE))
        if n:
            vulwoord_hits.append((w, n))
    if vulwoord_hits:
        total = sum(n for _, n in vulwoord_hits)
        score -= min(3, total)
        formatted = ", ".join(f"{w} ({n}x)" for w, n in vulwoord_hits)
        notes.append(f"Toon: vulwoorden — {formatted}. Schrappen levert directere zinnen op.")

    excl_hits = len(re.findall(r"!", prose))
    if excl_hits > 2:
        score -= min(2, (excl_hits - 2))
        notes.append(
            f"Toon: {excl_hits} uitroeptekens. Energie zonder uitroeptekens werkt beter."
        )

    intro_hits = []
    for pat in INLEIDING_ANTIPATTERNS:
        if re.search(pat, prose):
            intro_hits.append(pat.strip(r"\b"))
    if intro_hits:
        score -= min(2, len(intro_hits))
        notes.append(
            "Toon: inleiding-clichés — "
            + ", ".join(intro_hits)
            + ". Begin direct met een voorbeeld of definitie."
        )

    return max(1, score)


REFERENCE_FILENAMES = {
    "cheatsheet",
    "over",
    "intro",
    "index",
    "readme",
    "meer-leren",
    "niet-gevonden",
    "veelgemaakte-fouten",
    "verbeteringen",
}


def is_lesson_page(path: Path, text: str) -> bool:
    """Lespagina's hebben een genummerde H1 (3.1, 4.2, ...). Referentie- en
    info-pagina's (cheatsheet, intro, over) zijn expliciet uitgezonderd in de
    schrijfgids en krijgen geen aftrek op H1-format."""
    stem = path.stem.lower()
    if stem in REFERENCE_FILENAMES:
        return False
    fm = FRONTMATTER_RE.match(text)
    if fm and ("displayed_sidebar: null" in fm.group(1) or "hide_pagination: true" in fm.group(1)):
        return False
    return True


def grade_primm(text: str, prose: str, path: Path, notes: list[str]) -> int:
    score = 10
    headings = HEADING_RE.findall(text)
    if not headings:
        return 7

    first_h1 = next((h for lvl, h in headings if len(lvl) == 1), None)
    if first_h1 and is_lesson_page(path, text):
        if not re.match(r"^\d+\.\d+\s+\S+", first_h1.strip()):
            score -= 2
            notes.append(
                f"PRIMM: H1 '{first_h1[:60]}' volgt geen '<H>.<S> Titel' format."
            )

    code_blocks = CODE_BLOCK_RE.findall(text)
    if code_blocks:
        first_code_idx = text.find("```")
        first_def_idx = re.search(r"\b(is een|betekent|definieert|kun je)\b", prose)
        if first_def_idx and first_code_idx >= 0:
            def_pos_in_full = text.find(first_def_idx.group(0))
            if def_pos_in_full > -1 and def_pos_in_full < first_code_idx - 200:
                score -= 2
                notes.append(
                    "PRIMM: definitie komt ruim voor het eerste code-voorbeeld. "
                    "Toon eerst werkende code, daarna de uitleg."
                )

    has_opdrachten = bool(OPDRACHT_RE.search(text))
    if has_opdrachten and not code_blocks:
        score -= 2
        notes.append("PRIMM: opdracht aanwezig zonder code-voorbeeld eraan voorafgaand.")

    return max(1, score)


def grade_cognitive_load(text: str, prose: str, notes: list[str]) -> int:
    score = 10
    h2s = [h for lvl, h in HEADING_RE.findall(text) if len(lvl) == 2]
    if len(h2s) > 8:
        score -= 2
        notes.append(
            f"Cognitive load: {len(h2s)} H2-secties. Splits pagina als meer dan ~1-2 concepten."
        )

    paragraphs = [p.strip() for p in prose.split("\n\n") if p.strip() and not p.strip().startswith("#")]
    if paragraphs:
        long_paras = [p for p in paragraphs if len(p.split()) > 80]
        if long_paras:
            score -= min(2, len(long_paras))
            notes.append(
                f"Cognitive load: {len(long_paras)} paragraaf/paragrafen > 80 woorden. Kortere stukken zijn beter te volgen."
            )

    sentences = re.split(r"(?<=[.!?])\s+", prose)
    long_sentences = [s for s in sentences if len(s.split()) > 30]
    if long_sentences:
        score -= min(2, len(long_sentences) // 3)
        if len(long_sentences) > 2:
            notes.append(
                f"Cognitive load: {len(long_sentences)} zinnen > 30 woorden. Splits voor leesbaarheid."
            )

    return max(1, score)


def grade_opdracht_scaffolding(text: str, notes: list[str]) -> int:
    opdrachten = list(OPDRACHT_RE.finditer(text))
    if not opdrachten:
        return 10

    score = 10
    missing_tip = 0
    missing_oplossing = 0
    for i, m in enumerate(opdrachten):
        start = m.start()
        end = opdrachten[i + 1].start() if i + 1 < len(opdrachten) else len(text)
        section = text[start:end]
        details_blocks = DETAILS_RE.findall(section)
        summaries = [
            re.search(r"<summary>(.*?)</summary>", b, re.DOTALL | re.IGNORECASE)
            for b in details_blocks
        ]
        summary_texts = [s.group(1).lower() if s else "" for s in summaries]
        has_tip = any(("tip" in s or "hint" in s) for s in summary_texts)
        has_oplossing = any(
            ("oplossing" in s or "antwoord" in s or "solution" in s) for s in summary_texts
        )
        if not has_tip:
            missing_tip += 1
        if not has_oplossing:
            missing_oplossing += 1

    if missing_oplossing:
        score -= min(5, missing_oplossing * 2)
        notes.append(
            f"Opdracht-scaffolding: {missing_oplossing} opdracht(en) zonder <details>-oplossing."
        )
    if missing_tip:
        score -= min(3, missing_tip)
        notes.append(
            f"Opdracht-scaffolding: {missing_tip} opdracht(en) zonder <details>-tip "
            "(optioneel maar gebruikelijk)."
        )
    return max(1, score)


def grade_code_kwaliteit(text: str, notes: list[str]) -> int:
    blocks = CODE_BLOCK_RE.findall(text)
    py_blocks = [body for lang, body in blocks if lang.lower() in ("python", "py")]
    if not py_blocks:
        return 10

    score = 10
    no_import = 0
    pseudo = 0
    for body in py_blocks:
        if re.search(r"\bimport\s+\w+", body) is None and "from " not in body:
            no_import += 1
        if re.search(r"#\s*\.\.\.|<\.\.\.>|\bpseudocode\b", body, re.IGNORECASE):
            pseudo += 1

    if no_import:
        ratio = no_import / len(py_blocks)
        if ratio > 0.5:
            score -= 3
            notes.append(
                f"Code-kwaliteit: {no_import}/{len(py_blocks)} Python-blokken zonder import. "
                "Voorbeelden horen runnable te zijn."
            )
        else:
            score -= 1

    if pseudo:
        score -= min(3, pseudo)
        notes.append(
            f"Code-kwaliteit: {pseudo} blok(ken) lijken pseudo-code (# ..., <...>). "
            "Liever complete kleine voorbeelden."
        )

    return max(1, score)


def lint_file(path: Path) -> FileReport:
    rep = FileReport(path=str(path))
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        rep.notes.append(f"Kon bestand niet lezen: {e}")
        rep.overall = 0
        return rep

    body = FRONTMATTER_RE.sub("", text, count=1)
    prose = strip_code(body)

    rep.scores["Toon"] = grade_toon(text, prose, rep.notes)
    rep.scores["PRIMM"] = grade_primm(text, prose, path, rep.notes)
    rep.scores["Cognitive load"] = grade_cognitive_load(text, prose, rep.notes)
    rep.scores["Opdracht-scaffolding"] = grade_opdracht_scaffolding(text, rep.notes)
    rep.scores["Code-kwaliteit"] = grade_code_kwaliteit(text, rep.notes)

    rep.overall = round(sum(rep.scores.values()) / len(rep.scores))
    return rep


def render_report(reports: list[FileReport]) -> str:
    if not reports:
        return ""

    lines = ["## Docs review (regelgebaseerd)", ""]
    lines.append(
        "_Geautomatiseerde check op basis van de Coderius schrijfgids. "
        "Cijfers zijn een indicatie, geen oordeel._"
    )
    lines.append("")
    lines.append("| Bestand | Toon | PRIMM | CogLoad | Opdracht | Code | **Totaal** |")
    lines.append("|---|:---:|:---:|:---:|:---:|:---:|:---:|")
    for r in reports:
        s = r.scores
        lines.append(
            f"| `{r.path}` | {s.get('Toon','-')} | {s.get('PRIMM','-')} | "
            f"{s.get('Cognitive load','-')} | {s.get('Opdracht-scaffolding','-')} | "
            f"{s.get('Code-kwaliteit','-')} | **{r.overall}** |"
        )

    avg = round(sum(r.overall for r in reports) / len(reports))
    lines.append("")
    lines.append(f"**Gemiddeld cijfer:** {avg}/10 over {len(reports)} bestand(en).")
    lines.append("")

    lines.append("### Verbeterpunten per bestand")
    lines.append("")
    for r in reports:
        if not r.notes:
            lines.append(f"<details><summary><code>{r.path}</code> — geen opmerkingen</summary>\n\nDeze pagina volgt de schrijfgids goed.\n\n</details>")
            continue
        lines.append(f"<details><summary><code>{r.path}</code> — {len(r.notes)} punt(en)</summary>\n")
        for n in r.notes:
            lines.append(f"- {n}")
        lines.append("\n</details>")
    lines.append("")
    lines.append(
        "_Deze check vervangt geen menselijke review. Regels zijn deterministisch — "
        "een lage score kan correct gemotiveerd zijn._"
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: docs_lint.py <changed_files.txt> <output.md>", file=sys.stderr)
        return 2

    list_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    paths: list[Path] = []
    for line in list_path.read_text().splitlines():
        s = line.strip()
        if not s:
            continue
        p = Path(s)
        if p.exists() and p.is_file():
            paths.append(p)

    if not paths:
        out_path.write_text("")
        print("Geen bestanden om te beoordelen.")
        return 0

    reports = [lint_file(p) for p in paths]
    out_path.write_text(render_report(reports))
    print(f"Review geschreven naar {out_path} ({len(reports)} bestand(en)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
