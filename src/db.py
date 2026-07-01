"""SQLite persistence for tasks, daily notes, and cached summaries."""

from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path


def app_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return base / "LearningDesk"
    return Path(__file__).resolve().parent / "data"


def db_path() -> Path:
    d = app_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "learning_desk.db"


def today_str() -> str:
    return date.today().isoformat()


@dataclass
class TaskRow:
    id: int
    task_date: str
    title: str
    done: bool


@dataclass
class PlanRow:
    id: int
    name: str
    start_date: str
    end_date: str


@dataclass
class PlanItemRow:
    id: int
    plan_id: int
    plan_date: str
    subject: str
    time_slot: str
    content: str
    done: bool


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or db_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_date TEXT NOT NULL,
                title TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_date ON tasks(task_date);

            CREATE TABLE IF NOT EXISTS daily_notes (
                note_date TEXT PRIMARY KEY,
                content TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS summary_cache (
                kind TEXT NOT NULL,
                period_key TEXT NOT NULL,
                body TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                PRIMARY KEY (kind, period_key)
            );

            CREATE TABLE IF NOT EXISTS period_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS period_plan_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL REFERENCES period_plans(id) ON DELETE CASCADE,
                plan_date TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT '',
                time_slot TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_plan_items_plan ON period_plan_items(plan_id);
            CREATE INDEX IF NOT EXISTS idx_plan_items_date ON period_plan_items(plan_date);
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- tasks ---
    def list_tasks(self, task_date: str) -> list[TaskRow]:
        cur = self._conn.execute(
            "SELECT id, task_date, title, done FROM tasks WHERE task_date = ? ORDER BY id",
            (task_date,),
        )
        return [
            TaskRow(r["id"], r["task_date"], r["title"], bool(r["done"]))
            for r in cur.fetchall()
        ]

    def add_task(self, task_date: str, title: str) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        cur = self._conn.execute(
            "INSERT INTO tasks (task_date, title, done, created_at) VALUES (?,?,0,?)",
            (task_date, title.strip(), now),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def update_task_title(self, task_id: int, title: str) -> None:
        self._conn.execute(
            "UPDATE tasks SET title = ? WHERE id = ?", (title.strip(), task_id)
        )
        self._conn.commit()

    def set_task_done(self, task_id: int, done: bool) -> None:
        self._conn.execute(
            "UPDATE tasks SET done = ? WHERE id = ?", (1 if done else 0, task_id)
        )
        self._conn.commit()

    def delete_task(self, task_id: int) -> None:
        self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()

    # --- daily notes ---
    def get_note(self, note_date: str) -> str:
        row = self._conn.execute(
            "SELECT content FROM daily_notes WHERE note_date = ?", (note_date,)
        ).fetchone()
        return row["content"] if row else ""

    def upsert_note(self, note_date: str, content: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            """
            INSERT INTO daily_notes (note_date, content, updated_at)
            VALUES (?,?,?)
            ON CONFLICT(note_date) DO UPDATE SET content = excluded.content,
                updated_at = excluded.updated_at
            """,
            (note_date, content, now),
        )
        self._conn.commit()

    def iter_days_range(self, start: date, end: date) -> list[tuple[str, str, list[TaskRow]]]:
        """For each day in [start, end]: (iso_date, note, tasks)."""
        out: list[tuple[str, str, list[TaskRow]]] = []
        d = start
        while d <= end:
            s = d.isoformat()
            note = self.get_note(s)
            tasks = self.list_tasks(s)
            out.append((s, note, tasks))
            d += timedelta(days=1)
        return out

    def list_dates_with_activity(self) -> list[str]:
        """All dates that have at least one task or non-empty note, newest first."""
        cur = self._conn.execute(
            """
            SELECT d FROM (
                SELECT task_date AS d FROM tasks
                UNION
                SELECT note_date AS d FROM daily_notes WHERE TRIM(content) != ''
            )
            ORDER BY d DESC
            """
        )
        return [str(r["d"]) for r in cur.fetchall()]

    # --- summary cache ---
    def delete_summary(self, kind: str, period_key: str) -> None:
        self._conn.execute(
            "DELETE FROM summary_cache WHERE kind = ? AND period_key = ?", (kind, period_key)
        )
        self._conn.commit()

    def list_all_summaries(self) -> list[dict]:
        cur = self._conn.execute(
            "SELECT kind, period_key, body, generated_at FROM summary_cache ORDER BY generated_at DESC"
        )
        return [dict(r) for r in cur.fetchall()]

    def get_cached_summary(self, kind: str, period_key: str) -> str | None:
        row = self._conn.execute(
            "SELECT body FROM summary_cache WHERE kind = ? AND period_key = ?",
            (kind, period_key),
        ).fetchone()
        return row["body"] if row else None

    def save_summary_cache(self, kind: str, period_key: str, body: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            """
            INSERT INTO summary_cache (kind, period_key, body, generated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(kind, period_key) DO UPDATE SET body = excluded.body,
                generated_at = excluded.generated_at
            """,
            (kind, period_key, body, now),
        )
        self._conn.commit()

    # --- period plans ---
    def list_plans(self) -> list[PlanRow]:
        cur = self._conn.execute(
            "SELECT id, name, start_date, end_date FROM period_plans ORDER BY id DESC"
        )
        return [PlanRow(r["id"], r["name"], r["start_date"], r["end_date"]) for r in cur.fetchall()]

    def add_plan(self, name: str, start_date: str, end_date: str) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        cur = self._conn.execute(
            "INSERT INTO period_plans (name, start_date, end_date, created_at) VALUES (?,?,?,?)",
            (name.strip(), start_date, end_date, now),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def delete_plan(self, plan_id: int) -> None:
        self._conn.execute("DELETE FROM period_plan_items WHERE plan_id = ?", (plan_id,))
        self._conn.execute("DELETE FROM period_plans WHERE id = ?", (plan_id,))
        self._conn.commit()

    def list_plan_items(self, plan_id: int) -> list[PlanItemRow]:
        cur = self._conn.execute(
            "SELECT id, plan_id, plan_date, subject, time_slot, content, done "
            "FROM period_plan_items WHERE plan_id = ? ORDER BY plan_date, time_slot, id",
            (plan_id,),
        )
        return [PlanItemRow(r["id"], r["plan_id"], r["plan_date"], r["subject"],
                            r["time_slot"], r["content"], bool(r["done"])) for r in cur.fetchall()]

    def add_plan_item(self, plan_id: int, plan_date: str, subject: str,
                      time_slot: str, content: str) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        cur = self._conn.execute(
            "INSERT INTO period_plan_items (plan_id, plan_date, subject, time_slot, content, done, created_at) "
            "VALUES (?,?,?,?,?,0,?)",
            (plan_id, plan_date, subject.strip(), time_slot.strip(), content.strip(), now),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def set_plan_item_done(self, item_id: int, done: bool) -> None:
        self._conn.execute(
            "UPDATE period_plan_items SET done = ? WHERE id = ?", (1 if done else 0, item_id)
        )
        self._conn.commit()

    def delete_plan_item(self, item_id: int) -> None:
        self._conn.execute("DELETE FROM period_plan_items WHERE id = ?", (item_id,))
        self._conn.commit()
