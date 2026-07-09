"""oscompile: tools for building a custom print book from OpenStax CNXML sources.

This package is intentionally dependency-free (Python standard library only) so it
runs in the repo's devcontainer or a bare Python 3 install with no `pip install`.

Modules:
    collection  -- parse a `*.collection.xml` table of contents into a tree.
    module      -- parse a single `modules/mXXXXX/index.cnxml` document.
    validate    -- cross-check a collection: missing modules, images, and links
                   (especially links that break when a chapter is left out of a
                   custom subset, or imported from another book).

The collection/module parsers are the shared foundation the CNXML -> LaTeX
converter will build on next.
"""

from .collection import Collection, Unit, ModuleRef, parse_collection
from .module import Module, parse_module

__all__ = [
    "Collection",
    "Unit",
    "ModuleRef",
    "parse_collection",
    "Module",
    "parse_module",
]
