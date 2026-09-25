"""告警中心业务规则：状态流转、字段校验与筛选口径都收在这里。

告警状态只有四类：待确认、已确认、已处置、已忽略。状态机约定：
- 只有「待确认」的告警需要处理，工作台卡片按这一口径统计；
- 「已忽略」「已处置」是终态，忽略掉的告警不能再被其他动作改回去；
- 同一条告警重复提交同一动作只生效一次，直接返回当前状态，不产生新记录。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "alarm"
REQUIRED_FIELDS = ["告警编号", "告警类型", "告警等级"]
STATUS_FIELD = "告警状态"
CONFIRMER_FIELD = "确认人员"
DISPOSAL_FIELD = "处置说明"
PENDING_STATUS = "待确认"
IGNORED_STATUS = "已忽略"
STATUS_ORDER = ["待确认", "已确认", "已处置", "已忽略"]
ACTION_RULES = {"确认告警": "已确认", "处置告警": "已处置", "忽略告警": "已忽略"}
TERMINAL_STATUSES = ["已处置", "已忽略"]
HIGH_LEVELS = ["紧急", "严重", "高"]


class AlarmService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        alarm_type: str | None = None,
        level: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("告警编号", ""))]
        if alarm_type:
            rows = [row for row in rows if alarm_type in str(row.get("告警类型", ""))]
        if level:
            rows = [row for row in rows if level in str(row.get("告警等级", ""))]
        if status:
            rows = [row for row in rows if self._display_status(row) == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def stats(
        self,
        keyword: str | None = None,
        alarm_type: str | None = None,
        level: str | None = None,
        status: str | None = None,
    ) -> dict[str, int]:
        """统计卡片口径：待确认数量与按相同条件过滤后的列表保持一致。"""
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("告警编号", ""))]
        if alarm_type:
            rows = [row for row in rows if alarm_type in str(row.get("告警类型", ""))]
        if level:
            rows = [row for row in rows if level in str(row.get("告警等级", ""))]
        visible = [row for row in rows if not status or self._display_status(row) == status]
        return {
            "total": len(visible),
            "pending": sum(1 for row in visible if self._display_status(row) == PENDING_STATUS),
            "high_level": sum(
                1 for row in visible if str(row.get("告警等级") or "").strip() in HIGH_LEVELS
            ),
        }

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in ("触发设备", "触发时间"):
            if values.get(field) is not None:
                entry[field] = values[field]
        entry["status"] = PENDING_STATUS
        entry[STATUS_FIELD] = PENDING_STATUS
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"告警事件 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于告警中心可执行范围"
        current = self._display_status(entry)
        target = ACTION_RULES[action]
        if current in TERMINAL_STATUSES and current != target:
            return None, f"告警状态为{current}，不能再执行「{action}」"
        # 幂等：同一动作重复提交只生效一次，保留第一次的确认人员与处置说明。
        if current == target:
            return entry, f"告警状态已是{target}，请勿重复提交"
        values = values or {}
        if action == "确认告警":
            operator = str(values.get(CONFIRMER_FIELD) or "").strip()
            if operator and not str(entry.get(CONFIRMER_FIELD) or "").strip():
                entry[CONFIRMER_FIELD] = operator
        elif action == "处置告警":
            note = str(values.get(DISPOSAL_FIELD) or "").strip()
            if note:
                entry[DISPOSAL_FIELD] = note
        self._apply_status(entry, target)
        return entry, f"告警状态已更新为{target}"

    def _apply_status(self, entry: dict[str, Any], target: str) -> None:
        """统一写状态：内部标记、中文状态字段与筛选口径必须保持一致。"""
        entry["status"] = target
        entry[STATUS_FIELD] = target
        entry["pending"] = target == PENDING_STATUS
        entry["abnormal"] = target == IGNORED_STATUS

    def _display_status(self, entry: dict[str, Any]) -> str:
        """以中文状态字段为准展示与筛选，历史数据缺字段时回退到内部状态。"""
        status = str(entry.get(STATUS_FIELD) or entry.get("status") or "").strip()
        return status if status in STATUS_ORDER else PENDING_STATUS
