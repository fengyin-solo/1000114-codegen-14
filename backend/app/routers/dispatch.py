"""调度派单接口：维护调度单，覆盖确认派单、确认发车、撤销派单等动作。

所有接口都带岗位身份，权限判定集中在 DispatchService，路由层只负责把身份透传
并把越权结果以 ok=False + 原因的形式驳回。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import Principal, get_principal
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.dispatch import DispatchService

router = APIRouter(prefix="/api/dispatch", tags=["调度派单"])

service = DispatchService()

STATUSES = ["待派单", "已派单", "已发车", "已撤销"]


@router.get("/scope")
def dispatch_scope(principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    """当前岗位在调度页的可见列、动作入口与可建车队边界。"""
    return service.scope(principal)


@router.get("/export")
def export_entries(principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    """导出调度派单清单：字段范围与列表接口保持同一套岗位投影。"""
    items, total = service.list_entries(principal, page=1, size=10000)
    return {"module": "dispatch", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按调度单号检索"),
    status: str | None = Query(default=None, description="待派单、已派单、已发车、已撤销"),
    page: int = 1,
    size: int = 20,
    principal: Principal = Depends(get_principal),
) -> PageResult[dict]:
    """按调度单号与状态过滤调度派单列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        principal, keyword=keyword, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int, principal: Principal = Depends(get_principal)) -> dict:
    """读取单条调度单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(principal, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"调度单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(
    payload: EntryPayload, principal: Principal = Depends(get_principal)
) -> ActionResult:
    """登记一条调度单：仅调度员、仅限本车队；缺字段或越权都注明原因。"""
    entry, missing, deny = service.create_entry(principal, payload.values)
    if deny:
        return ActionResult(ok=False, message=deny)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="调度单已登记", entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def update_entry(
    entry_id: int,
    payload: EntryPayload,
    principal: Principal = Depends(get_principal),
) -> ActionResult:
    """修改调度单：仅本车队管理员，且只接受白名单字段；越权一律驳回。"""
    entry, message = service.update_entry(principal, entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    principal: Principal = Depends(get_principal),
) -> ActionResult:
    """对单条调度单执行确认派单、确认发车、撤销派单；越权动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(principal, entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
