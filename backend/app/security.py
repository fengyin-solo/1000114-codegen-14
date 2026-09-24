"""操作人身份与岗位权限：从请求头解析岗位与归属车队，供各模块做越权判定。

前端在请求头里带上 `X-Operator-Role` 与 `X-Operator-Fleets`（逗号分隔）；
缺头或岗位无法识别时按最小权限（调度员、无归属车队）处理，宁可误拒不可误放。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import unquote

from fastapi import Header

ROLE_DISPATCHER = "dispatcher"
ROLE_FLEET_ADMIN = "fleet_admin"
ROLE_OPS_ADMIN = "ops_admin"

ROLE_LABELS = {
    ROLE_DISPATCHER: "调度员",
    ROLE_FLEET_ADMIN: "车队管理员",
    ROLE_OPS_ADMIN: "运营管理员",
}


@dataclass
class OperatorContext:
    """一次请求的操作人身份：岗位 + 归属车队。"""

    role: str = ROLE_DISPATCHER
    fleets: list[str] = field(default_factory=list)

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)

    @property
    def is_ops_admin(self) -> bool:
        return self.role == ROLE_OPS_ADMIN

    def manages(self, fleet: str | None) -> bool:
        """是否管辖某个车队：运营管理员全部管辖，其余岗位只认归属车队。"""
        if self.is_ops_admin:
            return True
        return bool(fleet) and fleet in self.fleets


def operator_context(
    x_operator_role: str | None = Header(default=None),
    x_operator_fleets: str | None = Header(default=None),
) -> OperatorContext:
    """从请求头解析操作人身份，作为 FastAPI 依赖注入到各路由。

    车队名含中文，调用方按 percent-encode 编码后放入请求头，这里逐个解码还原。
    """
    role = (x_operator_role or "").strip() or ROLE_DISPATCHER
    if role not in ROLE_LABELS:
        role = ROLE_DISPATCHER
    fleets = [
        unquote(item.strip())
        for item in (x_operator_fleets or "").split(",")
        if item.strip()
    ]
    return OperatorContext(role=role, fleets=fleets)
