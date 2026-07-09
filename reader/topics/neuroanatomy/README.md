# topic reader definitions

## Neuroanatomy

```sh
python3 tools/validate.py reader/topics/neuroanatomy/neuroanatomy.collection.xml
python3 tools/build_latex.py reader/topics/neuroanatomy/neuroanatomy.collection.xml --out build/topics/neuroanatomy/neuroanatomy.tex
cd build/topics/neuroanatomy && xelatex neuroanatomy.tex && xelatex neuroanatomy.tex

```
