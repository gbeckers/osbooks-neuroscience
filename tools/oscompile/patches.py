"""Declarative content patches: keep upstream modules pristine, express course
customizations (omit a paragraph, drop the always-empty Multiple-Choice section,
swap a phrase) as a small YAML overlay applied to the parsed CNXML tree at build
time.

Why this exists
---------------
`modules/` is synced verbatim from OpenStax (`git merge upstream/main`). Editing a
module in place turns every future sync into a merge conflict. A patch instead
names its target by a **unique text fragment**, not a line number, so it keeps
applying across upstream edits. And when a fragment no longer matches -- because
OpenStax reworded that passage -- the build *fails loudly*, naming the module and
the fragment, instead of silently dropping the wrong thing or diverging unnoticed.

Directives
----------
* ``delete``        -- remove the innermost block element (para / figure / item /
                       note / table / ...) whose text contains an anchor fragment.
* ``drop-sections`` -- remove whole ``<section>``s by their ``<title>`` text.
* ``replace``       -- swap one run of literal text (``find`` -> ``with``) inside a
                       single text node.

``delete`` and ``replace`` are strict: the anchor must match **exactly one** place,
else it is an error (0 = upstream changed / typo; >1 = ambiguous, add context).
``drop-sections`` is lenient: it removes every matching section and zero is fine,
so a global rule can list "Multiple Choice" without every module having one.

Scope / file layout
-------------------
A ``patches/`` directory next to the collection file. Within it:

* ``<module_id>.patch.yaml`` -- applies to that one module.
* ``_all.patch.yaml``        -- applies to *every* module in the build (e.g. the
                                empty Multiple Choice / Fill in the Blank sections).

The file format is a small, fixed YAML subset (stdlib only -- no PyYAML): the three
top-level keys above, each a list. Free-text values (prose fragments, which contain
colons and quotes) should use a ``|`` block scalar so they don't collide with YAML
syntax. See ``reader/topics_core/neuroanatomy/patches/`` for worked examples.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
import xml.etree.ElementTree as ET

CNXML_NS = "http://cnx.rice.edu/cnxml"

_DIRECTIVE_KEYS = ("delete", "replace", "drop-sections")

# Block elements a `delete` anchor may resolve to. A whole <section> is removed via
# drop-sections instead (by title), so it is deliberately not here.
_DELETE_TAGS = {"para", "figure", "media", "table", "note", "example", "quote",
                "item", "list"}


class PatchError(Exception):
    """A patch could not be applied unambiguously (anchor missing/ambiguous, or a
    malformed patch file). Raised so the build stops with a clear message rather
    than producing a silently wrong document."""


# -- matching helpers -----------------------------------------------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _norm(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip. CNXML wraps and
    indents prose, so anchors are compared on normalised text, not byte-for-byte."""
    return re.sub(r"\s+", " ", text).strip()


def _text_of(el: ET.Element) -> str:
    return "".join(el.itertext())


def _is_ancestor(a: ET.Element, b: ET.Element) -> bool:
    return any(x is b for x in a.iter()) and a is not b


# -- applying to a parsed tree --------------------------------------------

def apply_patches(root: ET.Element, module_id: str, patchset: "PatchSet") -> None:
    """Apply the global + per-module directives for `module_id` to `root` in place.
    Order: drop whole sections, then delete blocks, then run replacements on what
    survives (so a `find` inside a dropped block is not required to still exist)."""
    directives = patchset.for_module(module_id)
    if not directives:
        return
    _drop_sections(root, directives.get("drop-sections", []), module_id)
    _delete_blocks(root, directives.get("delete", []), module_id)
    _replace_text(root, directives.get("replace", []), module_id)


def _parent_map(root: ET.Element) -> dict:
    return {child: parent for parent in root.iter() for child in parent}


def _section_heading(sec: ET.Element) -> str:
    """The heading a reader sees for a <section>: its own <title> if it has one,
    else -- for an untitled wrapper section that just groups a titled <note>/<figure>
    -- the first <title> appearing inside it (document order)."""
    first = next(sec.iter(f"{{{CNXML_NS}}}title"), None)
    return _norm(_text_of(first)) if first is not None else ""


def _drop_sections(root: ET.Element, titles, module_id: str) -> None:
    for title in titles:
        want = _norm(title)
        parents = _parent_map(root)  # rebuilt each pass; trees are small
        for sec in list(root.iter()):
            if _local(sec.tag) != "section" or sec not in parents:
                continue
            if _section_heading(sec) == want:
                parents[sec].remove(sec)
        # drop-sections is lenient: a global rule ("Multiple Choice") legitimately
        # matches nothing in modules that lack that section.


def _delete_blocks(root: ET.Element, anchors, module_id: str) -> None:
    for anchor in anchors:
        want = _norm(anchor)
        candidates = [el for el in root.iter()
                      if _local(el.tag) in _DELETE_TAGS and want in _norm(_text_of(el))]
        # Keep only the innermost matches (drop any candidate that is an ancestor of
        # another candidate) so an anchor in a <para> deletes the para, not the
        # <section>/<list> that also contains it.
        innermost = [el for el in candidates
                     if not any(_is_ancestor(el, other) for other in candidates)]
        if not innermost:
            raise PatchError(
                f"{module_id}: delete anchor not found (upstream may have reworded "
                f"it): {anchor!r}")
        if len(innermost) > 1:
            raise PatchError(
                f"{module_id}: delete anchor matches {len(innermost)} elements; add "
                f"more context to make it unique: {anchor!r}")
        target = innermost[0]
        _parent_map(root)[target].remove(target)


def _replace_text(root: ET.Element, rules, module_id: str) -> None:
    for rule in rules:
        if not isinstance(rule, dict) or "find" not in rule:
            raise PatchError(f"{module_id}: each replace rule needs 'find' and "
                             f"'with' keys, got: {rule!r}")
        find = rule["find"]
        repl = rule.get("with", "")
        want = _norm(find)
        # Whitespace-tolerant matcher: the source may wrap the phrase differently.
        pattern = re.compile(r"\s+".join(re.escape(w) for w in want.split()))
        hits = []
        for el in root.iter():
            for attr in ("text", "tail"):
                s = getattr(el, attr)
                if s and pattern.search(s):
                    hits.append((el, attr))
        if not hits:
            raise PatchError(
                f"{module_id}: replace 'find' not found -- it may have been reworded "
                f"upstream, or it spans inline markup (a <term>/<link> splits the "
                f"run across text nodes): {find!r}")
        if len(hits) > 1:
            raise PatchError(
                f"{module_id}: replace 'find' matches {len(hits)} places; add context "
                f"to make it unique: {find!r}")
        el, attr = hits[0]
        # lambda replacement so backslashes/\1 in `repl` are taken literally.
        setattr(el, attr, pattern.sub(lambda _m: repl, getattr(el, attr), count=1))


# -- loading patch files (tiny YAML-subset parser, stdlib only) -----------

@dataclass
class PatchSet:
    """All patches discovered next to a collection: a global set applied to every
    module, plus per-module sets keyed by module id."""

    global_directives: dict = field(default_factory=dict)
    per_module: dict = field(default_factory=dict)

    def for_module(self, module_id: str) -> dict | None:
        g = self.global_directives
        m = self.per_module.get(module_id)
        if not g and not m:
            return None
        merged = {k: [] for k in _DIRECTIVE_KEYS}
        for src in (g, m):
            for k in _DIRECTIVE_KEYS:
                merged[k] += (src or {}).get(k, [])
        return merged

    def module_ids(self) -> set[str]:
        return set(self.per_module)


def _merge_directives(a: dict, b: dict) -> dict:
    """Concatenate the directive lists of two directive dicts (b's appended after
    a's), so a module patched by both a shared and a collection-specific file gets
    both sets of edits."""
    out = {k: [] for k in _DIRECTIVE_KEYS}
    for src in (a, b):
        for k in _DIRECTIVE_KEYS:
            out[k] += (src or {}).get(k, [])
    return out


def _load_patch_dir(pdir: Path):
    """Read one `patches/` dir. Returns (global directives from _all.patch.yaml,
    {module_id: directives})."""
    global_directives: dict = {}
    per_module: dict = {}
    if pdir.is_dir():
        for f in sorted(pdir.glob("*.patch.yaml")):
            directives = _parse_patch_yaml(f.read_text(encoding="utf-8"), f)
            stem = f.name[: -len(".patch.yaml")]
            if stem == "_all":
                global_directives = directives
            else:
                per_module[stem] = directives
    return global_directives, per_module


def load_patchset(patch_dirs) -> PatchSet:
    """Build a PatchSet from an ordered list of `patches/` dirs (e.g. a shared
    repo-level dir, then the collection's own). Later dirs *add* to earlier ones, so
    the same module can carry shared edits plus reader-specific ones. Dirs that
    resolve to the same path (the main reader's own dir *is* the shared dir) are
    loaded once."""
    ps = PatchSet()
    seen: set = set()
    for d in patch_dirs:
        if d is None:
            continue
        pdir = Path(d).resolve()
        if pdir in seen:
            continue
        seen.add(pdir)
        g, per_module = _load_patch_dir(pdir)
        ps.global_directives = _merge_directives(ps.global_directives, g)
        for mid, directives in per_module.items():
            ps.per_module[mid] = _merge_directives(ps.per_module.get(mid, {}), directives)
    return ps


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _read_block_scalar(lines, i, min_indent):
    """Collect a `|` block scalar: subsequent lines indented deeper than
    `min_indent` (blank lines allowed). Returns (dedented text, next index)."""
    block = []
    while i < len(lines):
        raw = lines[i]
        if raw.strip() == "":
            block.append("")
            i += 1
            continue
        if _indent_of(raw) <= min_indent:
            break
        block.append(raw)
        i += 1
    non_empty = [ln for ln in block if ln.strip()]
    common = min((_indent_of(ln) for ln in non_empty), default=0)
    text = "\n".join(ln[common:] if ln.strip() else "" for ln in block)
    return text.strip("\n"), i


def _parse_patch_yaml(text: str, path) -> dict:
    """Parse a patch file. Supports exactly the patch schema: top-level directive
    keys, list items that are scalars (inline or `|` block) or {find:, with:} maps.
    Not a general YAML parser -- it raises PatchError on anything outside the schema.
    """
    lines = text.splitlines()
    result: dict = {k: [] for k in _DIRECTIVE_KEYS}
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        if _indent_of(raw) != 0 or not raw.rstrip().endswith(":"):
            raise PatchError(f"{path}: expected a top-level directive, got: {raw!r}")
        key = raw.strip()[:-1].strip()
        if key not in result:
            raise PatchError(f"{path}: unknown directive {key!r} "
                             f"(expected one of {', '.join(_DIRECTIVE_KEYS)})")
        i += 1
        items, i = _parse_list(lines, i, key, path)
        result[key] = items
    return result


def _parse_list(lines, i, key, path):
    items = []
    n = len(lines)
    while i < n:
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        indent = _indent_of(raw)
        stripped = raw.strip()
        if indent == 0 or not stripped.startswith("-"):
            break  # dedented back to a top-level key (or past this list)
        after = stripped[1:].strip()
        if key == "replace":
            item, i = _parse_replace_item(lines, i, indent, after, path)
            items.append(item)
        elif after == "|":
            val, i = _read_block_scalar(lines, i + 1, indent)
            items.append(val)
        else:
            items.append(_unquote(after))
            i += 1
    return items, i


def _parse_replace_item(lines, i, item_indent, first_after, path):
    """A replace item is a small map. Its keys (find/with) sit two columns in from
    the dash, the first sharing the `- ` line."""
    m: dict = {}
    key_indent = item_indent + 2
    # First key rides on the `- find: ...` line; its value may follow on later lines.
    i = _absorb_map_entry(lines, i + 1, key_indent, first_after, m, path)
    n = len(lines)
    while i < n:
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        if _indent_of(raw) != key_indent:
            break
        i = _absorb_map_entry(lines, i + 1, key_indent, raw.strip(), m, path)
    return m, i


def _absorb_map_entry(lines, next_i, key_indent, entry, m, path):
    """Record one `key: value` map entry; `value` may be an inline scalar or a `|`
    block scalar continuing on subsequent lines. Returns the next line index."""
    if ":" not in entry:
        raise PatchError(f"{path}: expected 'key: value' in replace item, got {entry!r}")
    k, _, v = entry.partition(":")
    k, v = k.strip(), v.strip()
    if v == "|":
        val, next_i = _read_block_scalar(lines, next_i, key_indent)
    else:
        val = _unquote(v)
    m[k] = val
    return next_i
