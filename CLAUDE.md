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
`xltabular`, `tcolorbox`, `xurl`, `enumitem`, `newunicodechar` (texlive-latex-extra).
Page layout defaults to compact **A4 / 10pt / 2cm margins** (to save paper when
students print); override with `--paper {a4,letter} --fontsize {10,11,12} --margin
<len>`. `report` supports only 10/11/12pt — 10.5 would need a KOMA class.
The full reader is ~480 pages (was ~630 before the compact layout) / hundreds of
images and takes minutes per pass;
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
- Course reader: `reader/UCSCICOG11_Cognitive_Neuroscience_I_Reader.xml` — 12
  neuroscience chapters + the imported Evolution chapter + Methods (~482-page A4 PDF
  at the compact 10pt layout).
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
