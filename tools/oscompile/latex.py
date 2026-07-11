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


_URL_RE = re.compile(r"https?://\S+")


def _escape_plain(text: str) -> str:
    return "".join(_SPECIALS.get(ch, ch) for ch in text)


def url_arg(url: str) -> str:
    r"""A URL made safe as the argument of \url{}. On its own \url handles a bare
    "#", but when the \url sits inside another macro's braces (e.g. a reference
    footnote) the "#" is read as a parameter token -> hyperref "Illegal parameter
    number in \Hy@tempa". Escaping it to \# renders identically and survives both
    contexts."""
    return url.replace("#", r"\#")


def escape(text: str) -> str:
    """Escape LaTeX specials in a run of text (Unicode is left for xelatex).

    Bare URLs (common in reference lists) are wrapped in \\url{} so they can break
    across lines -- otherwise a long DOI is a single ~500pt-wide unbreakable box.
    """
    if not text:
        return ""
    # Some source text is double-encoded (e.g. "&amp;amp;" survives one XML decode
    # as the literal "&amp;"); undo any leftover HTML entities before LaTeX-escaping.
    text = html.unescape(text)

    out, last = [], 0
    for m in _URL_RE.finditer(text):
        url = m.group(0)
        # Keep trailing sentence punctuation outside the \url{}.
        trail = ""
        while url and url[-1] in ".,;:)]}":
            trail = url[-1] + trail
            url = url[:-1]
        out.append(_escape_plain(text[last:m.start()]))
        out.append(f"\\url{{{url_arg(url)}}}" if url else "")
        out.append(_escape_plain(trail))
        last = m.end()
    out.append(_escape_plain(text[last:]))
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
    # Add unnumbered *chapters* (Preface, Methods, appendix) to the ToC. Unnumbered
    # sections are left out so they don't bypass tocdepth and flood a short ToC.
    if not numbered and cmd == "chapter":
        out += f"\\addcontentsline{{toc}}{{{cmd}}}{{{title}}}\n"
    if label:
        out += f"\\label{{{label}}}\n"
    return out


def _number_from_id(el_id: str) -> str:
    """Derive a display number from a figure/table id.

    Neuroscience ids are dot-separated after an Image/Figure/Table- prefix and may
    carry alpha suffixes we must keep distinct (Image-2.24 -> 2.24; Figure-9.X ->
    9.X). Biology/Anatomy ids look like fig-ch11_02_01 -> 11.2.1 or tbl-ch12_01 ->
    12.1. Both stay internally consistent because caption and cross-reference derive
    from the same id.

    The result is typeset verbatim (caption + "Figure N" cross-refs), so an
    unrecognised id must not leak LaTeX specials (a bare "_" -> "Missing $").
    """
    m = re.match(r"^(?:Image|Figure|Table)-(.+)$", el_id)
    if m:  # neuroscience: keep dotted parts, preserve alpha suffixes (9.X)
        parts = m.group(1).split(".")
        return ".".join(str(int(p)) if p.isdigit() else p for p in parts)
    # biology/anatomy: fig/tbl/tab/table-ch11_02_01 -> join the numeric groups.
    m = re.match(r"^(?:fig|figure|tbl|tab|table)-(?:ch)?(.+)$", el_id, re.IGNORECASE)
    if m:
        nums = re.findall(r"\d+", m.group(1))
        if nums:
            return ".".join(str(int(n)) for n in nums)
    return el_id.replace("_", ".")  # unknown scheme: at least keep it LaTeX-safe


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
        self._numbered = True  # sections in an unnumbered chapter are unnumbered too
        self._exercise_n = 0   # per-module counter for rendered exercises

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

        # In an unnumbered chapter (Preface, Methods) the module's own sub-sections
        # must be unnumbered too, else they inherit the stale chapter counter
        # (e.g. "19.17 Chemogenetics" under a \chapter* that follows chapter 19).
        self._numbered = numbered
        self._exercise_n = 0
        content = root.find(f"{{{CNXML_NS}}}content")
        body = self._blocks(content, level=heading_level + 1) if content is not None else ""

        head = heading(heading_level, title, numbered, label=f"mod:{module_id}")
        return f"{head}\n{body}\n"

    # -- first pass: id -> Label ------------------------------------------

    def prescan_labels(self, paths) -> None:
        """Index figure/table ids across all modules in the build *before*
        rendering, so a cross-reference resolves even when its target lives in a
        later-processed module (e.g. another module in the same chapter)."""
        for p in paths:
            p = Path(p)
            if p.is_dir():
                p = p / "index.cnxml"
            try:
                self._index_labels(ET.parse(p).getroot())
            except (ET.ParseError, OSError):
                continue

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

    def _blocks(self, parent: ET.Element, level: int, in_box: bool = False) -> str:
        out: list[str] = []
        for el in parent:
            out.append(self._block(el, level, in_box))
        return "\n".join(chunk for chunk in out if chunk.strip())

    def _block(self, el: ET.Element, level: int, in_box: bool = False) -> str:
        tag = _local(el.tag)
        if tag == "section":
            return self._section(el, level, in_box)
        if tag == "para":
            return self._inline(el) + "\n"
        if tag == "list":
            return self._list(el)
        if tag == "figure":
            return self._figure(el)
        if tag == "media":
            return self._block_media(el)
        if tag == "table":
            return self._table(el, in_box)
        if tag == "note":
            return self._note(el, level)
        if tag == "exercise":
            return self._exercise(el, level, in_box)
        if tag in ("quote",):
            return "\\begin{quote}\n" + self._inline(el) + "\n\\end{quote}\n"
        if tag in ("title", "metadata"):
            return ""  # handled by caller / not printed
        # Fallback: try inline so we don't lose text.
        return self._inline(el)

    def _section(self, el: ET.Element, level: int, in_box: bool = False) -> str:
        title_el = el.find(f"{{{CNXML_NS}}}title")
        title = self._inline(title_el) if title_el is not None else ""
        cls = el.get("class", "")

        if cls == "learning-objectives":
            inner = self._blocks(el, level + 1, in_box=True)
            # Present as a labelled box rather than a numbered heading.
            return ("\\begin{objectives}\n" + inner + "\n\\end{objectives}\n")

        return heading(level, title, numbered=self._numbered) + self._blocks(el, level + 1, in_box)

    _NUMBER_STYLES = {
        "lower-alpha": r"\alph*.", "upper-alpha": r"\Alph*.",
        "lower-roman": r"\roman*.", "upper-roman": r"\Roman*.",
    }

    def _list(self, el: ET.Element) -> str:
        items = el.findall(f"{{{CNXML_NS}}}item")
        # OpenStax marks run-in lists (e.g. the Key Terms section) with
        # display="inline"; the print book sets these comma-separated on one line
        # instead of one bullet per line. Match that -- it reads the same and
        # saves a lot of vertical space.
        if el.get("display") == "inline":
            return ", ".join(self._inline(item) for item in items) + "\n"
        if el.get("list-type") == "enumerated":
            env = "enumerate"
            # Honour number-style (biology multiple-choice options use lower-alpha),
            # via enumitem's [label=...]; distinguishes options from question numbers.
            label = self._NUMBER_STYLES.get(el.get("number-style", ""))
            begin = f"\\begin{{enumerate}}[label={label}]" if label else "\\begin{enumerate}"
        else:
            env = "itemize"
            begin = "\\begin{itemize}"
        rendered = ["  \\item " + self._inline(item) for item in items]
        return begin + "\n" + "\n".join(rendered) + f"\n\\end{{{env}}}\n"

    def _graphic(self, img: ET.Element | None) -> str:
        """A centered \\includegraphics for a CNXML <image>, or "" if absent.
        Path is relative to the module dir; the driver sets \\graphicspath."""
        if img is None or not img.get("src"):
            return ""
        src = Path(img.get("src")).name
        return (f"  \\includegraphics[width=\\linewidth,"
                f"height=0.5\\textheight,keepaspectratio]{{{src}}}\n")

    def _block_media(self, el: ET.Element) -> str:
        """A block-level <media> that is NOT wrapped in a <figure> -- an
        explanatory diagram with no number/caption (the algebra module uses these
        for its arrow diagrams and blank plot grids). Without this the element
        falls through to inline rendering, where <image> has no handler and the
        picture is silently dropped. Center it like a figure; drop video iframes."""
        if el.find(f"{{{CNXML_NS}}}iframe") is not None:
            self.dropped.append("iframe")
            return ""
        graphic = self._graphic(el.find(f".//{{{CNXML_NS}}}image"))
        if not graphic:
            return ""
        return "\\par\\medskip\n{\\centering\n" + graphic + "\\par}\n\\medskip\n"

    def _figure(self, el: ET.Element) -> str:
        el_id = el.get("id", "")
        number = self.labels.get(el_id, Label("figure", _number_from_id(el_id))).number
        # Splash/chapter-opener figures aren't numbered (id like "sploish").
        is_numbered = el.get("class") != "splash" and any(c.isdigit() for c in number)
        title_el = el.find(f"{{{CNXML_NS}}}title")
        caption_el = el.find(f"{{{CNXML_NS}}}caption")

        img = el.find(f".//{{{CNXML_NS}}}image")
        graphic = self._graphic(img)

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
        # A \hypertarget makes "Figure N" cross-references clickable without relying
        # on LaTeX's figure counter (which would renumber and break id-based numbers).
        anchor = f"\\hypertarget{{fig:{el_id}}}{{}}" if el_id else ""
        return (
            anchor + "\\par\\medskip\n{\\centering\n" + graphic + "\\par}\n"
            "\\smallskip\n{\\small " + caption + "}\n\\par\\medskip\n"
        )

    def _table(self, el: ET.Element, in_box: bool = False) -> str:
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

        # xltabular (longtable + X columns) breaks across pages and repeats the
        # header (\endhead). But longtable can't live inside a box, so inside a note
        # or objectives box we fall back to a plain (non-breaking) tabularx.
        # Both are non-floating; \small helps wide (many-column) tables fit.
        env = "tabularx" if in_box else "xltabular"
        anchor = f"\\hypertarget{{tab:{el_id}}}{{}}" if el_id else ""
        lines = ["\\par\\medskip\\begingroup\\small" + anchor,
                 f"{{\\textbf{{Table {number}.}}}}\\par\\smallskip",
                 f"\\begin{{{env}}}{{\\linewidth}}{{{colspec}}}", "  \\hline"]
        lines += thead
        if not in_box:
            lines.append("  \\endhead")  # repeat header on each page it spans
        lines += tbody
        lines += [f"  \\end{{{env}}}", "\\endgroup\\par\\medskip"]
        return "\n".join(lines) + "\n"

    def _exercise(self, el: ET.Element, level: int, in_box: bool) -> str:
        """Render an exercise with real content (problem + optional solution).

        Neuroscience exercises hold only an os-embed placeholder link, so their
        <problem> renders empty -- those are dropped. Biology's multiple-choice and
        critical-thinking exercises have genuine text/lists and are kept, numbered
        per module, with the answer shown in small italics beneath the question.
        """
        problem = el.find(f"{{{CNXML_NS}}}problem")
        prob = self._blocks(problem, level, in_box).strip() if problem is not None else ""
        if not prob:
            self.dropped.append("exercise")
            return ""

        self._exercise_n += 1
        out = [f"\\par\\smallskip\\noindent\\textbf{{{self._exercise_n}.}} {prob}"]
        solution = el.find(f"{{{CNXML_NS}}}solution")
        if solution is not None:
            sol = self._blocks(solution, level, in_box).strip()
            if sol:
                out.append(f"\\par\\nopagebreak\\noindent{{\\small\\emph{{Answer.}} {sol}}}")
        out.append("\\par\\smallskip")
        return "\n".join(out)

    def _note(self, el: ET.Element, level: int) -> str:
        cls = el.get("class", "boxed-feature")
        header = NOTE_LABELS.get(cls, "")
        title_el = el.find(f"{{{CNXML_NS}}}title")
        title = self._inline(title_el) if title_el is not None else ""

        head = ": ".join(p for p in (header, title) if p)
        # Skip children we already consumed / that are interactive-only.
        # in_box=True: contents are inside a tcolorbox, so tables must stay
        # non-breaking (plain tabularx, not xltabular/longtable).
        inner_parts = []
        for child in el:
            if _local(child.tag) == "title":
                continue
            inner_parts.append(self._block(child, level + 1, in_box=True))
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
        if tag == "footnote":  # biology uses real footnotes for citations
            return f"\\footnote{{{self._inline(el)}}}"
        if tag == "definition":  # biology inline glossary: <term>..<meaning>..
            term_el = el.find(f"{{{CNXML_NS}}}term")
            meaning_el = el.find(f"{{{CNXML_NS}}}meaning")
            term = self._inline(term_el) if term_el is not None else ""
            meaning = self._inline(meaning_el) if meaning_el is not None else ""
            return f"\\textbf{{{term}}}: {meaning}"
        if tag == "meaning":
            return self._inline(el)
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
            inner = self._mathml(el)
            # An empty <m:math/> would emit "$$", which TeX reads as a display-math
            # delimiter and mismatches against the next real "$...$" ("Display math
            # should end with $$"). Drop it instead.
            return f"${inner}$" if inner.strip() else ""
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
            # Cross-module reference.
            if target and target in self.labels:  # figure/table in another module
                return self._fig_ref(target)
            title = self.module_titles.get(document)
            if title and document in self.included_ids:
                # Clickable jump to that module's heading (label set in heading()).
                return f"(see \\hyperref[mod:{document}]{{\\emph{{{escape(title)}}}}})"
            if title:
                return f"(see \\emph{{{escape(title)}}})"
            return ""

        if target:
            if target in self.labels:
                return self._fig_ref(target)
            # Non-figure internal target (section/para): no counter to reference.
            return "this section"

        if url:  # external web link
            inner = self._inline(el)
            if inner:
                return f"{inner}\\footnote{{\\url{{{url_arg(url)}}}}}"
            return f"\\url{{{url_arg(url)}}}"
        return self._inline(el)

    def _fig_ref(self, target: str) -> str:
        """A clickable 'Figure N'/'Table N' pointing at the target's \\hypertarget.
        Uses the id-derived number (not a LaTeX counter) so it matches the source;
        if the target isn't in this build the link is inert but the text still shows."""
        lab = self.labels[target]
        prefix = "fig" if lab.kind == "figure" else "tab"
        return f"\\hyperlink{{{prefix}:{target}}}{{{lab.kind.capitalize()}~{lab.number}}}"

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
