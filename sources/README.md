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

## SOURCE.md

Every source directory needs a `SOURCE.md` (copy `SOURCE.template.md`). It pins
the snapshot and records the license — this is what makes the reader's provenance
appendix and CC-license compliance (attribution + same-license + indicating
changes) automatic. For imported OpenStax books, record the exact upstream commit
you copied from so the snapshot is reproducible.

> Licensing: this book is CC BY-NC-SA 4.0. Imported CC BY material is compatible
> (attribute it); license your own content BY-NC-SA 4.0 or more permissive so the
> combined reader stays shareable under one license.
