"""调度派单接口：维护调度单，覆盖确认派单、确认发车、撤销派单等动作。

所有入口都先解析操作人身份（岗位 + 归属车队），越权请求一律驳回并在 message 里注明原因。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.security import OperatorContext, operator_context
from app.services.dispatch import DispatchService

router = APIRouter(prefix="/api/dispatch", tags=["调度派单"])

service = DispatchService()


@router.get("/permissions")
def permission_descriptor(ctx: OperatorContext = Depends(operator_context)) -> dict[str, Any]:
    """当前岗位的权限画像：可见列、可下单车队、动作全集，前端据此渲染页面边界。"""
    return service.permission_descriptor(ctx)


@router.get("/export")
def export_entries(ctx: OperatorContext = Depends(operator_context)) -> dict[str, Any]:
    """导出调度派单清单：返回当前过滤条件下的全量数据，敏感字段同样按岗位脱敏。"""
    items, total = service.list_entries(ctx, page=1, size=10000)
    return {"module": "dispatch", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按调度单号检索"),
    status: str | None = Query(default=None, description="待派单、已派单、已发车、已撤销"),
    page: int = 1,
    size: int = 20,
    ctx: OperatorContext = Depends(operator_context),
) -> PageResult[dict]:
    """按调度单号与状态过滤调度派单列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(ctx, keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int, ctx: OperatorContext = Depends(operator_context)) -> dict:
    """读取单条调度单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(ctx, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"调度单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(
    payload: EntryPayload, ctx: OperatorContext = Depends(operator_context)
) -> ActionResult:
    """登记一条调度单；缺字段或车队越权时说明原因，不静默丢弃。"""
    entry, error = service.create_entry(ctx, payload.values)
    if error is not None:
        return ActionResult(ok=False, message=error)
    return ActionResult(ok=True, message="调度单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int, payload: EntryPayload, ctx: OperatorContext = Depends(operator_context)
) -> ActionResult:
    """对单条调度单执行确认派单、确认发车、撤销派单；越权或不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(ctx, entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
