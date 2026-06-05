"""计分结果数据结构（避免 engine ↔ score_v2 循环引用）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScoreResult:
    """一轮计分结果。"""

    total_score: float
    rating_label: str
    categories: list[dict[str, Any]] = field(default_factory=list)

    @property
    def macro_summary(self) -> str:
        return self._cat_summary("宏观数据")

    def _cat_summary(self, name: str) -> str:
        for c in self.categories:
            if c.get("name") == name:
                return str(c.get("summary", ""))
        return ""
