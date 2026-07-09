"""Parse a single OpenStax CNXML module (`modules/mXXXXX/index.cnxml`).

We extract only what the validator and (later) the LaTeX converter need:

    Module
      module_id : str                  e.g. "m00021"
      title     : str
      path      : Path                 the index.cnxml file
      ids       : set[str]             every @id in the document (link targets)
      images    : list[ImageRef]       <image src=...> occurrences, path-resolved
      links     : list[LinkRef]        <link ...> occurrences (document/target-id/url)
      iframes   : list[str]            <iframe src=...> (embedded video/interactives)

CNXML uses a small, regular vocabulary. The full element list observed in this
book is: para, emphasis, title, link, item, term, section, problem, exercise,
media, image, figure, caption, list, note, table (tgroup/tbody/thead/row/entry/
colspec), sup, sub, newline, iframe, quote, and MathML (m:*). The converter will
map each of these; the parser here just indexes cross-references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import xml.etree.ElementTree as ET

CNXML_NS = "http://cnx.rice.edu/cnxml"
MD_NS = "http://cnx.rice.edu/mdml"


@dataclass
class ImageRef:
    """An <image src=...> reference, with the path resolved from the module dir."""

    src: str            # raw src attribute, e.g. "../../media/Image-1.01_...png"
    resolved: Path      # absolute path the src points to
    mime_type: str | None = None


@dataclass
class LinkRef:
    """A <link> element. Any of the attributes may be None depending on link kind.

    - target_id only            -> intra-module reference (usually a figure).
    - document (+/- target_id)  -> cross-module reference to another module.
    - url starting with http    -> external web link.
    - url starting with '#'      -> in-page anchor; os-embed exercises use this.
    """

    document: str | None
    target_id: str | None
    url: str | None
    cls: str | None

    @property
    def is_os_embed(self) -> bool:
        return self.cls == "os-embed"

    @property
    def is_external(self) -> bool:
        return bool(self.url) and self.url.startswith(("http://", "https://"))


@dataclass
class Module:
    module_id: str
    title: str
    path: Path
    ids: set[str] = field(default_factory=set)
    images: list[ImageRef] = field(default_factory=list)
    links: list[LinkRef] = field(default_factory=list)
    iframes: list[str] = field(default_factory=list)


def _local(tag: str) -> str:
    """Strip the XML namespace from a tag name."""
    return tag.split("}", 1)[-1]


def parse_module(path: str | Path, module_id: str | None = None) -> Module:
    """Parse a module's index.cnxml. `path` may be the dir or the index.cnxml file."""
    path = Path(path)
    if path.is_dir():
        path = path / "index.cnxml"
    module_dir = path.parent

    root = ET.parse(path).getroot()

    # Title lives at <document><title> (and mirrored in metadata).
    title_el = root.find(f"{{{CNXML_NS}}}title")
    title = (title_el.text or "").strip() if title_el is not None else (module_id or path.stem)

    if module_id is None:
        cid = root.find(f".//{{{MD_NS}}}content-id")
        module_id = (cid.text or "").strip() if cid is not None else module_dir.name

    module = Module(module_id=module_id, title=title, path=path)

    for el in root.iter():
        tag = _local(el.tag)

        # Index every id so intra-module target-id links can be resolved.
        el_id = el.get("id")
        if el_id:
            module.ids.add(el_id)

        if tag == "image":
            src = el.get("src")
            if src:
                resolved = (module_dir / src).resolve()
                module.images.append(
                    ImageRef(src=src, resolved=resolved, mime_type=el.get("mime-type"))
                )
        elif tag == "link":
            module.links.append(
                LinkRef(
                    document=el.get("document"),
                    target_id=el.get("target-id"),
                    url=el.get("url"),
                    cls=el.get("class"),
                )
            )
        elif tag == "iframe":
            src = el.get("src")
            if src:
                module.iframes.append(src)

    return module
