from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class RiskDecision:
    level: str
    reason: str


HIGH_RISK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(edit|modify|change|update|rewrite|refactor|implement|fix)\b", re.I), "requests code or file edits"),
    (re.compile(r"\b(create|delete|remove|rename|move)\b", re.I), "requests filesystem mutation"),
    (re.compile(r"\b(commit|push|checkout|rebase|merge|cherry-pick)\b", re.I), "requests git mutation"),
    (re.compile(r"\b(pip|npm|pnpm|yarn|brew|apt|cargo)\s+(install|add|remove|update)\b", re.I), "requests dependency changes"),
    (re.compile(r"\b(curl|wget)\b", re.I), "requests network access"),
    (re.compile(r"\b(run|execute)\b.+\b(shell|command|script)\b", re.I), "requests arbitrary command execution"),
    (re.compile(r"(修改|改动|实现|修复|重构|更新|编辑|写入|新增代码)"), "requests code or file edits"),
    (re.compile(r"(创建|删除|移除|重命名|移动文件|改文件)"), "requests filesystem mutation"),
    (re.compile(r"(提交|推送|切换分支|变基|合并|拣选)"), "requests git mutation"),
    (re.compile(r"(安装依赖|安装包|升级依赖|删除依赖)"), "requests dependency changes"),
    (re.compile(r"(下载|联网|请求网络|抓取网页)"), "requests network access"),
    (re.compile(r"(执行命令|运行脚本|跑命令|终端执行)"), "requests arbitrary command execution"),
)


def classify_risk(message: str) -> RiskDecision:
    normalized = message.strip()
    if not normalized:
        return RiskDecision(level="readonly", reason="empty message")

    for pattern, reason in HIGH_RISK_PATTERNS:
        if pattern.search(normalized):
            return RiskDecision(level="high_risk", reason=reason)

    return RiskDecision(level="readonly", reason="no mutation indicators detected")
