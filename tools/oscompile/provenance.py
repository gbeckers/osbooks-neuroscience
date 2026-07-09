"""Generate the reader's provenance appendix (LaTeX).

Two data sources, so the appendix can't drift from reality:

  * the Workspace's per-source metadata -> "Sources & Attribution" (who made it,
    under what license, how many modules used) -- this is what keeps the reader
    CC-compliant (attribution + same-license + indicating changes).
  * `git diff upstream/main -- modules/` -> "Modifications to the original text"
    (exactly which neuroscience modules you edited), optionally enriched with the
    plain-English notes in reader/errata.md.

Emitted as a final unnumbered chapter and appended by build_latex.py.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .latex import heading, escape
from .sources import Workspace

# Cells that mean "nothing here" in an errata table; dropped rather than rendered.
_EMPTY_CELL = {"", "—", "–", "-", "n/a", "none"}


def _typeset(cell: str) -> str:
    """Light typographic cleanup of an errata cell before LaTeX-escaping, so a
    change reads like prose rather than source notation: collapse whitespace,
    turn ASCII ``->`` into a real arrow, and straighten quotes into curly ones.
    The arrow/quote codepoints pass through ``escape`` untouched (the preamble
    maps → to \\rightarrow; Latin Modern has the curly quotes)."""
    cell = re.sub(r"\s+", " ", cell).strip()
    cell = cell.replace("->", "→")
    out, open_q = [], True
    for ch in cell:
        if ch == '"':
            out.append("“" if open_q else "”")
            open_q = not open_q
        else:
            out.append(ch)
    return "".join(out).replace("'", "’")


def _format_errata_row(cells: list[str]) -> str:
    """Render one errata table row as an itemize item. Empty cells are dropped;
    the template's trailing OpenStax errata-id column, when a bare number, is
    spelled out instead of left as a dangling digit string."""
    parts = []
    for i, raw in enumerate(cells):
        cell = _typeset(raw)
        if cell.lower() in _EMPTY_CELL:
            continue
        if i == len(cells) - 1 and re.fullmatch(r"#?\d+", cell):
            parts.append("OpenStax erratum \\#" + cell.lstrip("#"))
        else:
            parts.append(escape(cell))
    return " — ".join(parts)


def _git_changed_modules(repo_root: Path, upstream: str = "upstream/main") -> list[str] | None:
    """Module ids whose files differ from upstream. None if git/upstream unavailable."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--name-only", upstream, "--", "modules/"],
            capture_output=True, text=True,
        )
    except OSError:
        return None
    if r.returncode != 0:
        return None
    ids = set()
    for line in r.stdout.splitlines():
        parts = line.split("/")
        if len(parts) >= 2 and parts[0] == "modules":
            ids.add(parts[1])
    return sorted(ids)


def _errata_rows(paths: list[Path]) -> list[list[str]]:
    """Real (non-placeholder) rows from each errata.md table, as cell lists.

    Reads several files (the top-level reader/errata.md plus the collection-local
    one, if any) and concatenates their rows, deduplicating identical rows so a
    note that appears in both files is only listed once.
    """
    rows: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for path in paths:
        if not path.exists():
            continue
        in_comment = False
        for line in path.read_text(encoding="utf-8").splitlines():
            # Skip HTML comment blocks (the file ships with a commented-out example row).
            if "<!--" in line:
                in_comment = True
            if in_comment:
                if "-->" in line:
                    in_comment = False
                continue
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            first = cells[0].lower()
            if not first or first.startswith(("module", "---", ":--")) or "none yet" in first:
                continue
            key = tuple(cells)
            if key in seen:
                continue
            seen.add(key)
            rows.append(cells)
    return rows


def generate_appendix(
    ws: Workspace,
    included_ids: set[str],
    module_titles: dict[str, str],
    repo_root: Path,
    collection_dir: Path | None = None,
) -> str:
    parts = [heading(0, "Provenance \\& Attribution", numbered=False, label="app:provenance")]

    # -- Sources ----------------------------------------------------------
    parts.append(heading(1, "Sources", numbered=False))
    used = []
    seen = set()
    for mid in included_ids:
        s = ws.source_of(mid)
        if s and id(s) not in seen:
            seen.add(id(s))
            used.append(s)
    used.sort(key=lambda s: (not s.is_upstream, s.name))

    parts.append("This reader is a derivative work assembled from the following sources. "
                 "Individual figures retain their original credit lines in their captions.\n")
    parts.append("\\begin{itemize}")
    for s in used:
        n = sum(1 for mid in included_ids if ws.source_of(mid) is s)
        bits = [f"\\textbf{{{escape(s.name)}}}"]
        if s.license:
            bits.append(f"licensed {escape(s.license)}")
        if s.origin:
            bits.append(f"\\url{{{s.origin}}}" if s.origin.startswith("http") else escape(s.origin))
        bits.append(f"{n} module{'s' if n != 1 else ''} used")
        parts.append("  \\item " + ", ".join(bits) + ".")
    parts.append("\\end{itemize}")

    # -- Modifications ----------------------------------------------------
    parts.append(heading(1, "Modifications to the original text", numbered=False))
    changed = _git_changed_modules(repo_root)
    if changed is None:
        parts.append("A list of corrections is unavailable because the \\texttt{upstream} "
                     "git remote is not configured.\n")
    else:
        changed_in_book = [m for m in changed if m in included_ids]
        if not changed_in_book:
            parts.append("No changes have been made to the original OpenStax text in this reader.\n")
        else:
            parts.append("The following sections were corrected relative to the original "
                         "OpenStax text:\n")
            parts.append("\\begin{itemize}")
            for mid in changed_in_book:
                title = module_titles.get(mid, mid)
                parts.append(f"  \\item \\emph{{{escape(title)}}} (\\texttt{{{escape(mid)}}})")
            parts.append("\\end{itemize}")

        # The top-level reader/errata.md plus, for a topic collection, the
        # errata.md sitting next to that collection file.
        errata_paths = [repo_root / "reader" / "errata.md"]
        if collection_dir is not None:
            errata_paths.append(collection_dir / "errata.md")
        rows = _errata_rows(errata_paths)
        if rows:
            parts.append("\nDetails:\n\\begin{itemize}")
            for cells in rows:
                parts.append("  \\item " + _format_errata_row(cells))
            parts.append("\\end{itemize}")

    return "\n".join(parts) + "\n"
