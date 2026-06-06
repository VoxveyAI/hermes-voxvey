from __future__ import annotations

from pathlib import Path


def test_no_pricing_page_references():
    root = Path(__file__).resolve().parents[1]
    banned = ["voxvey.com/" + "pricing", "sub" + "scription", "pro/" + "enterprise"]
    offenders = []
    for base in (root / "plugins", root / "README.md"):
        paths = base.rglob("*") if base.is_dir() else [base]
        for path in paths:
            if not path.is_file() or path.suffix not in {"", ".md", ".py", ".yaml", ".yml"}:
                continue
            text = path.read_text(errors="ignore").lower()
            if any(term in text for term in banned):
                offenders.append(str(path.relative_to(root)))
    assert offenders == []
