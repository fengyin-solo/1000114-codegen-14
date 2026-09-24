"""调度派单业务规则：状态流转、字段校验、岗位分权与字段可见口径都收在这里。

分权边界（后端是唯一裁决方，前端只做入口收敛）：
- 调度员：只能新建本车队调度单；确认派单/确认发车仅限本车队单子；
- 车队管理员：本车队单子可改（指派车辆/指派司机/计划发车时间）并可流转，
  其他车队单子只读；不能新建；
- 运营管理员：可见全部，可撤销任意一张单子；不参与派单/发车/改单/新建。
越权操作一律 ok=False 驳回并注明原因。
"""
from __future__ import annotations

from typing import Any

from app.auth import (
    ROLE_DISPATCHER,
    ROLE_FLEET_MANAGER,
    ROLE_OPS_ADMIN,
    FLEETS,
    Principal,
)
from app.store import store

MODULE = "dispatch"
FLEET_FIELD = "所属车队"
REQUIRED_FIELDS = ["调度单号", "关联订单", "配送线路"]
# 车队管理员改单时允许触碰的字段，其余字段一律不接受改动。
EDITABLE_FIELDS = ["指派车辆", "指派司机", "计划发车时间"]

# 列顺序：基础列 + 所属车队 + 车队内执行列 + 状态列。
BASE_FIELDS = ["调度单号", "关联订单", "配送线路"]
EXECUTION_FIELDS = ["指派车辆", "指派司机", "计划发车时间"]
STATUS_FIELD = "调度状态"
ALL_FIELDS = BASE_FIELDS + [FLEET_FIELD] + EXECUTION_FIELDS + [STATUS_FIELD]

# 列表头部按 调度单号、状态 过滤
STATUS_ORDER = ["待派单", "已派单", "已发车", "已撤销"]
ACTION_RULES = {"确认派单": "已派单", "确认发车": "已发车", "撤销派单": "已撤销"}
NEGATIVE_ACTIONS = ["撤销派单"]
FLEET_ACTIONS = ["确认派单", "确认发车"]
CANCEL_ACTION = "撤销派单"


class DispatchService:
    # ---------- 视图权限描述：前端可见列、动作入口、可建车队全以此为准 ----------

    def scope(self, principal: Principal) -> dict[str, Any]:
        """返回当前岗位在调度列表页的可见/可改边界。"""
        role_actions: dict[str, list[str]] = {
            ROLE_DISPATCHER: FLEET_ACTIONS,
            ROLE_FLEET_MANAGER: FLEET_ACTIONS,
            ROLE_OPS_ADMIN: [CANCEL_ACTION],
        }
        return {
            "role": principal.role,
            "principal": principal.key,
            "principal_name": principal.name,
            "fleet": principal.fleet,
            "fleets": list(FLEETS),
            # 运营视角不含车队内执行字段；车队岗位的执行字段按行归属再做投影。
            "columns": self._columns_for(principal),
            "actions": role_actions.get(principal.role, []),
            "can_create": principal.is_dispatcher,
            "can_edit": principal.is_fleet_manager,
            "editable_fields": list(EDITABLE_FIELDS) if principal.is_fleet_manager else [],
        }

    def _columns_for(self, principal: Principal) -> list[str]:
        if principal.is_ops_admin:
            return BASE_FIELDS + [FLEET_FIELD] + [STATUS_FIELD]
        return list(ALL_FIELDS)

    # ---------- 读取：筛选 + 字段投影 ----------

    def list_entries(
        self,
        principal: Principal,
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
        page_rows = [self._project(row, principal) for row in rows[start:start + size]]
        return page_rows, total

    def get_entry(self, principal: Principal, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None
        return self._project(row, principal)

    def _project(self, row: dict[str, Any], principal: Principal) -> dict[str, Any]:
        """按岗位与单子归属裁剪字段：保留状态机用的内部键，业务列按权限输出。"""
        projected = {key: row.get(key) for key in ("id", "status", "pending", "abnormal")}
        visible = self._visible_fields(row, principal)
        for field in ALL_FIELDS:
            if field in visible:
                projected[field] = row.get(field)
        # 动作入口按行再裁一遍：只读行不返回任何动作，前端直接据此渲染。
        projected["permitted_actions"] = self._permitted_actions(row, principal)
        projected["editable"] = self._can_edit_row(row, principal)
        return projected

    def _visible_fields(self, row: dict[str, Any], principal: Principal) -> set[str]:
        columns = set(self._columns_for(principal))
        # 车队岗位看别的车队只读：执行细节（车/司机/发车时间）不对齐，直接隐去。
        if principal.is_fleet_role and not principal.owns(row.get(FLEET_FIELD)):
            columns -= set(EXECUTION_FIELDS)
        return columns

    def _permitted_actions(self, row: dict[str, Any], principal: Principal) -> list[str]:
        if principal.is_ops_admin:
            return [CANCEL_ACTION]
        if principal.is_fleet_role and principal.owns(row.get(FLEET_FIELD)):
            if principal.is_dispatcher:
                return list(FLEET_ACTIONS)
            if principal.is_fleet_manager:
                return list(FLEET_ACTIONS)
        return []

    def _can_edit_row(self, row: dict[str, Any], principal: Principal) -> bool:
        return principal.is_fleet_manager and principal.owns(row.get(FLEET_FIELD))

    # ---------- 写入：新建 / 改单 / 动作，全部带岗位裁决 ----------

    def create_entry(
        self, principal: Principal, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[str], str | None]:
        """新建调度单。返回 (记录, 缺失字段, 驳回原因)；驳回原因为 None 才放行。"""
        if not principal.is_dispatcher:
            return None, [], f"当前岗位「{principal.role}」无权新建调度单，仅调度员可登记本车队调度单"
        fleet = str(values.get(FLEET_FIELD) or "").strip()
        if not fleet:
            return None, [], f"缺少必填字段：{FLEET_FIELD}"
        if fleet not in FLEETS:
            return None, [], f"车队「{fleet}」不在可选车队范围内"
        if fleet != principal.fleet:
            return None, [], (
                f"越权驳回：您归属「{principal.fleet}」，不能为「{fleet}」新建调度单，"
                "调度员只能登记自己归属车队的单子"
            )
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, None
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 车队以岗位归属为准，忽略提交内容里的其他执行字段，避免夹带越权数据。
        entry[FLEET_FIELD] = principal.fleet
        for field in EXECUTION_FIELDS:
            entry[field] = values.get(field)
        entry[STATUS_FIELD] = STATUS_ORDER[0]
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._project(entry, principal), [], None

    def update_entry(
        self, principal: Principal, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """改单：仅本车队管理员，且只接受白名单字段。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"调度单 {entry_id} 不存在或已归档"
        if not principal.is_fleet_manager:
            return None, f"越权驳回：当前岗位「{principal.role}」无权修改调度单，仅车队管理员可改"
        if not principal.owns(entry.get(FLEET_FIELD)):
            return None, (
                f"越权驳回：该调度单归属「{entry.get(FLEET_FIELD) or '未分配车队'}」，"
                f"您是「{principal.fleet}」车队管理员，对其他车队的单子只读"
            )
        changes = {
            field: values[field]
            for field in EDITABLE_FIELDS
            if field in values and str(values.get(field) or "").strip()
        }
        if not changes:
            return None, f"没有可更新的字段；车队管理员仅能修改：{'、'.join(EDITABLE_FIELDS)}"
        entry.update(changes)
        return self._project(entry, principal), f"调度单已更新 {len(changes)} 个字段"

    def run_action(
        self, principal: Principal, entry_id: int, action: str
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"调度单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于调度派单可执行范围"
        if not self._action_allowed(principal, entry, action):
            return None, self._deny_reason(principal, entry, action)
        target = ACTION_RULES[action]
        entry["status"] = target
        # 业务列「调度状态」与内部状态机保持同步，列表展示才不会出现空值/旧值。
        entry[STATUS_FIELD] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return self._project(entry, principal), f"调度单已{action}"

    def _action_allowed(self, principal: Principal, entry: dict[str, Any], action: str) -> bool:
        if action == CANCEL_ACTION:
            return principal.is_ops_admin
        if action in FLEET_ACTIONS:
            return principal.is_fleet_role and principal.owns(entry.get(FLEET_FIELD))
        return False

    def _deny_reason(self, principal: Principal, entry: dict[str, Any], action: str) -> str:
        row_fleet = entry.get(FLEET_FIELD) or "未分配车队"
        if action == CANCEL_ACTION:
            return (
                f"越权驳回：仅运营管理员可撤销调度单，当前岗位「{principal.role}」无权撤销"
                f"（该单归属{row_fleet}）"
            )
        if not principal.is_fleet_role:
            return (
                f"越权驳回：{action}仅限车队岗位操作，运营管理员对该单只保留撤销权限"
            )
        if not principal.owns(entry.get(FLEET_FIELD)):
            return (
                f"越权驳回：该调度单归属「{row_fleet}」，您归属「{principal.fleet}」，"
                f"对其他车队的单子只读，不能{action}"
            )
        return f"当前岗位「{principal.role}」无权执行「{action}」"
