# sources/ — content from origins other than the neuroscience upstream

The repo **root** (`modules/`, `media/`, `collections/`) is the OpenStax
*Introduction to Behavioral Neuroscience* upstream, synced via `git merge
upstream/main`. Everything from a **different** origin lives here instead, one
subdirectory per source, so provenance is obvious from location and upstream
merges never touch it.

```
sources/
├── <book-slug>/        e.g. osbooks-biology / an evolution book
│   ├── modules/        modules copied from that repo (see id rule below)
│   ├── media/          that source's figures
│   └── SOURCE.md       provenance manifest (copy SOURCE.template.md)
└── original/           your own new content (e.g. cortical architecture)
    ├── modules/
    ├── media/
    └── SOURCE.md
```

## Module id rule — prefix everything here

The neuroscience upstream owns ids like `m00021` and they **must not be renamed**
(that would break upstream merges). Other books reuse the same `m0000x` ids, so to
avoid collisions, **prefix module directory ids by source**:

- `sources/evolution/modules/evo-m00012/`
- `sources/original/modules/own-cortex-01/`

The prefix makes every id globally unique *and* advertises its origin. The course
collection in `reader/` then just references the unique id
(`<col:module document="evo-m00012"/>`).

## Authored LaTeX sections (`index.tex`)

OpenStax modules are CNXML, but CNXML is awkward to write by hand. For **your own**
short sections, a module directory may instead hold an **`index.tex`** — raw LaTeX
that the builder injects verbatim. (A directory with both files uses the CNXML.)

```
sources/authored/modules/authored-ions/index.tex
```

```latex
% title: Ions
An atom is normally electrically neutral…
\subsection{Cations and anions}
When an atom loses an electron…
\begin{itemize}
  \item Sodium (Na$^{+}$)…
\end{itemize}
```

- The optional first-line `% title: …` comment sets the section title. The
  **builder** emits the heading (`\section{…}` and a `\label{mod:<id>}`) at the
  right level, so numbering matches the OpenStax modules around it — write only the
  body, starting at `\subsection` for any internal structure.
- Everything else is plain LaTeX; the reader preamble already loads `amsmath`,
  `graphicx`, `enumitem`, `hyperref`, etc. Use `$…$` for math.
- Reference the id from a reader collection like any module
  (`<col:module document="authored-ions"/>`). `validate.py` skips CNXML checks for
  `.tex` modules (no image/xref validation — you manage those yourself).

See `sources/authored/` for a working example.

## SOURCE.md

Every source directory needs a `SOURCE.md` (copy `SOURCE.template.md`). It pins
the snapshot and records the license — this is what makes the reader's provenance
appendix and CC-license compliance (attribution + same-license + indicating
changes) automatic. For imported OpenStax books, record the exact upstream commit
you copied from so the snapshot is reproducible.

> Licensing: this book is CC BY-NC-SA 4.0. Imported CC BY material is compatible
> (attribute it); license your own content BY-NC-SA 4.0 or more permissive so the
> combined reader stays shareable under one license.
