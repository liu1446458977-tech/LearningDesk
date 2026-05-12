"""Aggregate daily data into human-readable summaries."""

from __future__ import annotations

from datetime import date, timedelta

from db import Database


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
    """Calendar month containing `ref`."""
    ref = ref or date.today()
    start = date(ref.year, ref.month, 1)
    if ref.month == 12:
        next_m = date(ref.year + 1, 1, 1)
    else:
        next_m = date(ref.year, ref.month + 1, 1)
    end = next_m - timedelta(days=1)
    period_key = f"{ref.year:04d}-{ref.month:02d}"
    rows = db.iter_days_range(start, end)
    parts = [f"月总结（{period_key}）", ""]
    for iso, note, tasks in rows:
        parts.append(_format_day(iso, note, tasks))
        parts.append("")
    return period_key, "\n".join(parts).strip()
