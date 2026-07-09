"""CNXML -> LaTeX converter (prototype).

Converts a single OpenStax module (`modules/mXXXXX/index.cnxml`) to a LaTeX
fragment. A driver (`build_latex.py`) wraps one or more fragments in a preamble.

Design decisions worth knowing:

* **Figure/table numbers come from the id, not a LaTeX counter.** OpenStax encodes
  the printed number in the element id (`Image-2.24` -> "2.24"). Because we extract
  a chapter (or a subset), LaTeX's own sequential counters would renumber and no
  longer match the text. So we caption figures as "Figure 2.24. ..." literally and
  synthesise cross-reference text ("Figure 2.24") from the same id -- text and
  figure always agree, and they match the source book.
* **Tables reuse `Image-` ids**, so a first pass builds an id -> (kind, number)
  map to tell "Figure 2.16" from "Table 2.24".
* **Links are empty** (`<link target-id="Image-2.16"/>`) -- there is no inner text,
  so all reference wording is generated here.
* Interactive content (`os-embed` exercises, `iframe` videos) is dropped, with a
  small margin note so nothing silently vanishes.

Targets **xelatex/lualatex** (Unicode passes through: +/-, arrows, Greek, curly
quotes). See build_latex.py for the preamble.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import html
import re
import xml.etree.ElementTree as ET

CNXML_NS = "http://cnx.rice.edu/cnxml"
MD_NS = "http://cnx.rice.edu/mdml"
MATHML_NS = "http://www.w3.org/1998/Math/MathML"

# Human-readable headers for the note boxes, keyed by CNXML class.
NOTE_LABELS = {
    "meet-author": "Meet the Author",
    "inthe-lab": "In the Lab",
    "in-thewild": "In the Wild",
    "boxed-feature": "",  # generic box, no header prefix
    "across-species": "Across Species",
}

_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def escape(text: str) -> str:
    """Escape LaTeX specials in a run of text (Unicode is left for xelatex)."""
    if not text:
        return ""
    # Some source text is double-encoded (e.g. "&amp;amp;" survives one XML decode
    # as the literal "&amp;"); undo any leftover HTML entities before LaTeX-escaping.
    text = html.unescape(text)
    out = []
    for ch in text:
        out.append(_SPECIALS.get(ch, ch))
    return "".join(out)


# Absolute heading levels -> LaTeX sectioning commands (report class).
# 0 = chapter (a unit), 1 = section (a module), then subsections within a module.
LEVEL_CMDS = {
    0: "chapter", 1: "section", 2: "subsection",
    3: "subsubsection", 4: "paragraph", 5: "subparagraph",
}


def heading(level: int, title: str, numbered: bool = True, label: str | None = None) -> str:
    """A LaTeX sectioning command at an absolute level.

    Unnumbered headings (used for the standalone Preface / Methods chapters) are
    still added to the table of contents.
    """
    cmd = LEVEL_CMDS.get(level if level <= 5 else 5, "paragraph")
    out = f"\\{cmd}{'' if numbered else '*'}{{{title}}}\n"
    if not numbered and cmd in ("chapter", "section"):
        out += f"\\addcontentsline{{toc}}{{{cmd}}}{{{title}}}\n"
    if label:
        out += f"\\label{{{label}}}\n"
    return out


def _number_from_id(el_id: str) -> str:
    """'Image-2.24' -> '2.24', 'Image-2.04.2' -> '2.4.2'."""
    stripped = re.sub(r"^(Image|Figure|Table)-", "", el_id)
    parts = stripped.split(".")
    norm = []
    for p in parts:
        norm.append(str(int(p)) if p.isdigit() else p)
    return ".".join(norm)


@dataclass
class Label:
    kind: str      # "figure" or "table"
    number: str    # e.g. "2.24"


class LatexConverter:
    def __init__(
        self,
        module_titles: dict[str, str] | None = None,
        included_ids: set[str] | None = None,
    ):
        # Titles of modules on disk, for rendering cross-module link text.
        self.module_titles = module_titles or {}
        # Module ids in the current build (unused refs still render as text).
        self.included_ids = included_ids or set()
        self.labels: dict[str, Label] = {}
        self.dropped: list[str] = []  # notes about interactive content dropped

    # -- public entry point ------------------------------------------------

    def convert_module(
        self,
        path: str | Path,
        module_id: str,
        heading_level: int = 1,
        numbered: bool = True,
    ) -> str:
        """Convert a module. `heading_level` is the absolute level of the module's
        own title (1 = section, i.e. a module inside a unit-chapter); its internal
        sections are rendered one level deeper."""
        path = Path(path)
        if path.is_dir():
            path = path / "index.cnxml"
        root = ET.parse(path).getroot()

        self._index_labels(root)

        title_el = root.find(f"{{{CNXML_NS}}}title")
        title = self._inline(title_el) if title_el is not None else module_id

        content = root.find(f"{{{CNXML_NS}}}content")
        body = self._blocks(content, level=heading_level + 1) if content is not None else ""

        head = heading(heading_level, title, numbered, label=f"mod:{module_id}")
        return f"{head}\n{body}\n"

    # -- first pass: id -> Label ------------------------------------------

    def _index_labels(self, root: ET.Element) -> None:
        for el in root.iter():
            tag = _local(el.tag)
            el_id = el.get("id")
            if not el_id:
                continue
            if tag == "figure":
                self.labels[el_id] = Label("figure", _number_from_id(el_id))
            elif tag == "table":
                self.labels[el_id] = Label("table", _number_from_id(el_id))

    # -- block-level rendering --------------------------------------------

    def _blocks(self, parent: ET.Element, level: int) -> str:
        out: list[str] = []
        for el in parent:
            out.append(self._block(el, level))
        return "\n".join(chunk for chunk in out if chunk.strip())

    def _block(self, el: ET.Element, level: int) -> str:
        tag = _local(el.tag)
        if tag == "section":
            return self._section(el, level)
        if tag == "para":
            return self._inline(el) + "\n"
        if tag == "list":
            return self._list(el)
        if tag == "figure":
            return self._figure(el)
        if tag == "table":
            return self._table(el)
        if tag == "note":
            return self._note(el, level)
        if tag == "exercise":
            self.dropped.append("exercise")
            return ""  # interactive; dropped
        if tag in ("quote",):
            return "\\begin{quote}\n" + self._inline(el) + "\n\\end{quote}\n"
        if tag in ("title", "metadata"):
            return ""  # handled by caller / not printed
        # Fallback: try inline so we don't lose text.
        return self._inline(el)

    def _section(self, el: ET.Element, level: int) -> str:
        title_el = el.find(f"{{{CNXML_NS}}}title")
        title = self._inline(title_el) if title_el is not None else ""
        cls = el.get("class", "")

        if cls == "learning-objectives":
            inner = self._blocks(el, level + 1)
            # Present as a labelled box rather than a numbered heading.
            return ("\\begin{objectives}\n" + inner + "\n\\end{objectives}\n")

        return heading(level, title) + self._blocks(el, level + 1)

    def _list(self, el: ET.Element) -> str:
        env = "enumerate" if el.get("list-type") == "enumerated" else "itemize"
        items = []
        for item in el.findall(f"{{{CNXML_NS}}}item"):
            items.append("  \\item " + self._inline(item))
        return f"\\begin{{{env}}}\n" + "\n".join(items) + f"\n\\end{{{env}}}\n"

    def _figure(self, el: ET.Element) -> str:
        el_id = el.get("id", "")
        number = self.labels.get(el_id, Label("figure", _number_from_id(el_id))).number
        # Splash/chapter-opener figures aren't numbered (id like "sploish").
        is_numbered = el.get("class") != "splash" and any(c.isdigit() for c in number)
        title_el = el.find(f"{{{CNXML_NS}}}title")
        caption_el = el.find(f"{{{CNXML_NS}}}caption")

        img = el.find(f".//{{{CNXML_NS}}}image")
        graphic = ""
        if img is not None and img.get("src"):
            # Path is relative to the module dir; the driver sets \graphicspath.
            src = Path(img.get("src")).name
            graphic = (f"  \\includegraphics[width=\\linewidth,"
                       f"height=0.5\\textheight,keepaspectratio]{{{src}}}\n")

        cap_parts = []
        if is_numbered:
            cap_parts.append(f"\\textbf{{Figure {number}.}} ")
        if title_el is not None:
            cap_parts.append("\\textbf{" + self._inline(title_el) + ".} ")
        if caption_el is not None:
            cap_parts.append(self._inline(caption_el))
        caption = "".join(cap_parts)

        # Non-floating: a float (figure env) can't sit inside a note box / tcolorbox
        # ("Not in outer par mode"). Numbers are already baked into the caption, so
        # we don't need the float's counter. Keeps figures in reading order too.
        return (
            "\\par\\medskip\n{\\centering\n" + graphic + "\\par}\n"
            "\\smallskip\n{\\small " + caption + "}\n\\par\\medskip\n"
        )

    def _table(self, el: ET.Element) -> str:
        el_id = el.get("id", "")
        number = self.labels.get(el_id, Label("table", _number_from_id(el_id))).number
        tgroup = el.find(f"{{{CNXML_NS}}}tgroup")
        if tgroup is None:
            return ""
        ncols = int(tgroup.get("cols", "1"))
        colspec = "|" + "|".join(["X"] * ncols) + "|"

        def rows(section: ET.Element | None, header: bool) -> list[str]:
            if section is None:
                return []
            out = []
            for row in section.findall(f"{{{CNXML_NS}}}row"):
                cells = [self._inline(e) for e in row.findall(f"{{{CNXML_NS}}}entry")]
                if header:
                    cells = ["\\textbf{" + c + "}" for c in cells]
                out.append("  " + " & ".join(cells) + " \\\\ \\hline")
            return out

        thead = rows(tgroup.find(f"{{{CNXML_NS}}}thead"), header=True)
        tbody = rows(tgroup.find(f"{{{CNXML_NS}}}tbody"), header=False)

        # Non-floating (see _figure): tabularx isn't a float, but wrapping it in a
        # table float would break inside note boxes, so we place it inline with a
        # manual caption above.
        lines = ["\\par\\medskip", f"\\noindent{{\\small\\textbf{{Table {number}.}}}}\\par\\smallskip",
                 f"\\noindent\\begin{{tabularx}}{{\\linewidth}}{{{colspec}}}", "  \\hline"]
        lines += thead + tbody
        lines += ["  \\end{tabularx}", "\\par\\medskip"]
        return "\n".join(lines) + "\n"

    def _note(self, el: ET.Element, level: int) -> str:
        cls = el.get("class", "boxed-feature")
        header = NOTE_LABELS.get(cls, "")
        title_el = el.find(f"{{{CNXML_NS}}}title")
        title = self._inline(title_el) if title_el is not None else ""

        head = ": ".join(p for p in (header, title) if p)
        # Skip children we already consumed / that are interactive-only.
        inner_parts = []
        for child in el:
            if _local(child.tag) == "title":
                continue
            inner_parts.append(self._block(child, level + 1))
        inner = "\n".join(p for p in inner_parts if p.strip())
        if not inner.strip():
            return ""  # e.g. author-video note with only an iframe
        return (f"\\begin{{featurebox}}{{{head}}}\n" + inner + "\n\\end{featurebox}\n")

    # -- inline rendering --------------------------------------------------

    def _inline(self, el: ET.Element | None) -> str:
        if el is None:
            return ""
        out = [escape(el.text or "")]
        for child in el:
            out.append(self._inline_child(child))
            out.append(escape(child.tail or ""))
        return "".join(out).strip()

    def _inline_child(self, el: ET.Element) -> str:
        tag = _local(el.tag)
        if tag == "emphasis":
            effect = el.get("effect", "italics")
            inner = self._inline(el)
            return {
                "italics": f"\\emph{{{inner}}}",
                "bold": f"\\textbf{{{inner}}}",
                "underline": f"\\underline{{{inner}}}",
                "smallcaps": f"\\textsc{{{inner}}}",
            }.get(effect, f"\\emph{{{inner}}}")
        if tag == "term":
            return f"\\textbf{{{self._inline(el)}}}"
        if tag == "sup":
            return f"\\textsuperscript{{{self._inline(el)}}}"
        if tag == "sub":
            return f"\\textsubscript{{{self._inline(el)}}}"
        if tag == "newline":
            # \newline (not \\) so it also works inside a tabularx cell, where \\
            # would prematurely end the row and unbalance any surrounding braces.
            return "\\newline "
        if tag == "link":
            return self._link(el)
        if tag == "media":
            return self._inline_media(el)
        if tag == "math":  # MathML (m:math)
            return f"${self._mathml(el)}$"
        if tag in ("title", "caption", "entry", "item", "para"):
            return self._inline(el)
        return self._inline(el)  # unknown inline: keep its text

    def _link(self, el: ET.Element) -> str:
        target = el.get("target-id")
        document = el.get("document")
        url = el.get("url")
        cls = el.get("class")

        if cls == "os-embed" or (url and url.startswith("#")):
            self.dropped.append("os-embed")
            return ""  # interactive exercise reference

        if document:
            # Cross-module reference: render as plain text (no hyperlink in print).
            title = self.module_titles.get(document)
            if target and target in self.labels:  # rare: cross-module figure ref
                lab = self.labels[target]
                return f"{lab.kind.capitalize()}~{lab.number}"
            if title:
                return f"(see \\emph{{{escape(title)}}})"
            return ""

        if target:
            lab = self.labels.get(target)
            if lab:
                return f"{lab.kind.capitalize()}~{lab.number}"
            # Non-figure internal target (section/para): use LaTeX ref if labelled.
            return "this section"

        if url:  # external web link
            inner = self._inline(el)
            if inner:
                return f"{inner}\\footnote{{\\url{{{url}}}}}"
            return f"\\url{{{url}}}"
        return self._inline(el)

    def _inline_media(self, el: ET.Element) -> str:
        # Inline media: an iframe (video) is dropped; an inline image is included.
        if el.find(f"{{{CNXML_NS}}}iframe") is not None:
            self.dropped.append("iframe")
            return ""
        img = el.find(f"{{{CNXML_NS}}}image")
        if img is not None and img.get("src"):
            src = Path(img.get("src")).name
            return f"\\includegraphics[height=1em]{{{src}}}"
        return ""

    def _mathml(self, el: ET.Element) -> str:
        """Minimal MathML -> LaTeX for the elements this book uses."""
        tag = _local(el.tag)
        kids = list(el)
        if tag in ("math", "mrow"):
            return "".join(self._mathml(k) for k in kids)
        if tag in ("mi", "mn", "mo"):
            return (el.text or "").strip()
        if tag == "mfrac" and len(kids) == 2:
            return f"\\frac{{{self._mathml(kids[0])}}}{{{self._mathml(kids[1])}}}"
        if tag == "msup" and len(kids) == 2:
            return f"{{{self._mathml(kids[0])}}}^{{{self._mathml(kids[1])}}}"
        if tag == "msub" and len(kids) == 2:
            return f"{{{self._mathml(kids[0])}}}_{{{self._mathml(kids[1])}}}"
        if tag == "msqrt":
            return f"\\sqrt{{{''.join(self._mathml(k) for k in kids)}}}"
        return "".join(self._mathml(k) for k in kids)
