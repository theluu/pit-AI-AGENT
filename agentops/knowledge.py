from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class RunbookIndex:
    """Zero-dependency retrieval fallback; replaceable by pgvector without graph changes."""

    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).parent.parent / "docs" / "runbooks"

    def search(self, query: str, service: str, limit: int = 3) -> list[dict[str, Any]]:
        terms = set(re.findall(r"[a-z0-9_]{3,}", f"{query} {service}".lower()))
        rows = []
        if not self.root.exists():
            return rows
        for path in self.root.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            for index, section in enumerate(re.split(r"(?=^## )", text, flags=re.MULTILINE)):
                section_terms = set(re.findall(r"[a-z0-9_]{3,}", section.lower()))
                score = len(terms & section_terms)
                if score:
                    heading = section.splitlines()[0].lstrip("# ") if section.splitlines() else path.stem
                    rows.append({"citation_id": f"runbook:{path.stem}:{index}", "document": path.name, "heading": heading, "score": score, "excerpt": section[:700]})
        return sorted(rows, key=lambda row: (-row["score"], row["citation_id"]))[:limit]
