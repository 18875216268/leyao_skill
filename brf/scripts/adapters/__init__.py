"""适配器注册表：按资产声明分派到对应适配器。

扩展点：新领域特殊源 → 实现 base.Adapter 子类并加入 ADAPTERS。
当前闭环适配器：pool（公共池三库）· cli（云智库桥接）· template（本地模板）。
"""
from __future__ import annotations

from .base import Adapter
from .cli_adapter import CliAdapter
from .pool_adapter import PoolAdapter
from .template_adapter import TemplateAdapter

ADAPTERS: list[Adapter] = [CliAdapter(), TemplateAdapter(), PoolAdapter()]


def get_adapter(asset):
    """按资产 adapter 声明（优先）或模式推断返回适配器；无匹配返回 None。"""
    want = asset.get("adapter")
    if want:
        for a in ADAPTERS:
            if a.id == want:
                return a
    for a in ADAPTERS:
        if a.match(asset):
            return a
    return None
