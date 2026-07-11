"""Validate a collection against the modules and media on disk.

The point of this pass is to surface, *before* you try to build a PDF, every
reference that will break in your custom reader:

  ERROR  -- will definitely produce a broken/missing output:
            * a module listed in the collection has no index.cnxml
            * an <image src> points at a file that isn't in media/
            * an intra-module figure link (target-id) resolves to no such id
            * a cross-module link points at a module that doesn't exist on disk

  WARN   -- will build, but the result is probably not what you want:
            * a cross-module link points at a module NOT in this collection
              (the classic "I dropped that chapter" dangling reference)
            * a cross-module target-id doesn't exist in the target module
            * the same module is included more than once
            * os-embed exercises / iframes: interactive content that can't print

  INFO   -- context, e.g. external web links, and (with --orphans) media files
            not referenced by any included module (candidates for pruning).

Usage as a library:  build_report(collection, repo_root) -> Report
Usage as a CLI:      python -m oscompile.validate [collection.xml] [--orphans]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import xml.etree.ElementTree as ET

from .collection import Collection, parse_collection
from .module import Module, parse_module
from .sources import Workspace, discover_workspace

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"


@dataclass
class Issue:
    severity: str
    category: str
    message: str
    module_id: str | None = None
    location: str | None = None  # unit path within the book

    def format(self) -> str:
        where = f" [{self.module_id}]" if self.module_id else ""
        loc = f" ({self.location})" if self.location else ""
        return f"{self.severity:5} {self.category:16}{where}{loc}: {self.message}"


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)
    modules_checked: int = 0

    def add(self, *args, **kwargs) -> None:
        self.issues.append(Issue(*args, **kwargs))

    def by_severity(self, sev: str) -> list[Issue]:
        return [i for i in self.issues if i.severity == sev]

    @property
    def error_count(self) -> int:
        return len(self.by_severity(ERROR))

    @property
    def warn_count(self) -> int:
        return len(self.by_severity(WARN))


def build_report(
    collection: Collection,
    repo_root: str | Path,
    check_orphans: bool = False,
    workspace: Workspace | None = None,
) -> Report:
    """Cross-check `collection` against the modules/media of every content source
    (the neuroscience upstream plus anything under sources/)."""
    repo_root = Path(repo_root)
    ws = workspace or discover_workspace(repo_root)
    report = Report()

    # Same module id defined in more than one source: resolution is ambiguous.
    for mid, srcs in ws.collisions.items():
        report.add(ERROR, "id-collision",
                   f"module id defined in multiple sources: {', '.join(srcs)}",
                   module_id=mid)
    # Same media filename in two sources: \graphicspath picks one arbitrarily.
    for name, srcs in ws.media_collisions().items():
        report.add(WARN, "media-collision",
                   f"media file '{name}' exists in multiple sources: {', '.join(srcs)}")

    refs = collection.module_refs()
    included_ids = collection.module_ids()

    # Detect duplicate inclusions.
    seen: set[str] = set()
    for ref in refs:
        if ref.document in seen:
            report.add(
                WARN, "duplicate-module",
                "module is included more than once in the collection",
                module_id=ref.document, location=ref.location,
            )
        seen.add(ref.document)

    # Cache of parsed modules (parse each on disk at most once), keyed by id.
    cache: dict[str, Module | None] = {}

    def load(module_id: str) -> Module | None:
        if module_id not in cache:
            p = ws.resolve(module_id)
            if p is not None and p.suffix == ".tex":
                # Course-authored raw-LaTeX section: no CNXML to validate.
                cache[module_id] = None
            else:
                try:
                    cache[module_id] = parse_module(p, module_id=module_id) if p else None
                except Exception as exc:  # malformed XML shouldn't crash the whole run
                    cache[module_id] = None
                    report.add(ERROR, "parse-error", f"failed to parse: {exc}", module_id=module_id)
        return cache[module_id]

    referenced_media: set[Path] = set()

    # Walk each included module in reading order.
    for ref in refs:
        mid, loc = ref.document, ref.location
        path = ws.resolve(mid)
        if path is None:
            report.add(ERROR, "missing-module",
                       f"no module '{mid}' found in any source (modules/ or sources/*/modules/)",
                       module_id=mid, location=loc)
            continue

        module = load(mid)
        if module is None:
            continue
        report.modules_checked += 1

        # 1. Images referenced must exist on disk.
        for img in module.images:
            referenced_media.add(img.resolved)
            if not img.resolved.exists():
                report.add(ERROR, "missing-image",
                           f"image not found: {img.src}",
                           module_id=mid, location=loc)

        # 2. Links.
        for link in module.links:
            if link.is_os_embed:
                # Interactive exercise pulled from OpenStax's system; can't print.
                continue  # summarised below to avoid one line per exercise
            if link.document:
                _check_cross_module_link(report, link, mid, loc, included_ids, load)
            elif link.target_id:
                if link.target_id not in module.ids:
                    report.add(ERROR, "broken-anchor",
                               f"target-id '{link.target_id}' not found in this module",
                               module_id=mid, location=loc)
            elif link.is_external:
                pass  # external web links are fine; counted in summary

        # 3. Interactive content that won't survive to print.
        n_embed = sum(1 for l in module.links if l.is_os_embed)
        if n_embed:
            report.add(WARN, "os-embed",
                       f"{n_embed} interactive exercise(s) won't render in print",
                       module_id=mid, location=loc)
        if module.iframes:
            report.add(WARN, "iframe",
                       f"{len(module.iframes)} embedded iframe(s) (video/interactive) won't print",
                       module_id=mid, location=loc)

    if check_orphans:
        _report_orphans(report, ws, referenced_media)

    return report


def _check_cross_module_link(report, link, mid, loc, included_ids, load) -> None:
    target = link.document
    tmod = load(target)
    if tmod is None:
        report.add(ERROR, "missing-target-module",
                   f"link to module '{target}' which is not on disk",
                   module_id=mid, location=loc)
        return
    if target not in included_ids:
        report.add(WARN, "dangling-xref",
                   f"links to module '{target}' ({tmod.title!r}) which is NOT in this "
                   f"collection — reference will dangle",
                   module_id=mid, location=loc)
    if link.target_id and link.target_id not in tmod.ids:
        report.add(WARN, "broken-xref-anchor",
                   f"links to '{target}#{link.target_id}' but that id is absent in the target",
                   module_id=mid, location=loc)


def _report_orphans(report, ws: Workspace, referenced: set[Path]) -> None:
    for media_dir in ws.media_dirs():
        for f in sorted(media_dir.iterdir()):
            if f.name.startswith("."):
                continue
            if f.is_file() and f.resolve() not in referenced:
                rel = f.relative_to(ws.repo_root) if ws.repo_root in f.parents else f
                report.add(INFO, "orphan-media",
                           f"{rel} is not referenced by any included module")


def print_report(report: Report, collection: Collection, workspace: Workspace | None = None) -> None:
    order = {ERROR: 0, WARN: 1, INFO: 2}
    issues = sorted(report.issues, key=lambda i: (order[i.severity], i.category, i.module_id or ""))

    print(f"\nCollection: {collection.title}")
    print(f"  {collection.path}")
    print(f"  modules referenced: {len(collection.module_refs())}  "
          f"(unique: {len(collection.module_ids())})")
    print(f"  modules parsed:     {report.modules_checked}")
    if workspace:
        print("  sources:")
        for s in workspace.sources:
            tag = " (upstream)" if s.is_upstream else ""
            print(f"    - {s.name}{tag}: {len(s.module_ids())} modules")
    print()

    if not issues:
        print("No issues found.\n")
    else:
        for issue in issues:
            print("  " + issue.format())
        print()

    print(f"Summary: {report.error_count} error(s), {report.warn_count} warning(s), "
          f"{len(report.by_severity(INFO))} info.\n")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate an OpenStax collection subset.")
    parser.add_argument("collection", nargs="?",
                        help="path to a *.collection.xml (default: the one in collections/)")
    parser.add_argument("--orphans", action="store_true",
                        help="also list media files not referenced by any included module")
    args = parser.parse_args(argv)

    # Repo root = two levels up from this file (tools/oscompile/validate.py).
    repo_root = Path(__file__).resolve().parents[2]

    coll_path = Path(args.collection) if args.collection else _default_collection(repo_root)
    if coll_path is None or not coll_path.exists():
        parser.error(f"collection file not found: {coll_path}")

    collection = parse_collection(coll_path)
    workspace = discover_workspace(repo_root)
    report = build_report(collection, repo_root, check_orphans=args.orphans, workspace=workspace)
    print_report(report, collection, workspace)
    return 1 if report.error_count else 0


def _default_collection(repo_root: Path) -> Path | None:
    """The book's canonical collection, per META-INF/books.xml if present.

    Falls back to the only *.collection.xml if there's exactly one, otherwise
    returns None (so we don't silently validate the wrong file when several exist).
    """
    books = repo_root / "META-INF" / "books.xml"
    if books.exists():
        try:
            root = ET.parse(books).getroot()
            for book in root.iter():
                if book.tag.split("}", 1)[-1] == "book" and book.get("href"):
                    href = (repo_root / "META-INF" / book.get("href")).resolve()
                    if href.exists():
                        return href
        except ET.ParseError:
            pass

    coll_dir = repo_root / "collections"
    files = sorted(coll_dir.glob("*.collection.xml")) if coll_dir.is_dir() else []
    return files[0] if len(files) == 1 else None


if __name__ == "__main__":
    raise SystemExit(main())
