"""适配器抽象基类：通用 ACS 的源接入契约。

任何领域（乐药/其它）的资产接入 = 一个适配器实例。
新 skill 接入优先复用内置适配器（pool/cli/template），
特殊源按本基类实现 match/query 后注册进 adapters/__init__.py 即可。
"""
from __future__ import annotations


class Adapter:
    """源适配器基类：match 判定是否处理该资产，query 执行查询返回统一响应。"""

    id = "base"

    def match(self, asset) -> bool:
        """该适配器是否能处理此资产（按 adapter 声明或模式推断）。"""
        raise NotImplementedError

    def query(self, asset, need_type, question, **kwargs) -> dict:
        """执行查询，返回统一响应：{ok, need_type, answer, source, category, trust,
        confidence, version, ...}；失败返回 {ok: False, reason, ...}。"""
        raise NotImplementedError
