---
name: Course-authored supplements
slug: authored
license: CC BY-NC-SA 4.0
origin: Written for UCSCICOG11 Cognitive Neuroscience
imported: 2026-07-11
modules:
  - authored-ions
---

## Notes

Original short sections written for this reader that do not come from an OpenStax
book. Unlike the imported sources, these are authored in **raw LaTeX**
(`modules/<id>/index.tex`) rather than CNXML, because CNXML is awkward to write by
hand. The builder injects the file verbatim under an auto-generated section
heading; see `sources/README.md` ("Authored LaTeX sections") for the format.

- `authored-ions` — *Ions* — a short primer on ions, intracellular/extracellular
  ion distributions, and the origin of bioelectricity. Placed after the imported
  *Elements and Atoms* section (`anat-adapt-m45998`) in the Chemistry chapter of
  the Background Primer, since the course leans heavily on ions (ion channels,
  action potentials) but the A&P chemistry module does not cover them.
