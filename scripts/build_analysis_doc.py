#!/usr/bin/env python3
"""
Build SHOUDAO_ANALYSIS.md - a complete codebase dump for AI analysis.
Similar to HaoLine's HAOLINE_ANALYSIS.md pattern.
"""

from datetime import datetime
from pathlib import Path

# Project root
ROOT = Path(__file__).parent.parent

# File patterns to include
MD_FILES = [
    "README.md",
    "ShouDao_PRD.md",
    "ShouDao_BACKLOG.md",
    "ARCHITECTURE.md",
]

PY_DIRS = [
    "src/shoudao",
    "tests",
    "scripts",
]

EXCLUDE_PATTERNS = [
    "__pycache__",
    ".pyc",
    "venv",
    ".egg-info",
]


def should_include(path: Path) -> bool:
    """Check if file should be included."""
    path_str = str(path)
    return not any(ex in path_str for ex in EXCLUDE_PATTERNS)


def collect_files() -> tuple[list[Path], list[Path]]:
    """Collect markdown and Python files."""
    md_files = []
    py_files = []

    # Collect markdown files
    for name in MD_FILES:
        path = ROOT / name
        if path.exists():
            md_files.append(path)

    # Collect Python files
    for dir_name in PY_DIRS:
        dir_path = ROOT / dir_name
        if dir_path.exists():
            for py_file in dir_path.rglob("*.py"):
                if should_include(py_file):
                    py_files.append(py_file)

    return md_files, py_files


def file_to_anchor(path: Path) -> str:
    """Convert file path to markdown anchor."""
    rel = path.relative_to(ROOT)
    return str(rel).replace("/", "").replace("\\", "").replace(".", "").lower()


def build_toc(md_files: list[Path], py_files: list[Path]) -> str:
    """Build table of contents."""
    lines = ["## Table of Contents", "", "### Documentation Files", ""]

    for path in md_files:
        rel = path.relative_to(ROOT)
        anchor = file_to_anchor(path)
        lines.append(f"- [{rel}](#{anchor})")

    lines.extend(["", "### Python Files", ""])

    current_dir = None
    for path in sorted(py_files):
        rel = path.relative_to(ROOT)
        dir_name = str(rel.parent)

        if dir_name != current_dir:
            current_dir = dir_name
            lines.append(f"\n**{dir_name}/**\n")

        anchor = file_to_anchor(path)
        lines.append(f"- [{rel.name}](#{anchor})")

    return "\n".join(lines)


def build_content(md_files: list[Path], py_files: list[Path]) -> str:
    """Build file contents section."""
    lines = []

    # Documentation files
    lines.append("\n---\n\n# Documentation Files\n")

    for path in md_files:
        rel = path.relative_to(ROOT)
        anchor = file_to_anchor(path)
        content = path.read_text(encoding="utf-8")

        lines.append(f"\n## {rel}\n")
        lines.append(f"<a id=\"{anchor}\"></a>\n")
        lines.append(content)
        lines.append("\n---\n")

    # Python files
    lines.append("\n# Python Files\n")

    for path in sorted(py_files):
        rel = path.relative_to(ROOT)
        anchor = file_to_anchor(path)
        content = path.read_text(encoding="utf-8")

        lines.append(f"\n## {rel}\n")
        lines.append(f"<a id=\"{anchor}\"></a>\n")
        lines.append(f"```python\n{content}\n```\n")
        lines.append("\n---\n")

    return "\n".join(lines)


def main() -> None:
    """Generate the analysis document."""
    md_files, py_files = collect_files()

    total_files = len(md_files) + len(py_files)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    header = f"""# ShouDao Complete Codebase Analysis Document

**Generated:** {timestamp}
**Total Files:** {total_files} ({len(md_files)} .md, {len(py_files)} .py)

> This document contains all documentation and Python source code
> from the ShouDao repository for comprehensive AI analysis.

---

"""

    toc = build_toc(md_files, py_files)
    content = build_content(md_files, py_files)

    output = header + toc + content
    output_path = ROOT / "SHOUDAO_ANALYSIS.md"
    output_path.write_text(output, encoding="utf-8")

    print(f"Generated: {output_path}")
    print(f"Total files: {total_files}")


if __name__ == "__main__":
    main()

