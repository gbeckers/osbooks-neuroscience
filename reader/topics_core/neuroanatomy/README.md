# topic reader definitions

## Neuroanatomy

## Sources:

- https://github.com/openstax/osbooks-neuroscience/tree/main (2026-07-09; commit 6164a76)
  - included modules m00026, m00021, m00022, m00023, m00024, m00025
  - m00021 is the pristine upstream module; the cut of its cell-biology preamble and
    histology-techniques sections is expressed as a shared patch (see below), not a
    fork. (This replaced the former hand-maintained `neuro-adap-m00021b` copy.)

## Content patches

Course customizations to upstream modules live in `patches/` dirs as declarative
overlays, so `modules/` stays byte-for-byte OpenStax (clean `git merge
upstream/main`). Each patch targets text by a **unique fragment**, not a line
number; if upstream rewords it, the build fails loudly naming the file + fragment
instead of diverging silently. See `tools/oscompile/patches.py` for the schema.

Two scopes, merged at build time:

- `reader/patches/` — **shared** across every reader (e.g. `m00021.patch.yaml`,
  which both this reader and the main UCSCICOG11 reader use).
- `patches/` next to this collection — reader-specific:
  - `_all.patch.yaml` applies to every module here (drops the always-empty
    "Multiple Choice" / "Fill in the Blank" sections).
  - `<module_id>.patch.yaml` per-module `delete` / `drop-sections` / `replace`.
    `patches/m00022.patch.yaml` is a worked example.

## 

## Build and compile document

```sh
python3 tools/validate.py reader/topics_core/neuroanatomy/neuroanatomy.collection.xml
python3 tools/build_latex.py reader/topics_core/neuroanatomy/neuroanatomy.collection.xml \
--margin="1in" \
--out build/topics_core/neuroanatomy/neuroanatomy.tex
cd build/topics_core/neuroanatomy && xelatex neuroanatomy.tex && xelatex neuroanatomy.tex
cd ../..
```
