# CLAUDE.md

A fork of OpenStax `osbooks-neuroscience` extended with tooling that compiles a
**custom, printable course reader** from OpenStax CNXML sources: selected
chapters/modules of the neuroscience book, modules imported from *other* OpenStax
books, in-place errata fixes, and an auto-generated provenance/attribution
appendix. Output is a LaTeX → xelatex PDF.

## Layout
- `modules/`, `media/`, `collections/` — the neuroscience **upstream**, synced via
  `git merge upstream/main`. Edit these *only* for errata (in place).
- `sources/<name>/` — content from other origins; one dir each with `modules/`,
  `media/`, and a `SOURCE.md` manifest. Module ids are source-prefixed (e.g.
  `bio-m45486`) to stay globally unique. See `sources/README.md`.
- `reader/` — the course definition: a `*.collection.xml` table of contents plus
  `errata.md`. See `reader/README.md`.
- `tools/` — dependency-free (stdlib-only) Python build/validate pipeline. See
  `tools/README.md`.
- `build/` — generated `.tex`/`.pdf` (git-ignored).

## Workflow
```
python3 tools/validate.py   reader/<course>.collection.xml            # refs/collisions
python3 tools/build_latex.py reader/<course>.collection.xml --title "…" --out build/x.tex
cd build && xelatex x.tex && xelatex x.tex                            # twice: ToC/refs
```
Use **xelatex** (not pdflatex — the source has Unicode). Needs TeX Live with
`xltabular`, `tcolorbox`, `xurl`, `enumitem`, `newunicodechar`, plus `extsizes`
(8/9pt `extreport`) and `cuted` (full-width `strip`) for the two-column layout —
all in texlive-latex-extra. Body text is **Libertinus** (Serif/Sans/Mono) — a
humanist OpenType serif that stays legible on screen at 9pt where Computer
Modern's thin strokes thin out; it must be installed as a **system font** (xelatex
finds it by name via fontspec). Math stays Computer Modern: `unicode-math` +
Libertinus Math would make Unicode Greek math-active and break the book's
pervasive *inline text* Greek (α/β receptors), so instead each Greek codepoint is
mapped (in `newunicodechar`) to the Libertinus text glyph in text and the CM math
command in equations.
Page layout defaults to compact **two-column A4 / 9pt / 1.5cm margins** (halves the
page count vs. the old single-column 10pt, to cut color-print cost when students
print). Two-column narrows lines so a smaller font stays readable; figures and
boxes reflow into a column automatically (they're emitted at `\linewidth`), and
tables become non-breaking `tabularx` — a `longtable` is illegal in twocolumn mode.
Wide (≥5-col) **or** image-bearing tables would be crushed in a ~8cm column, so they
break out to full page width via `cuted`'s `\begin{strip}`. Override with `--paper
{a4,letter} --fontsize {8,9,10,11,12} --margin <len>`, or `--onecolumn` for the old
single-column layout. `report` (single-column) supports only 10/11/12pt; 8/9pt
switches to `extreport`. The full reader is ~215 pages (was ~412 single-column) /
hundreds of images and takes minutes per pass;
run compiles in the background. If a run is killed it leaves a truncated `.toc` that
breaks the next run ("File ended while scanning \@writefile") — delete
`build/<name>.{aux,toc,out,log}` and recompile.

## Conventions
- **Importing a book**: copy its modules into `sources/<book>/modules/` with
  source-prefixed ids + their `media/`, write `SOURCE.md` (origin, pinned commit,
  license), reference the ids from a reader collection, run `validate.py`, and fix
  any id/media collisions it flags. Cross-module `<link document=…>` refs to
  non-included modules render as plain text — validate lists them as `dangling-xref`.
- **Errata**: edit the upstream module in place, commit with an `errata:` prefix;
  changes auto-appear in the provenance appendix (derived from `git diff
  upstream/main -- modules/`), enriched by rows in `reader/errata.md` **and** an
  `errata.md` sitting next to the collection being built (e.g.
  `reader/topics/<topic>/errata.md`). Appendix rows are typeset (`->` → arrow,
  straight quotes → curly, bare OpenStax id → "OpenStax erratum #N").
- **Upstream sync**: `git fetch upstream && git merge upstream/main`, then validate.

## Current state
- Course reader: `reader/UCSCICOG11_Cognitive_Neuroscience_I_Reader.xml` — 10
  neuroscience chapters + Methods (~215-page A4 PDF at the default two-column 9pt
  layout; was ~412 single-column).
- Per-class topic readers under `reader/topics/<topic>/` (a `*.collection.xml` plus
  its own `errata.md`), e.g. `reader/topics/neuroanatomy/` — lets each class get its
  own document. Neuroanatomy is a work in progress (more sources to be added).
- Imported source: `sources/biology/` — *Concepts of Biology* ch. 11 (Evolution).
- `main` is ahead of `origin/main` and unpushed (push from an interactive shell:
  `git push origin main`).

## Roadmap
- Import modules from OpenStax **Psychology** and **Anatomy & Physiology** into
  `sources/` (same recipe as biology).
- Optional polish: render dangling cross-chapter links as "see the chapter on *X*"
  instead of "see *Introduction*"; consider keeping/adapting biology review
  questions styling.
