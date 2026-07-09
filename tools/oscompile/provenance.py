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

import subprocess
from pathlib import Path

from .latex import heading, escape
from .sources import Workspace


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


def _errata_rows(repo_root: Path) -> list[list[str]]:
    """Real (non-placeholder) rows from reader/errata.md's table, as cell lists."""
    path = repo_root / "reader" / "errata.md"
    if not path.exists():
        return []
    rows = []
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
        rows.append(cells)
    return rows


def generate_appendix(
    ws: Workspace,
    included_ids: set[str],
    module_titles: dict[str, str],
    repo_root: Path,
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

        rows = _errata_rows(repo_root)
        if rows:
            parts.append("\nDetails:\n\\begin{itemize}")
            for cells in rows:
                parts.append("  \\item " + " — ".join(escape(c) for c in cells if c))
            parts.append("\\end{itemize}")

    return "\n".join(parts) + "\n"
