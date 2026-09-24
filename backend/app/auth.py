"""岗位身份与请求级身份解析。

调度派单按岗位分权：
- 调度员：归属某个车队，只能为本车队新建调度单、操作本车队的单子；
- 车队管理员：归属某个车队，本车队的单子可改可流转，其他车队只读；
- 运营管理员：不归属车队，可查看全部单子并撤销任意一张。

真实项目里这里会换成登录态/JWT 解析；当前演示版本通过请求头 X-Principal
（导出等无法带头的场景用 query 参数 principal）传入岗位身份键。
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException, Query

ROLE_DISPATCHER = "调度员"
ROLE_FLEET_MANAGER = "车队管理员"
ROLE_OPS_ADMIN = "运营管理员"

ROLE_LABELS = (ROLE_DISPATCHER, ROLE_FLEET_MANAGER, ROLE_OPS_ADMIN)

# 演示用车队清单：调度单、岗位都挂在这三支车队上。
FLEETS = ("一车队", "二车队", "三车队")


@dataclass(frozen=True)
class Principal:
    """一次请求的岗位身份。fleet 仅车队类岗位有值。"""

    key: str
    name: str
    role: str
    fleet: str | None

    @property
    def is_ops_admin(self) -> bool:
        return self.role == ROLE_OPS_ADMIN

    @property
    def is_dispatcher(self) -> bool:
        return self.role == ROLE_DISPATCHER

    @property
    def is_fleet_manager(self) -> bool:
        return self.role == ROLE_FLEET_MANAGER

    @property
    def is_fleet_role(self) -> bool:
        """归属具体车队的岗位：调度员、车队管理员。"""
        return self.fleet is not None

    def owns(self, row_fleet: str | None) -> bool:
        return self.fleet is not None and row_fleet == self.fleet


PRINCIPALS: dict[str, Principal] = {
    "dispatcher_a": Principal("dispatcher_a", "张调度", ROLE_DISPATCHER, "一车队"),
    "manager_a": Principal("manager_a", "李队长", ROLE_FLEET_MANAGER, "一车队"),
    "dispatcher_b": Principal("dispatcher_b", "王调度", ROLE_DISPATCHER, "二车队"),
    "ops_admin": Principal("ops_admin", "周运营", ROLE_OPS_ADMIN, None),
}

DEFAULT_PRINCIPAL_KEY = "dispatcher_a"


def get_principal(
    x_principal: str | None = Header(default=None, alias="X-Principal"),
    principal: str | None = Query(default=None, description="岗位身份键（无法带头的场景使用）"),
) -> Principal:
    """解析当前请求的岗位身份；身份键无法识别时直接驳回，不做静默降级。"""
    key = (x_principal or principal or "").strip()
    if not key:
        # 未带身份时回落到默认演示岗位，保证页面直接打开也可用；
        # 显式传了无法识别的身份键则视为无效凭据。
        return PRINCIPALS[DEFAULT_PRINCIPAL_KEY]
    found = PRINCIPALS.get(key)
    if found is None:
        raise HTTPException(status_code=401, detail=f"未识别的岗位身份：{key}，请重新选择岗位后再试")
    return found
