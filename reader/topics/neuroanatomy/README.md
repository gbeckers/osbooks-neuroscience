# topic reader definitions

## Neuroanatomy

## Sources:

- https://github.com/openstax/osbooks-neuroscience/tree/main (2026-07-09; commit 6164a76)
  - included modules m00026, m00021alt, m00022, m00023, m00024
  - m00021alt is based on m00021, but excludes section on histology techniques

## 

## Build and compile document

```sh
python3 tools/validate.py reader/topics/neuroanatomy/neuroanatomy.collection.xml
python3 tools/build_latex.py reader/topics/neuroanatomy/neuroanatomy.collection.xml \
--margin="1in" \
--out build/topics/neuroanatomy/neuroanatomy.tex
cd build/topics/neuroanatomy && xelatex neuroanatomy.tex && xelatex neuroanatomy.tex

```
