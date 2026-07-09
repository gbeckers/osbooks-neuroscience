"""Parse an OpenStax `*.collection.xml` table of contents.

A collection is a nested tree of subcollections (the book's "units"/parts) and
module references (`<col:module document="mXXXXX"/>`). Modules can also appear at
the top level (e.g. the preface sits before the first subcollection).

We model that as:

    Collection
      title: str
      slug, uuid, license_url, license_text: str | None   (book metadata)
      content: list[ModuleRef | Unit]                     (ordered, as in the file)

    Unit
      title: str
      content: list[ModuleRef | Unit]                     (subcollections may nest)

    ModuleRef
      document: str        e.g. "m00021"
      unit_path: tuple     titles of enclosing units, for readable diagnostics

Design notes:
- Nesting is handled recursively even though the current book only uses one level,
  so imported material or reorganised course readers keep working.
- We record source line numbers where available to make validator output clickable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Union
import xml.etree.ElementTree as ET

# Namespaces used in collection files.
NS = {
    "col": "http://cnx.rice.edu/collxml",
    "md": "http://cnx.rice.edu/mdml",
}

TreeNode = Union["ModuleRef", "Unit"]


@dataclass
class ModuleRef:
    """A reference to a module from the collection's table of contents."""

    document: str
    unit_path: tuple[str, ...] = ()

    @property
    def location(self) -> str:
        """Human-readable position in the book, e.g. 'Vision > The retina'."""
        return " > ".join(self.unit_path) if self.unit_path else "(top level)"


@dataclass
class Unit:
    """A subcollection: a titled group of modules and/or nested subcollections."""

    title: str
    content: list[TreeNode] = field(default_factory=list)


@dataclass
class Collection:
    """A parsed collection file (the whole book's structure)."""

    title: str
    path: Path
    slug: str | None = None
    uuid: str | None = None
    license_url: str | None = None
    license_text: str | None = None
    content: list[TreeNode] = field(default_factory=list)

    def module_refs(self) -> list[ModuleRef]:
        """All ModuleRefs in reading order, flattened across units."""
        out: list[ModuleRef] = []

        def walk(nodes: list[TreeNode]) -> None:
            for node in nodes:
                if isinstance(node, ModuleRef):
                    out.append(node)
                else:
                    walk(node.content)

        walk(self.content)
        return out

    def module_ids(self) -> set[str]:
        """Set of module ids included anywhere in this collection."""
        return {ref.document for ref in self.module_refs()}


def _text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    return el.text.strip()


def parse_collection(path: str | Path) -> Collection:
    """Parse a collection XML file into a Collection tree."""
    path = Path(path)
    root = ET.parse(path).getroot()

    meta = root.find("col:metadata", NS)
    license_el = meta.find("md:license", NS) if meta is not None else None

    collection = Collection(
        title=_text(meta.find("md:title", NS)) if meta is not None else path.stem,
        path=path,
        slug=_text(meta.find("md:slug", NS)) if meta is not None else None,
        uuid=_text(meta.find("md:uuid", NS)) if meta is not None else None,
        license_url=license_el.get("url") if license_el is not None else None,
        license_text=_text(license_el),
    )

    content_el = root.find("col:content", NS)
    if content_el is not None:
        collection.content = _parse_content(content_el, unit_path=())
    return collection


def _parse_content(content_el: ET.Element, unit_path: tuple[str, ...]) -> list[TreeNode]:
    """Parse the children of a <col:content> element, preserving order."""
    nodes: list[TreeNode] = []
    for child in content_el:
        tag = child.tag.split("}", 1)[-1]  # strip namespace
        if tag == "module":
            doc = child.get("document")
            if doc:
                nodes.append(ModuleRef(document=doc, unit_path=unit_path))
        elif tag == "subcollection":
            title = _text(child.find("md:title", NS)) or "(untitled unit)"
            sub_content = child.find("col:content", NS)
            unit = Unit(title=title)
            if sub_content is not None:
                unit.content = _parse_content(sub_content, unit_path + (title,))
            nodes.append(unit)
    return nodes
