#!/usr/bin/env python3
"""Aggregate per-plugin ``plugin.toml`` deps into root ``pyproject.toml``.

Walks ``src/plugins/*/plugin.toml`` and rewrites a single marker-delimited
``[tool.poetry.group.plugins.dependencies]`` block inside the root
``pyproject.toml``. Only the region between the BEGIN/END markers is touched;
everything else in the file is preserved verbatim.

Conflicting version pins across plugins are a hard error.

Usage
-----
    python scripts/sync_plugin_deps.py            # rewrite
    python scripts/sync_plugin_deps.py --check    # exit 1 if pyproject would change
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "src" / "plugins"
PYPROJECT = REPO_ROOT / "pyproject.toml"

BEGIN_MARKER = "# === BEGIN GENERATED PLUGIN DEPS — do not edit by hand ==="
END_MARKER = "# === END GENERATED PLUGIN DEPS ==="
GROUP_HEADER = "[tool.poetry.group.plugins.dependencies]"


def _format_pin(spec: dict | str) -> str:
    """Render a dep value the way Poetry expects it in TOML."""
    if isinstance(spec, str):
        return f'"{spec}"'
    version = spec.get("version")
    extras = spec.get("extras")
    if extras:
        parts = [f'version = "{version}"', f"extras = {extras!r}".replace("'", '"')]
        return "{ " + ", ".join(parts) + " }"
    return f'"{version}"'


def collect_plugin_deps() -> tuple[dict[str, dict | str], dict[str, list[tuple[str, dict | str]]], list[str]]:
    """Read every plugin.toml and merge their ``[dependencies]`` tables.

    Returns ``(merged_deps, seen, plugin_names)`` where *seen* maps each package
    name to the list of ``(plugin_name, spec)`` entries that declared it
    (also used for conflict reporting). Raises ``SystemExit`` on conflicts.
    """
    merged: dict[str, dict | str] = {}
    seen: dict[str, list[tuple[str, dict | str]]] = {}
    plugin_names: list[str] = []

    if not PLUGINS_DIR.is_dir():
        return merged, seen, plugin_names

    for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name.startswith("_"):
            continue
        manifest_path = plugin_dir / "plugin.toml"
        if not manifest_path.is_file():
            continue
        plugin_names.append(plugin_dir.name)
        with manifest_path.open("rb") as fh:
            data = tomllib.load(fh)
        deps = data.get("dependencies") or {}
        for pkg, spec in deps.items():
            # ``import`` is runtime metadata; poetry doesn't understand it.
            poetry_spec: dict | str
            if isinstance(spec, dict):
                poetry_spec = {k: v for k, v in spec.items() if k != "import"}
                if list(poetry_spec.keys()) == ["version"]:
                    poetry_spec = poetry_spec["version"]
            else:
                poetry_spec = spec
            seen.setdefault(pkg, []).append((plugin_dir.name, poetry_spec))
            merged[pkg] = poetry_spec

    conflicts = {
        pkg: entries
        for pkg, entries in seen.items()
        if len({repr(spec) for _, spec in entries}) > 1
    }
    if conflicts:
        print("Conflicting plugin dependency pins:", file=sys.stderr)
        for pkg, entries in conflicts.items():
            print(f"  {pkg}:", file=sys.stderr)
            for plugin_name, spec in entries:
                print(f"    - {plugin_name}: {spec!r}", file=sys.stderr)
        raise SystemExit(2)

    return merged, seen, plugin_names


def render_block(deps: dict[str, dict | str], seen: dict[str, list[tuple[str, dict | str]]]) -> str:
    # Group each dep under its alphabetically-first declaring plugin so the
    # block reads as one section per plugin. Shared deps surface only once.
    by_plugin: dict[str, list[str]] = {}
    for pkg in deps:
        owner = sorted({name for name, _ in seen.get(pkg, [])})[0]
        by_plugin.setdefault(owner, []).append(pkg)

    width = max((len(p) for p in deps), default=0)
    lines = [BEGIN_MARKER, GROUP_HEADER]
    for plugin in sorted(by_plugin):
        lines.append("")
        lines.append(f"# {plugin}")
        for pkg in sorted(by_plugin[plugin]):
            lines.append(f"{pkg.ljust(width)} = {_format_pin(deps[pkg])}")
    lines.append(END_MARKER)
    return "\n".join(lines)


def splice_block(pyproject_text: str, block: str) -> str:
    """Replace the existing generated block, or append it after [tool.poetry.dependencies]."""
    pattern = re.compile(
        re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER),
        re.DOTALL,
    )
    if pattern.search(pyproject_text):
        return pattern.sub(block, pyproject_text)

    # First-time insert: place after the [tool.poetry.dependencies] table.
    deps_header = "[tool.poetry.dependencies]"
    idx = pyproject_text.find(deps_header)
    if idx == -1:
        raise SystemExit("Could not find [tool.poetry.dependencies] in pyproject.toml")
    # Find the start of the next top-level section after deps_header.
    next_section = re.search(r"\n\[", pyproject_text[idx + len(deps_header):])
    insert_at = (
        idx + len(deps_header) + (next_section.start() if next_section else len(pyproject_text))
    )
    return (
        pyproject_text[:insert_at].rstrip()
        + "\n\n"
        + block
        + "\n"
        + pyproject_text[insert_at:]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if pyproject.toml would change; do not write.",
    )
    args = parser.parse_args()

    deps, seen, plugins = collect_plugin_deps()
    block = render_block(deps, seen)
    current = PYPROJECT.read_text()
    updated = splice_block(current, block)

    if args.check:
        if updated != current:
            print(
                "pyproject.toml is out of sync with plugin manifests. "
                "Run `python scripts/sync_plugin_deps.py`.",
                file=sys.stderr,
            )
            return 1
        return 0

    if updated == current:
        print(f"pyproject.toml already in sync ({len(deps)} deps from {len(plugins)} plugins).")
        return 0

    PYPROJECT.write_text(updated)
    print(
        f"Synced {len(deps)} deps from {len(plugins)} plugins "
        f"({', '.join(plugins) or 'none'}) into pyproject.toml."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
