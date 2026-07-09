"""Discover and resolve modules across multiple content sources.

The repo root is the OpenStax neuroscience upstream (`modules/`, `media/`,
`collections/`). Additional origins live under `sources/<name>/` — each with its
own `modules/`, `media/`, and a `SOURCE.md` provenance manifest (see
sources/README.md). This module ties them together so the validator and builder
can resolve a module id to a file regardless of which source it came from, know
where each module originated (for the provenance appendix), and flag id/media
collisions across sources.

Module ids are expected to be globally unique (neuroscience keeps its native
`m0000x`; imported/own sources use prefixed ids like `evo-m00012`). If two
sources define the same id, that's a collision we surface rather than guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .collection import parse_collection


@dataclass
class Source:
    """One content origin: the upstream neuroscience book, or a sources/<name> dir."""

    name: str                       # display name
    slug: str                       # short tag (matches module-id prefix for imports)
    root: Path                      # base dir of the source
    modules_dir: Path
    media_dir: Path | None
    is_upstream: bool = False       # the neuroscience root synced via git
    license: str | None = None
    origin: str | None = None       # repo URL / citation
    manifest: dict = field(default_factory=dict)

    def module_ids(self) -> list[str]:
        if not self.modules_dir.is_dir():
            return []
        return sorted(
            d.name for d in self.modules_dir.iterdir()
            if d.is_dir() and (d / "index.cnxml").exists()
        )


@dataclass
class Workspace:
    repo_root: Path
    sources: list[Source]
    index: dict[str, tuple[Source, Path]]        # module_id -> (source, index.cnxml)
    collisions: dict[str, list[str]]             # module_id -> source names (len > 1)

    # -- resolution --------------------------------------------------------

    def resolve(self, module_id: str) -> Path | None:
        hit = self.index.get(module_id)
        return hit[1] if hit else None

    def source_of(self, module_id: str) -> Source | None:
        hit = self.index.get(module_id)
        return hit[0] if hit else None

    def all_module_ids(self) -> set[str]:
        return set(self.index)

    def media_dirs(self) -> list[Path]:
        return [s.media_dir for s in self.sources if s.media_dir and s.media_dir.is_dir()]

    def media_collisions(self) -> dict[str, list[str]]:
        """Filenames present in more than one source's media dir (ambiguous for
        \\graphicspath, which resolves to whichever source comes first)."""
        seen: dict[str, list[str]] = {}
        for s in self.sources:
            if not (s.media_dir and s.media_dir.is_dir()):
                continue
            for f in s.media_dir.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    seen.setdefault(f.name, []).append(s.name)
        return {name: srcs for name, srcs in seen.items() if len(srcs) > 1}


def _parse_frontmatter(path: Path) -> dict:
    """Minimal YAML-frontmatter reader (stdlib only): `key: value` pairs and
    simple `- item` lists. Enough for SOURCE.md manifests."""
    text = path.read_text(encoding="utf-8")
    if not text.lstrip().startswith("---"):
        return {}
    body = text.lstrip()[3:]
    end = body.find("\n---")
    if end == -1:
        return {}
    data: dict = {}
    list_key: str | None = None
    for line in body[:end].splitlines():
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and list_key:
            data.setdefault(list_key, []).append(stripped[2:].strip())
            continue
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            if val:
                data[key], list_key = val, None
            else:
                data[key], list_key = [], key
    return data


def _discover_upstream(repo_root: Path) -> Source:
    """The neuroscience root; name/license read from its collection metadata."""
    name, license_text, origin = "Introduction to Behavioral Neuroscience (OpenStax)", None, None
    coll_dir = repo_root / "collections"
    colls = sorted(coll_dir.glob("*.collection.xml")) if coll_dir.is_dir() else []
    if colls:
        try:
            c = parse_collection(colls[0])
            name = c.title or name
            license_text = c.license_text
        except Exception:
            pass
    return Source(
        name=name, slug="neuro", root=repo_root,
        modules_dir=repo_root / "modules", media_dir=repo_root / "media",
        is_upstream=True, license=license_text,
        origin="https://github.com/openstax/osbooks-neuroscience",
    )


def _discover_extra(source_dir: Path) -> Source | None:
    modules_dir = source_dir / "modules"
    if not modules_dir.is_dir():
        return None
    manifest_path = source_dir / "SOURCE.md"
    m = _parse_frontmatter(manifest_path) if manifest_path.exists() else {}
    media = source_dir / "media"
    return Source(
        name=m.get("name", source_dir.name),
        slug=m.get("slug", source_dir.name),
        root=source_dir,
        modules_dir=modules_dir,
        media_dir=media if media.is_dir() else None,
        license=m.get("license"),
        origin=m.get("origin"),
        manifest=m,
    )


def discover_workspace(repo_root: str | Path) -> Workspace:
    repo_root = Path(repo_root)
    sources: list[Source] = [_discover_upstream(repo_root)]

    sources_root = repo_root / "sources"
    if sources_root.is_dir():
        for d in sorted(sources_root.iterdir()):
            if d.is_dir():
                src = _discover_extra(d)
                if src:
                    sources.append(src)

    index: dict[str, tuple[Source, Path]] = {}
    collisions: dict[str, list[str]] = {}
    for src in sources:
        for mid in src.module_ids():
            path = src.modules_dir / mid / "index.cnxml"
            if mid in index:
                collisions.setdefault(mid, [index[mid][0].name]).append(src.name)
            else:
                index[mid] = (src, path)
    return Workspace(repo_root=repo_root, sources=sources, index=index, collisions=collisions)
