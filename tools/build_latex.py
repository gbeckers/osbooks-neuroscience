#!/usr/bin/env python3
"""Build a LaTeX/PDF course reader from OpenStax CNXML modules (prototype).

Examples
--------
Build chapter 2 (Neurophysiology) from an explicit module list:

    python3 tools/build_latex.py \
        --modules m00011 m00012 m00013 m00014 m00015 m00016 \
        --title "Chapter 2 — Neurophysiology" \
        --out build/chapter02.tex

Build everything in a collection file:

    python3 tools/build_latex.py collections/my-course.collection.xml \
        --out build/my-course.tex

Then compile (needs a TeX Live install with xelatex):

    cd build && xelatex chapter02.tex && xelatex chapter02.tex

xelatex is run twice so \\label/\\ref and the ToC resolve. Unicode in the source
(+/-, arrows, Greek, curly quotes) requires xelatex or lualatex, not pdflatex.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from oscompile.collection import parse_collection, Unit, ModuleRef  # noqa: E402
from oscompile.latex import LatexConverter, heading, CNXML_NS  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULES_DIR = REPO_ROOT / "modules"
MEDIA_DIR = REPO_ROOT / "media"

PREAMBLE = r"""\documentclass[11pt]{report}
\usepackage{fontspec}
\usepackage[margin=1in]{geometry}
\usepackage{graphicx}
\usepackage{tabularx}
\usepackage{xltabular}   % longtable + X columns: wide tables break across pages
\usepackage{array}
\usepackage[most]{tcolorbox}
\usepackage{caption}
\usepackage{hyperref}
\usepackage{xurl}   % break long URLs/DOIs anywhere (load after hyperref)
\hypersetup{colorlinks=true, linkcolor=blue!50!black, urlcolor=blue!50!black}
% microtype is deliberately omitted: on xelatex it only does character
% protrusion, which chokes on the newunicodechar-active Greek letters below
% ("Unknown slot number of character"). xurl + emergencystretch cover the
% justification instead.
\emergencystretch=3em  % soak up the last few unbreakable overfulls

% The main font (Latin Modern) has no text-mode Greek; map the codepoints the
% book uses (receptor/molecule names, units) to math-mode equivalents so they
% render instead of dropping out as "Missing character".
\usepackage{newunicodechar}
\newunicodechar{α}{\ensuremath{\alpha}}
\newunicodechar{β}{\ensuremath{\beta}}
\newunicodechar{γ}{\ensuremath{\gamma}}
\newunicodechar{δ}{\ensuremath{\delta}}
\newunicodechar{ε}{\ensuremath{\varepsilon}}
\newunicodechar{ζ}{\ensuremath{\zeta}}
\newunicodechar{η}{\ensuremath{\eta}}
\newunicodechar{θ}{\ensuremath{\theta}}
\newunicodechar{κ}{\ensuremath{\kappa}}
\newunicodechar{λ}{\ensuremath{\lambda}}
\newunicodechar{μ}{\ensuremath{\mu}}
\newunicodechar{ν}{\ensuremath{\nu}}
\newunicodechar{π}{\ensuremath{\pi}}
\newunicodechar{ρ}{\ensuremath{\rho}}
\newunicodechar{σ}{\ensuremath{\sigma}}
\newunicodechar{τ}{\ensuremath{\tau}}
\newunicodechar{φ}{\ensuremath{\varphi}}
\newunicodechar{χ}{\ensuremath{\chi}}
\newunicodechar{ψ}{\ensuremath{\psi}}
\newunicodechar{ω}{\ensuremath{\omega}}
\newunicodechar{Δ}{\ensuremath{\Delta}}
\newunicodechar{Σ}{\ensuremath{\Sigma}}
\newunicodechar{Ω}{\ensuremath{\Omega}}
\newunicodechar{Φ}{\ensuremath{\Phi}}
\newunicodechar{Ψ}{\ensuremath{\Psi}}
\newunicodechar{Γ}{\ensuremath{\Gamma}}
\newunicodechar{⋅}{\ensuremath{\cdot}}
\newunicodechar{׳}{'}   % Hebrew geresh used as an apostrophe in a reference
\newunicodechar{⅔}{2/3}
\newunicodechar{⅓}{1/3}
\newunicodechar{½}{1/2}

\graphicspath{{@@MEDIADIR@@/}}
\captionsetup{labelformat=empty}

\newtcolorbox{featurebox}[1]{colback=gray!5, colframe=gray!55,
  title={#1}, breakable, fonttitle=\bfseries}
\newtcolorbox{objectives}{colback=blue!4, colframe=blue!45,
  title=Learning Objectives, breakable, fonttitle=\bfseries}

\title{@@TITLE@@}
\author{@@AUTHOR@@}
\date{\today}

\begin{document}
\maketitle
\begin{center}\small
Adapted from \emph{Introduction to Behavioral Neuroscience} (OpenStax, Rice University),
licensed CC BY-NC-SA 4.0. This derivative is shared under the same license.
\end{center}
\tableofcontents
\newpage
"""

POSTAMBLE = "\n\\end{document}\n"


def module_title(module_id: str) -> str | None:
    path = MODULES_DIR / module_id / "index.cnxml"
    if not path.exists():
        return None
    try:
        root = ET.parse(path).getroot()
        t = root.find(f"{{{CNXML_NS}}}title")
        if t is not None and t.text:
            return t.text.strip()
    except ET.ParseError:
        return None
    return None


def all_module_titles() -> dict[str, str]:
    titles: dict[str, str] = {}
    for d in MODULES_DIR.iterdir():
        if d.is_dir() and (d / "index.cnxml").exists():
            t = module_title(d.name)
            if t:
                titles[d.name] = t
    return titles


def _render_nodes(nodes, converter: LatexConverter, level: int, stats: Counter) -> str:
    """Walk the collection tree. A Unit becomes a heading (chapter at level 0);
    a ModuleRef is converted with its title at the current level. Standalone
    top-level modules (the Preface, Methods) are unnumbered chapters."""
    out: list[str] = []
    for node in nodes:
        if isinstance(node, Unit):
            out.append(heading(level, escape_title(node.title)))
            out.append(_render_nodes(node.content, converter, level + 1, stats))
        else:  # ModuleRef
            path = MODULES_DIR / node.document / "index.cnxml"
            if not path.exists():
                print(f"  WARN: module {node.document} not found, skipping", file=sys.stderr)
                continue
            numbered = level > 0  # top-level standalone modules are unnumbered
            out.append(converter.convert_module(
                path, node.document, heading_level=level, numbered=numbered))
            stats["modules"] += 1
    return "\n".join(chunk for chunk in out if chunk.strip())


def escape_title(text: str) -> str:
    # Unit titles are plain strings from the collection metadata.
    from oscompile.latex import escape
    return escape(text)


def _module_paths(nodes) -> list[Path]:
    """All module index.cnxml paths in the tree, in reading order."""
    paths: list[Path] = []
    for node in nodes:
        if isinstance(node, Unit):
            paths.extend(_module_paths(node.content))
        else:  # ModuleRef
            p = MODULES_DIR / node.document / "index.cnxml"
            if p.exists():
                paths.append(p)
    return paths


def build(nodes, included_ids: set[str], title: str, author: str, out_path: Path) -> None:
    titles = all_module_titles()
    converter = LatexConverter(module_titles=titles, included_ids=included_ids)

    # Index every figure/table id up front so cross-references resolve regardless
    # of module order (e.g. a link to a figure in a later module of the chapter).
    converter.prescan_labels(_module_paths(nodes))

    stats: Counter = Counter()
    body = _render_nodes(nodes, converter, level=0, stats=stats)

    preamble = (PREAMBLE
                .replace("@@MEDIADIR@@", MEDIA_DIR.as_posix())
                .replace("@@TITLE@@", title)
                .replace("@@AUTHOR@@", author))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(preamble + body + POSTAMBLE, encoding="utf-8")

    dropped = Counter(converter.dropped)
    print(f"Wrote {out_path}")
    print(f"  modules: {stats['modules']}   figures/tables labelled: {len(converter.labels)}")
    if dropped:
        summary = ", ".join(f"{n}x {k}" for k, n in dropped.items())
        print(f"  dropped interactive content: {summary}")
    print(f"\nCompile with:\n  cd {out_path.parent} && xelatex {out_path.name} && xelatex {out_path.name}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build a LaTeX reader from CNXML modules.")
    p.add_argument("collection", nargs="?", help="a *.collection.xml to build in full")
    p.add_argument("--modules", nargs="+", help="explicit module ids (wrapped in one chapter)")
    p.add_argument("--title", default="Course Reader")
    p.add_argument("--author", default="")
    p.add_argument("--out", default="build/reader.tex", type=Path)
    args = p.parse_args(argv)

    if args.modules:
        # Ad-hoc build: group the given modules under a single chapter.
        nodes = [Unit(title=args.title, content=[ModuleRef(document=m) for m in args.modules])]
        included_ids = set(args.modules)
    elif args.collection:
        coll = parse_collection(args.collection)
        nodes = coll.content
        included_ids = coll.module_ids()
        if args.title == "Course Reader":
            args.title = coll.title
    else:
        p.error("provide a collection file or --modules")

    out = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    build(nodes, included_ids, args.title, args.author, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
