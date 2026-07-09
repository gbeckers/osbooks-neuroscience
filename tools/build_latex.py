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

from oscompile.collection import parse_collection  # noqa: E402
from oscompile.latex import LatexConverter, CNXML_NS, MD_NS  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULES_DIR = REPO_ROOT / "modules"
MEDIA_DIR = REPO_ROOT / "media"

PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage{fontspec}
\usepackage[margin=1in]{geometry}
\usepackage{graphicx}
\usepackage{tabularx}
\usepackage{array}
\usepackage[most]{tcolorbox}
\usepackage{caption}
\usepackage{microtype}
\usepackage{hyperref}
\usepackage{url}
\hypersetup{colorlinks=true, linkcolor=blue!50!black, urlcolor=blue!50!black}

\graphicspath{{%(mediadir)s/}}
\captionsetup{labelformat=empty}

\newtcolorbox{featurebox}[1]{colback=gray!5, colframe=gray!55,
  title=#1, breakable, fonttitle=\bfseries}
\newtcolorbox{objectives}{colback=blue!4, colframe=blue!45,
  title=Learning Objectives, breakable, fonttitle=\bfseries}

\title{%(title)s}
\author{%(author)s}
\date{%(date)s}

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


def build(module_ids: list[str], title: str, author: str, out_path: Path) -> None:
    titles = all_module_titles()
    converter = LatexConverter(module_titles=titles, included_ids=set(module_ids))

    fragments = []
    for mid in module_ids:
        path = MODULES_DIR / mid / "index.cnxml"
        if not path.exists():
            print(f"  WARN: module {mid} not found, skipping", file=sys.stderr)
            continue
        fragments.append(converter.convert_module(path, mid))

    preamble = PREAMBLE % {
        "mediadir": MEDIA_DIR.as_posix(),
        "title": title,
        "author": author,
        "date": r"\today",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(preamble + "\n".join(fragments) + POSTAMBLE, encoding="utf-8")

    dropped = Counter(converter.dropped)
    print(f"Wrote {out_path}")
    print(f"  modules: {len(fragments)}   figures/tables labelled: {len(converter.labels)}")
    if dropped:
        summary = ", ".join(f"{n}x {k}" for k, n in dropped.items())
        print(f"  dropped interactive content: {summary}")
    print(f"\nCompile with:\n  cd {out_path.parent} && xelatex {out_path.name} && xelatex {out_path.name}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build a LaTeX reader from CNXML modules.")
    p.add_argument("collection", nargs="?", help="a *.collection.xml to build in full")
    p.add_argument("--modules", nargs="+", help="explicit module ids (overrides collection)")
    p.add_argument("--title", default="Course Reader")
    p.add_argument("--author", default="")
    p.add_argument("--out", default="build/reader.tex", type=Path)
    args = p.parse_args(argv)

    if args.modules:
        module_ids = args.modules
    elif args.collection:
        coll = parse_collection(args.collection)
        module_ids = [ref.document for ref in coll.module_refs()]
        if args.title == "Course Reader":
            args.title = coll.title
    else:
        p.error("provide a collection file or --modules")

    out = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    build(module_ids, args.title, args.author, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
