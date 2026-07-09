# reader/ — your course reader definition

This directory holds **your** reader, kept separate from the OpenStax upstream so
it never collides with `git merge upstream/main`.

## Contents

- `*.collection.xml` — the course table of contents. It lists the units/modules
  your reader includes, in order, referencing modules from **any** source:
  the neuroscience upstream (root `modules/`) or an imported/own source
  (`sources/<name>/modules/`). Trim chapters, reorder, mix sources here.
- `errata.md` — human-readable notes for each correction you make to upstream
  text. These complement the exact record git already keeps
  (`git diff upstream/main -- modules/`) and feed the reader's provenance
  appendix with a plain-English explanation of each change.
- `example-course-subset.collection.xml` — a worked example (intentionally
  triggers `dangling-xref` warnings; see tools/README.md).

## Workflow

```bash
# 1. (When upstream publishes fixes) pull them in
git fetch upstream && git merge upstream/main
#    resolve conflicts — only ever in modules you errata-edited

# 2. Check the course still assembles (missing modules, broken/dangling refs)
python3 tools/validate.py reader/cogneuro.collection.xml

# 3. Build the PDF
python3 tools/build_latex.py reader/cogneuro.collection.xml --out build/cogneuro.tex
cd build && xelatex cogneuro.tex && xelatex cogneuro.tex
```

## Authoring the collection

Start from the upstream collection and cut it down:

```bash
cp collections/introduction-behavioral-neuroscience.collection.xml \
   reader/cogneuro.collection.xml
# then delete the <col:module>/<col:subcollection> entries you don't teach,
# add <col:module> entries for imported/own modules (see sources/README.md),
# and run tools/validate.py to catch anything that dangles.
```

Errata (typo/minor fixes) are edited **in place** in the upstream `modules/` so
they keep merging with future upstream changes — see the top-level strategy notes.
Structural trims (using only part of a chapter) are done as override copies with a
new module id, so upstream structure changes don't fight your cuts.
