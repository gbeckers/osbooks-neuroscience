# tools/ — building a custom print book from the CNXML sources

Dependency-free (Python 3 standard library only). No `pip install` needed.

## What's here

- `oscompile/collection.py` — parse a `*.collection.xml` table of contents into a
  tree of units (`Unit`) and module references (`ModuleRef`).
- `oscompile/module.py` — parse one `index.cnxml` and index its title, element
  ids, image references, links, and iframes.
- `oscompile/sources.py` — a `Workspace` that discovers every content source (the
  neuroscience root plus each `sources/<name>/`), resolves a module id to a file,
  and flags id/media collisions. Both tools resolve modules through this.
- `oscompile/validate.py` — cross-check a collection against all sources.
- `oscompile/latex.py` — CNXML → LaTeX converter.
- `oscompile/provenance.py` — generate the "Provenance & Attribution" appendix
  from source metadata + `git diff upstream/main` + `reader/errata.md`.
- `validate.py` — convenience CLI wrapper to run from the repo root.

## Validate a collection

```bash
# The full book (baseline: 0 errors expected)
python3 tools/validate.py

# A custom course subset
python3 tools/validate.py reader/my-course.collection.xml

# Also list media files no included module uses (pruning candidates)
python3 tools/validate.py reader/my-course.collection.xml --orphans
```

Exit code is non-zero if there are any ERRORs, so it drops into CI/Make cleanly.

### What it reports

- **ERROR** — will produce broken output: a listed module isn't found in **any**
  source; an `<image src>` isn't on disk; an intra-module figure link (`target-id`)
  resolves to nothing; a cross-module link points at a module not on disk; the same
  id is defined in two sources (`id-collision`).
- **WARN** — builds, but check it: a cross-module link points at a module **not in
  this collection** (`dangling-xref` — the classic "I dropped that chapter" case);
  a cross-module `target-id` is absent in the target; a module is included twice;
  a media filename exists in two sources (`media-collision`); `os-embed` exercises
  / iframes (interactive content that can't print).
- **INFO** — external web links; with `--orphans`, unreferenced media (across all
  sources).

## Build a LaTeX/PDF reader (prototype)

`oscompile/latex.py` converts CNXML modules to LaTeX; `build_latex.py` wraps them
in a preamble and writes a `.tex` under `build/` (git-ignored).

```bash
# Prototype: chapter 2 (Neurophysiology) from an explicit module list
python3 tools/build_latex.py \
  --modules m00011 m00012 m00013 m00014 m00015 m00016 \
  --title "Chapter 2 — Neurophysiology" \
  --out build/chapter02.tex

# ...or build a whole collection file
python3 tools/build_latex.py reader/my-course.collection.xml --out build/my-course.tex

# Compile (needs TeX Live with xelatex; run twice for refs + ToC)
cd build && xelatex chapter02.tex && xelatex chapter02.tex
```

Page layout defaults to **A4, 10pt, 2 cm margins** (compact, to cut paper use when
students print). Override with `--paper {a4,letter}`, `--fontsize {10,11,12}`
(`report` supports those three only), and `--margin <length>` (e.g. `--margin 1in`).

**Use xelatex or lualatex, not pdflatex** — the source has Unicode (±, –, →, Greek,
curly quotes) that pdflatex won't handle.

What the converter does:
- **Structure** (`report` class): each collection unit → a numbered `\chapter`
  (so Neurophysiology = Chapter 2, matching the source's figure numbering), each
  module → a `\section`, module sub-sections → `\subsection`/`\subsubsection`.
  Standalone top-level modules (Preface, Methods) → unnumbered chapters. In
  `--modules` mode the given modules are grouped under a single chapter (`--title`).
- Figure/table **numbers come from the element id** (`Image-2.24` → "Figure 2.24"),
  not LaTeX counters, so numbering matches the source even in a subset. Empty
  `<link target-id=.../>` refs become **clickable** "Figure 2.16"/"Table 2.24"
  links (`\hyperlink`/`\hypertarget`, so the id-based numbers are preserved). A
  pre-scan indexes every id first, so a reference resolves even when its target is
  in a later module of the same chapter.
- Cross-*module* prose links → "(see \emph{Title})", clickable to that chapter
  when it's in the build.
- **Tables** break across pages via `xltabular` (longtable + `X` columns), with the
  header repeated on each page; tables inside note boxes stay non-breaking
  (`tabularx`), since a longtable can't live in a box.
- `note` blocks → titled boxes (Meet the Author / In the Lab / In the Wild / …).
- `learning-objectives` → a highlighted box.
- `sup`/`sub` (ion charges), `emphasis`, `term`, small MathML (`mfrac`, `msup`…).
- **Drops** interactive content (`os-embed` exercises, `iframe` videos) and prints
  a summary of what was dropped.
- **Multi-source**: modules are resolved across the neuroscience root and every
  `sources/<name>/` (each source's `media/` is added to `\graphicspath`).
- **Provenance appendix** (final unnumbered chapter, on by default; `--no-appendix`
  to omit): a "Sources & Attribution" list built from each source's license/origin,
  and a "Modifications to the original text" list from `git diff upstream/main`,
  enriched with any notes in `reader/errata.md`.

Requires a TeX Live install with `xltabular`, `tcolorbox`, `xurl`, `newunicodechar`
(all in `texlive-latex-extra`). Known limit: a few sub-visible overfull lines in
narrow bold table headers.

## Authoring a course subset

1. Copy `collections/introduction-behavioral-neuroscience.collection.xml` to a new
   `reader/<your-course>.collection.xml`.
2. Delete the `<col:module>` / `<col:subcollection>` entries you don't teach.
3. For a **partial chapter**, copy `modules/mXXXXX` to a new id (e.g. `m90001`),
   delete the `<section>`s you don't use, and reference the new id.
4. Run the validator and resolve `dangling-xref` warnings (drop the link, turn it
   into plain text, or add the referenced module back).

See `reader/example-course-subset.collection.xml` for a worked example that
intentionally triggers dangling-xref warnings.
