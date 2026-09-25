"""告警中心业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "alarm"
REQUIRED_FIELDS = ["告警编号", "告警类型", "告警等级"]
STATUS_ORDER = ["待确认", "已确认", "已处置", "已忽略"]
ACTION_RULES = {"确认告警": "已确认", "处置告警": "已处置", "忽略告警": "已忽略"}
NEGATIVE_ACTIONS = ["忽略告警"]
TERMINAL_STATUSES = ["已忽略"]


class AlarmService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("告警编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def stats(self) -> dict[str, int]:
        """统计卡片口径：待确认告警与列表按 status==待确认 过滤的条数同源，保证卡片和列表对得上。"""
        rows = store.rows(MODULE)
        return {
            "今日告警": len(rows),
            "待确认告警": sum(1 for row in rows if row.get("status") == STATUS_ORDER[0]),
            "高等级告警": sum(1 for row in rows if "高" in str(row.get("告警等级", ""))),
        }

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"告警事件 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于告警中心可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        if entry.get("status") == target:
            return entry, f"告警事件已是「{target}」状态，重复提交只生效一次"
        if entry.get("status") in TERMINAL_STATUSES:
            return None, f"告警事件已处于「{entry.get('status')}」状态，不能再执行{action}"
        entry["status"] = target
        # 工作台按 pending 统计待确认数量，只有「待确认」才计入；动作落库后即清零，
        # 保证工作台待确认数与列表按状态过滤的条数一致
        entry["pending"] = target == STATUS_ORDER[0]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"告警事件已{action}"
