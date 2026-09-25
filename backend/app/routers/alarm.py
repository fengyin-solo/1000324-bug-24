"""告警中心接口：维护告警事件，覆盖确认告警、处置告警、忽略告警等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.alarm import AlarmService

router = APIRouter(prefix="/api/alarm", tags=["告警中心"])

service = AlarmService()

LIST_FIELDS = ["告警编号", "告警类型", "告警等级", "触发设备", "触发时间", "确认人员", "处置说明", "告警状态"]
STATUSES = ["待确认", "已确认", "已处置", "已忽略"]


class AlarmActionPayload(BaseModel):
    """动作提交体：兼容扁平 {action} 与 {values: {action, ...}} 两种写法。"""

    action: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, alias="告警编号", description="按告警编号检索"),
    status: str | None = Query(default=None, description="待确认、已确认、已处置、已忽略"),
    alarm_type: str | None = Query(default=None, alias="告警类型", description="按告警类型检索"),
    level: str | None = Query(default=None, alias="告警等级", description="按告警等级检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按告警编号与状态过滤告警中心列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        alarm_type=alarm_type,
        level=level,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats(
    keyword: str | None = Query(default=None, alias="告警编号", description="与列表一致的告警编号检索"),
    alarm_type: str | None = Query(default=None, alias="告警类型", description="与列表一致的告警类型"),
    level: str | None = Query(default=None, alias="告警等级", description="与列表一致的告警等级"),
    status: str | None = Query(default=None, description="与列表一致的状态过滤"),
) -> dict[str, int]:
    """工作台与页面统计卡片：待确认数量与列表按相同条件核对时保持同一口径。"""
    return service.stats(keyword=keyword, alarm_type=alarm_type, level=level, status=status)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出告警中心清单：返回全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "alarm", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条告警事件明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"告警事件 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条告警事件，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="告警事件已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: AlarmActionPayload) -> ActionResult:
    """对单条告警事件执行确认告警、处置告警、忽略告警；不允许的动作会被拦下并说明原因。"""
    values = dict(payload.values or {})
    action = str(payload.action or values.pop("action", "") or "").strip()
    if payload.remark and not str(values.get("处置说明") or "").strip():
        values["处置说明"] = payload.remark
    entry, message = service.run_action(entry_id, action, values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
