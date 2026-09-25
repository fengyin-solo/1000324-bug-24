"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS

# 告警中心的「待处理」只统计待确认事件，中文状态字段与内部标记在这里对齐，
# 保证工作台卡片、列表状态过滤从同一口径读数。
_ALARM_STATUS_FIELD = "告警状态"
_ALARM_PENDING_STATUS = "待确认"
_ALARM_IGNORED_STATUS = "已忽略"


def _normalize_alarm(row: dict[str, Any]) -> None:
    status = str(row.get(_ALARM_STATUS_FIELD) or row.get("status") or "").strip()
    if status not in ("待确认", "已确认", "已处置", "已忽略"):
        status = str(row.get("status") or _ALARM_PENDING_STATUS)
    row["status"] = status
    row[_ALARM_STATUS_FIELD] = status
    row["pending"] = status == _ALARM_PENDING_STATUS
    row["abnormal"] = status == _ALARM_IGNORED_STATUS


_NORMALIZERS = {"alarm": _normalize_alarm}


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}
        for name, rows in SEED_ROWS.items():
            table = [dict(row) for row in rows]
            normalize = _NORMALIZERS.get(name)
            if normalize is not None:
                for row in table:
                    normalize(row)
            self._tables[name] = table

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
