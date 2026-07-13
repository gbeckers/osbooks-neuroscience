# Shared content patches

Declarative overlays applied to **pristine** OpenStax modules at build time, so
`modules/` (and `sources/*/modules/`) stay untouched and sync cleanly from
upstream. A patch names its target by a **unique text fragment**, not a line
number, and the build **fails loudly** (naming the file + fragment) if a fragment
no longer matches — so an upstream rewording is caught, not silently mis-applied.

Files here apply to **every reader** that includes the patched module. A
collection's own `patches/` dir (e.g. `reader/topics_core/<topic>/patches/`) adds
reader-specific edits on top; the two are merged, and if a reader's collection dir
*is* `reader/` (the main course reader) the shared dir is loaded once.

## Schema

`<module_id>.patch.yaml` — patches that one module. `_all.patch.yaml` — applies to
every module in the build. Three directives (see `tools/oscompile/patches.py`):

```yaml
delete:                      # remove the innermost block containing the fragment
  - |
    a unique sentence from the paragraph/figure to drop
drop-sections:               # remove whole <section>s by heading (lenient: 0 ok)
  - Multiple Choice
replace:                     # swap one run of literal text (must match exactly once)
  - find: |
      original wording
    with: |
      new wording
```

`delete` and `replace` are strict (exactly one match, else build error). Put prose
fragments in `|` block scalars so their colons/quotes don't clash with YAML.

## Current shared patches

- `m00021.patch.yaml` — cuts the cell-biology preamble and histology-techniques
  sections from *Building a Nervous System*. Used by the main UCSCICOG11 reader and
  the neuroanatomy topic reader. Replaced the former hand-maintained fork
  `sources/neuroscience_adapt/modules/neuro-adap-m00021b`.
