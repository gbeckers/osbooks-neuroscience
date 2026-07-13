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

    python3 tools/build_latex.py reader/my-course.collection.xml \
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
from oscompile.sources import Workspace, discover_workspace  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

PREAMBLE = r"""\documentclass[@@FONTSIZE@@pt@@CLASSOPTS@@]{@@CLASS@@}
\usepackage{fontspec}
\usepackage[@@PAPER@@paper,margin=@@MARGIN@@]{geometry}
@@TWOCOLUMN@@
\usepackage{graphicx}
\usepackage{amsmath}   % \text{...} for MathML <m:mtext> (words inside equations)
% Libertinus for the text: a humanist serif that stays solid at small sizes on
% screen (this reader is read on screen as much as printed), unlike Computer
% Modern's thin strokes. We set only the *text* fonts here, deliberately NOT the
% math font: unicode-math (which Libertinus Math needs) makes Unicode Greek
% math-active and so breaks this book's pervasive inline *text* Greek (alpha/beta
% receptors) -- it renders text alpha via the math-plane glyph the text font
% lacks. Instead math stays Computer Modern and the \newunicodechar maps below
% route each Greek letter to the text glyph in text and the math command in math.
\setmainfont{Libertinus Serif}
\setsansfont{Libertinus Sans}
\setmonofont{Libertinus Mono}
\usepackage{tabularx}
\usepackage{xltabular}   % longtable + X columns: wide tables break across pages
\usepackage{array}
\usepackage[most]{tcolorbox}
\usepackage{enumitem}   % [label=...] for lettered multiple-choice options
\usepackage{caption}
\usepackage{hyperref}
\usepackage{xurl}   % break long URLs/DOIs anywhere (load after hyperref)
\hypersetup{colorlinks=true, linkcolor=blue!50!black, urlcolor=blue!50!black}
% microtype is deliberately omitted: on xelatex it only does character
% protrusion, which chokes on the newunicodechar-active symbols below
% ("Unknown slot number of character"). xurl + emergencystretch cover the
% justification instead.
\emergencystretch=3em  % soak up the last few unbreakable overfulls

% Greek is context-sensitive: in text (receptor/molecule names, units) it renders
% as the upright Libertinus glyph, which the text font carries -- \char"XXXX pulls
% the codepoint from the current (Libertinus) font, so it follows bold/italic. In
% math (equations from MathML) it renders as the Computer Modern math command,
% since math stays CM. \relax terminates the hex constant so a following digit
% (e.g. the 7 in "alpha7") isn't swallowed into it.
\usepackage{newunicodechar}
\newcommand{\tg}[2]{\ifmmode#1\else\char"#2\relax\fi}   % text glyph / math command
\newunicodechar{α}{\tg{\alpha}{03B1}}
\newunicodechar{β}{\tg{\beta}{03B2}}
\newunicodechar{γ}{\tg{\gamma}{03B3}}
\newunicodechar{δ}{\tg{\delta}{03B4}}
\newunicodechar{ε}{\tg{\varepsilon}{03B5}}
\newunicodechar{ζ}{\tg{\zeta}{03B6}}
\newunicodechar{η}{\tg{\eta}{03B7}}
\newunicodechar{θ}{\tg{\theta}{03B8}}
\newunicodechar{κ}{\tg{\kappa}{03BA}}
\newunicodechar{λ}{\tg{\lambda}{03BB}}
\newunicodechar{μ}{\tg{\mu}{03BC}}
\newunicodechar{ν}{\tg{\nu}{03BD}}
\newunicodechar{π}{\tg{\pi}{03C0}}
\newunicodechar{ρ}{\tg{\rho}{03C1}}
\newunicodechar{σ}{\tg{\sigma}{03C3}}
\newunicodechar{τ}{\tg{\tau}{03C4}}
\newunicodechar{φ}{\tg{\varphi}{03C6}}
\newunicodechar{χ}{\tg{\chi}{03C7}}
\newunicodechar{ψ}{\tg{\psi}{03C8}}
\newunicodechar{ω}{\tg{\omega}{03C9}}
\newunicodechar{Δ}{\tg{\Delta}{0394}}
\newunicodechar{Σ}{\tg{\Sigma}{03A3}}
\newunicodechar{Ω}{\tg{\Omega}{03A9}}
\newunicodechar{Φ}{\tg{\Phi}{03A6}}
\newunicodechar{Ψ}{\tg{\Psi}{03A8}}
\newunicodechar{Γ}{\tg{\Gamma}{0393}}
\newunicodechar{⋅}{\ensuremath{\cdot}}
\newunicodechar{→}{\ensuremath{\rightarrow}}
\newunicodechar{⇔}{\ensuremath{\Leftrightarrow}}
\newunicodechar{−}{\ensuremath{-}}   % U+2212 MINUS SIGN (not the ASCII hyphen)
\newunicodechar{≠}{\ensuremath{\neq}}
\newunicodechar{≈}{\ensuremath{\approx}}
\newunicodechar{∞}{\ensuremath{\infty}}
\newunicodechar{׳}{'}   % Hebrew geresh used as an apostrophe in a reference
\newunicodechar{⅔}{2/3}
\newunicodechar{⅓}{1/3}
\newunicodechar{½}{1/2}
% Circled letters (U+24D0-) label exercise sub-parts in the algebra source; no
% text font carries them, so draw the circle ourselves. Font-independent.
\newcommand{\circledlabel}[1]{\textcircled{\scriptsize #1}}
\newunicodechar{ⓐ}{\circledlabel{a}}
\newunicodechar{ⓑ}{\circledlabel{b}}
\newunicodechar{ⓒ}{\circledlabel{c}}
\newunicodechar{ⓓ}{\circledlabel{d}}
\newunicodechar{ⓔ}{\circledlabel{e}}
\newunicodechar{ⓕ}{\circledlabel{f}}
\newunicodechar{ⓖ}{\circledlabel{g}}
\newunicodechar{ⓗ}{\circledlabel{h}}

\graphicspath{@@GRAPHICSPATH@@}
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
\setcounter{tocdepth}{1}   % ToC lists chapters + modules, not every subsection
\tableofcontents
\newpage
"""

POSTAMBLE = "\n\\end{document}\n"


def all_module_titles(ws: Workspace) -> dict[str, str]:
    titles: dict[str, str] = {}
    for module_id, (_src, path) in ws.index.items():
        try:
            root = ET.parse(path).getroot()
            t = root.find(f"{{{CNXML_NS}}}title")
            if t is not None and t.text:
                titles[module_id] = t.text.strip()
        except ET.ParseError:
            continue
    return titles


def _render_nodes(nodes, converter: LatexConverter, level: int, stats: Counter, ws: Workspace) -> str:
    """Walk the collection tree. A Unit becomes a heading (chapter at level 0);
    a ModuleRef is converted with its title at the current level. Standalone
    top-level modules (the Preface, Methods) are unnumbered chapters."""
    out: list[str] = []
    for node in nodes:
        if isinstance(node, Unit):
            out.append(heading(level, escape_title(node.title)))
            out.append(_render_nodes(node.content, converter, level + 1, stats, ws))
        else:  # ModuleRef
            path = ws.resolve(node.document)
            if path is None:
                print(f"  WARN: module {node.document} not found in any source, skipping",
                      file=sys.stderr)
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


def _module_paths(nodes, ws: Workspace) -> list[Path]:
    """All resolved module index.cnxml paths in the tree, in reading order."""
    paths: list[Path] = []
    for node in nodes:
        if isinstance(node, Unit):
            paths.extend(_module_paths(node.content, ws))
        else:  # ModuleRef
            p = ws.resolve(node.document)
            if p is not None:
                paths.append(p)
    return paths


# report only ships 10/11/12pt base sizes; 10.5 would need a KOMA class.
PAPER_OPTS = {"a4": "a4", "letter": "letter"}


def build(nodes, included_ids: set[str], title: str, author: str, out_path: Path,
          ws: Workspace, appendix: bool = True, collection_dir: Path | None = None,
          paper: str = "a4", fontsize: str = "9", margin: str = "1.5cm",
          two_column: bool = True) -> None:
    titles = all_module_titles(ws)
    converter = LatexConverter(module_titles=titles, included_ids=included_ids,
                               two_column=two_column)

    # Index every figure/table id up front so cross-references resolve regardless
    # of module order (e.g. a link to a figure in a later module of the chapter).
    converter.prescan_labels(_module_paths(nodes, ws))

    stats: Counter = Counter()
    body = _render_nodes(nodes, converter, level=0, stats=stats, ws=ws)

    # Every source's media dir goes on the graphics path, in source order.
    graphicspath = "".join(f"{{{d.as_posix()}/}}" for d in ws.media_dirs())
    # report ships only 10/11/12pt; 8/9pt (for narrow two-column lines) needs the
    # extsizes drop-in extreport. twocolumn is a class option; cuted gives wide
    # tables a full-width band via \begin{strip} (see LatexConverter._table).
    klass = "report" if fontsize in {"10", "11", "12"} else "extreport"
    class_opts = ",twocolumn" if two_column else ""
    twocol_pkgs = (
        "\\usepackage{cuted}   % \\begin{strip}: full-page-width bands in 2 columns\n"
        "\\setlength{\\columnsep}{16pt}\n" if two_column else "")
    preamble = (PREAMBLE
                .replace("@@GRAPHICSPATH@@", graphicspath)
                .replace("@@PAPER@@", PAPER_OPTS[paper])
                .replace("@@FONTSIZE@@", fontsize)
                .replace("@@CLASS@@", klass)
                .replace("@@CLASSOPTS@@", class_opts)
                .replace("@@TWOCOLUMN@@", twocol_pkgs)
                .replace("@@MARGIN@@", margin)
                .replace("@@TITLE@@", escape_title(title))
                .replace("@@AUTHOR@@", escape_title(author)))
    if appendix:
        from oscompile.provenance import generate_appendix
        body += "\n" + generate_appendix(ws, included_ids, titles, REPO_ROOT, collection_dir)

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
    p.add_argument("--paper", choices=sorted(PAPER_OPTS), default="a4",
                   help="page size (default: a4; students print on A4)")
    p.add_argument("--fontsize", choices=["8", "9", "10", "11", "12"], default="9",
                   help="base font size in pt (default: 9, to suit two-column's narrow "
                        "lines; 8/9 switch report->extreport)")
    p.add_argument("--onecolumn", dest="twocolumn", action="store_false",
                   help="single-column layout; the default is two-column (narrower "
                        "lines -> smaller font -> ~half the pages / print cost)")
    p.add_argument("--margin", default="1.5cm",
                   help="page margin, any LaTeX length (default: 1.5cm)")
    p.add_argument("--no-appendix", dest="appendix", action="store_false",
                   help="omit the auto-generated provenance & attribution appendix")
    args = p.parse_args(argv)

    collection_dir: Path | None = None
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
        collection_dir = Path(args.collection).resolve().parent
    else:
        p.error("provide a collection file or --modules")

    out = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    ws = discover_workspace(REPO_ROOT)
    build(nodes, included_ids, args.title, args.author, out, ws,
          appendix=args.appendix, collection_dir=collection_dir,
          paper=args.paper, fontsize=args.fontsize, margin=args.margin,
          two_column=args.twocolumn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
