"""意图识别：从问句自动推断 need_type（AI 无需手动指定类型）。

规则优先级（从具体到默认）：
  口径/计算 → caliber ｜ 分析方法 → process ｜ 模板 → template
  查/搜/制度/课程 → tool ｜ 公司 → term（走公司表）｜ 数据/数值 → data
  是什么/定义/含义 → term ｜ 默认 → term
"""
from __future__ import annotations

RULES = [
    ("caliber", ["怎么算", "如何计算", "怎么计算", "计算公式", "口径", "计算方式", "公式是"]),
    ("template", ["模板", "格式", "怎么写周报", "怎么写日报", "怎么写复盘", "怎么做周报", "怎么做日报", "怎么做复盘", "报表格式"]),
    ("process", ["怎么做", "怎么分析", "分析方法", "方法论", "分析框架", "怎么复盘", "复盘方法", "如何复盘", "分析方法论"]),
    ("tool", ["查一下", "搜索", "搜一下", "找一下", "怎么查", "如何查", "查查", "制度", "课程", "文档", "资料", "文件"]),
    ("term", ["是什么", "定义", "含义", "什么意思", "解释一下", "啥意思", "公司", "子公司"]),
    ("data", ["数据", "多少", "数值", "统计", "指标值", "金额", "数量"]),
]
DEFAULT = "term"


def infer_need_type(question) -> str:
    q = (question or "").strip()
    if not q:
        return DEFAULT
    for need, keys in RULES:
        if any(k in q for k in keys):
            return need
    return DEFAULT
