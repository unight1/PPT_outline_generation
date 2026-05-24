from __future__ import annotations

import re
from typing import Any


def infer_target_pages(clarification: dict[str, Any] | None, raw_notes: str | None = None) -> int:
    """Infer a practical slide count from user clarification answers."""

    hints: list[str] = []
    if isinstance(raw_notes, str) and raw_notes.strip():
        hints.append(raw_notes)
    if isinstance(clarification, dict):
        questions = clarification.get("questions", [])
        if isinstance(questions, list):
            for item in questions:
                if not isinstance(item, dict):
                    continue
                prompt = str(item.get("prompt") or "")
                answer = str(item.get("answer") or "")
                if "页" in prompt or "page" in prompt.lower() or "页" in answer or "page" in answer.lower():
                    hints.append(answer)

    for text in hints:
        if not text:
            continue
        range_match = re.search(r"(\d{1,2})\s*[-~—]\s*(\d{1,2})", text)
        if range_match:
            low = int(range_match.group(1))
            high = int(range_match.group(2))
            return max(5, min(20, (low + high) // 2))
        single_match = re.search(r"(\d{1,2})\s*(?:页|pages?)", text, flags=re.IGNORECASE)
        if single_match:
            return max(5, min(20, int(single_match.group(1))))
    return 8


def clarification_summary(clarification: dict[str, Any] | None) -> str:
    if not isinstance(clarification, dict):
        return ""
    lines: list[str] = []
    questions = clarification.get("questions", [])
    if not isinstance(questions, list):
        return ""
    for item in questions:
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if prompt and answer:
            lines.append(f"{prompt}：{answer}")
    return "\n".join(lines)


def generate_outline_skeleton(task: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate a page-level skeleton without RAG, ready for user editing."""

    input_payload = task.get("input", {}) if isinstance(task.get("input"), dict) else {}
    topic = str(input_payload.get("topic") or "演示主题").strip() or "演示主题"
    raw_notes = input_payload.get("raw_notes")
    clarification = task.get("clarification") if isinstance(task.get("clarification"), dict) else None
    pages = infer_target_pages(clarification=clarification, raw_notes=raw_notes if isinstance(raw_notes, str) else None)

    base = [
        ("问题背景与目标", "说明为什么要关注该主题，以及本次演示希望达成的目标"),
        ("现状分析与核心挑战", "梳理当前状态、主要矛盾和需要解决的问题"),
        ("方案思路与总体框架", "给出解决路径、关键模块和逻辑关系"),
        ("关键能力与实现路径", "展开说明支撑方案成立的核心能力或方法"),
        ("案例场景与应用价值", "结合典型场景说明方案如何产生实际价值"),
        ("实施计划与里程碑", "说明落地步骤、阶段成果和协作节奏"),
        ("风险边界与应对策略", "提前说明不确定性、限制条件和应对办法"),
        ("总结结论与下一步行动", "收束核心结论，并给出后续行动建议"),
    ]

    slides: list[dict[str, Any]] = []
    for idx in range(pages):
        if idx < len(base):
            title, intent = base[idx]
        else:
            title = f"补充专题 {idx + 1}"
            intent = "补充说明前面结构中尚未覆盖但对听众理解有帮助的内容"
        slides.append(
            {
                "slide_id": f"s{idx + 1}",
                "title": f"{title}：{topic}" if idx == 0 else title,
                "intent": intent,
                "user_notes": None,
            }
        )
    return slides
