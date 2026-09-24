"""调度派单业务规则：状态流转、字段校验、岗位分权与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.security import OperatorContext
from app.store import store

MODULE = "dispatch"
FLEETS = ["华东一队", "华东二队", "华南一队"]
REQUIRED_FIELDS = ["调度单号", "关联订单", "配送线路", "所属车队"]
OPTIONAL_FIELDS = ["指派车辆", "指派司机", "计划发车时间"]
LIST_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS + ["调度状态"]
# 非管辖车队的单子只给基础字段，敏感字段一律脱敏，保证可见范围与权限对齐
SENSITIVE_FIELDS = ["指派车辆", "指派司机", "计划发车时间"]
MASKED_VALUE = "***"
STATUS_ORDER = ["待派单", "已派单", "已发车", "已撤销"]
ACTION_RULES = {"确认派单": "已派单", "确认发车": "已发车", "撤销派单": "已撤销"}
NEGATIVE_ACTIONS = ["撤销派单"]


class DispatchService:
    def permission_descriptor(self, ctx: OperatorContext) -> dict[str, Any]:
        """给前端的权限画像：能看哪些列、能往哪些车队开单、动作全集。"""
        return {
            "role": ctx.role,
            "role_label": ctx.role_label,
            "fleets": ctx.fleets,
            "columns": LIST_FIELDS,
            "sensitive_fields": SENSITIVE_FIELDS,
            "masked_value": MASKED_VALUE,
            "creatable_fleets": self._creatable_fleets(ctx),
            "actions": list(ACTION_RULES),
        }

    def list_entries(
        self,
        ctx: OperatorContext,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("调度单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._present(ctx, row) for row in rows[start:start + size]], total

    def get_entry(self, ctx: OperatorContext, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None
        return self._present(ctx, row)

    def create_entry(
        self, ctx: OperatorContext, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        fleet = str(values.get("所属车队") or "").strip()
        if fleet not in self._creatable_fleets(ctx):
            return None, (
                f"所属车队「{fleet}」不在{ctx.role_label}的归属车队范围内，越权提交已驳回"
            )
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS + OPTIONAL_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._present(ctx, entry), None

    def run_action(
        self, ctx: OperatorContext, entry_id: int, action: str
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"调度单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于调度派单可执行范围"
        fleet = str(entry.get("所属车队") or "")
        if not ctx.manages(fleet):
            return None, (
                f"调度单 {entry.get('调度单号', entry_id)} 属于{fleet or '未分配车队'}，"
                f"{ctx.role_label}只能操作本车队的单子，越权提交已驳回"
            )
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return self._present(ctx, entry), f"调度单已{action}"

    def _creatable_fleets(self, ctx: OperatorContext) -> list[str]:
        """可下单的车队：运营管理员任选，其余岗位限归属车队。"""
        if ctx.is_ops_admin:
            return list(FLEETS)
        return [fleet for fleet in ctx.fleets if fleet in FLEETS]

    def _present(self, ctx: OperatorContext, row: dict[str, Any]) -> dict[str, Any]:
        """按操作人权限整形一行数据：越权行敏感字段脱敏，并给出可执行动作。"""
        writable = ctx.manages(str(row.get("所属车队") or ""))
        item = dict(row)
        if not writable:
            for field in SENSITIVE_FIELDS:
                if field in item:
                    item[field] = MASKED_VALUE
        item["writable"] = writable
        item["allowed_actions"] = list(ACTION_RULES) if writable else []
        return item
