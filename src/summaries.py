"""Aggregate daily data into human-readable summaries + AI-powered summaries."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from db import Database
from llm_client import LLMError, chat_completion


def _format_day(iso: str, note: str, tasks: list) -> str:
    lines = [f"【{iso}】"]
    if tasks:
        for t in tasks:
            mark = "✓" if t.done else "○"
            lines.append(f"  {mark} {t.title}")
    else:
        lines.append("  （无计划任务）")
    if note.strip():
        lines.append(f"  学习记录：{note.strip()}")
    else:
        lines.append("  学习记录：（未填写）")
    return "\n".join(lines)


def build_week_summary(db: Database, end: date | None = None) -> tuple[str, str]:
    """Rolling 7 days ending at `end` (inclusive). Returns (period_key, text)."""
    end = end or date.today()
    start = end - timedelta(days=6)
    period_key = f"{start.isoformat()}_{end.isoformat()}"
    rows = db.iter_days_range(start, end)
    parts = [f"周总结（{start.isoformat()} ～ {end.isoformat()}）", ""]
    for iso, note, tasks in rows:
        parts.append(_format_day(iso, note, tasks))
        parts.append("")
    return period_key, "\n".join(parts).strip()


def build_half_month_summary(db: Database, end: date | None = None) -> tuple[str, str]:
    """Rolling 15 days ending at `end` (inclusive)."""
    end = end or date.today()
    start = end - timedelta(days=14)
    period_key = f"{start.isoformat()}_{end.isoformat()}"
    rows = db.iter_days_range(start, end)
    parts = [f"半月总结（{start.isoformat()} ～ {end.isoformat()}）", ""]
    for iso, note, tasks in rows:
        parts.append(_format_day(iso, note, tasks))
        parts.append("")
    return period_key, "\n".join(parts).strip()


def build_month_summary(db: Database, ref: date | None = None) -> tuple[str, str]:
    """Calendar month from 1st to today (backwards-looking)."""
    ref = ref or date.today()
    start = date(ref.year, ref.month, 1)
    end = ref  # stop at today, not end of month
    period_key = f"{ref.year:04d}-{ref.month:02d}"
    rows = db.iter_days_range(start, end)
    parts = [f"月总结（{start.isoformat()} ～ {end.isoformat()}）", ""]
    for iso, note, tasks in rows:
        parts.append(_format_day(iso, note, tasks))
        parts.append("")
    return period_key, "\n".join(parts).strip()


def _build_ai_summary(
    raw_data: str,
    system_prompt: str,
    label: str,
    base_url: str,
    api_key: str,
    model: str,
) -> tuple[str, str]:
    """Build AI summary from raw data using given system prompt."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": raw_data},
    ]
    ai_text = chat_completion(base_url, api_key, model, messages)
    return label, ai_text


def build_ai_week_summary(
    db: Database,
    base_url: str,
    api_key: str,
    model: str,
    end: date | None = None,
) -> tuple[str, str]:
    """AI-powered weekly summary."""
    period_key, raw_text = build_week_summary(db, end)
    system_prompt = (
        "你是一名专业的学习复盘助手。根据用户提供的「近 7 日每日计划（含完成情况）」与「睡前记录」，生成一份简洁有力的周总结，包含：\n"
        "① 本周整体完成情况概览\n"
        "② 做得好的地方（亮点）\n"
        "③ 需要改进的地方（不足）\n"
        "④ 下周建议方向\n\n"
        "控制在 600 字以内，用中文，分点清晰，语气鼓励但客观。"
    )
    return _build_ai_summary(raw_text, system_prompt, "week", base_url, api_key, model)


def build_ai_half_month_summary(
    db: Database,
    base_url: str,
    api_key: str,
    model: str,
    end: date | None = None,
) -> tuple[str, str]:
    """AI-powered half-month summary."""
    period_key, raw_text = build_half_month_summary(db, end)
    system_prompt = (
        "你是一名专业的学习复盘助手。根据用户提供的「近 15 日每日计划（含完成情况）」与「睡前记录」，生成一份简洁有力的半月总结，包含：\n"
        "① 整体进度概览\n"
        "② 主要收获与成果\n"
        "③ 存在的问题与不足\n"
        "④ 下一阶段建议方向\n\n"
        "控制在 800 字以内，用中文，分点清晰，语气鼓励但客观。"
    )
    return _build_ai_summary(raw_text, system_prompt, "half_month", base_url, api_key, model)


def build_ai_month_summary(
    db: Database,
    base_url: str,
    api_key: str,
    model: str,
    ref: date | None = None,
) -> tuple[str, str]:
    """AI-powered monthly summary."""
    period_key, raw_text = build_month_summary(db, ref)
    system_prompt = (
        "你是一名专业的学习复盘助手。根据用户提供的「本月每日计划（含完成情况）」与「睡前记录」，生成一份简洁有力的月总结，包含：\n"
        "① 本月整体完成情况概览\n"
        "② 主要里程碑/成果\n"
        "③ 待改进之处\n"
        "④ 下月规划建议方向\n\n"
        "控制在 1000 字以内，用中文，分点清晰，语气鼓励但客观。"
    )
    return _build_ai_summary(raw_text, system_prompt, "month", base_url, api_key, model)
