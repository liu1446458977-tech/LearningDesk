"""LearningDesk — desktop learning planner (CustomTkinter)."""

from __future__ import annotations

import threading
import tkinter.simpledialog as simpledialog
from datetime import date, timedelta
from tkinter import messagebox

import customtkinter as ctk

from config_store import DEFAULT_MODEL, load_settings, save_settings
from db import Database, app_data_dir, today_str
from llm_client import LLMError, build_suggestion_prompt, chat_completion
from summaries import build_half_month_summary, build_month_summary, build_week_summary

APP_VERSION = "1.1.0"


class LearningDeskApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"LearningDesk · 学习计划 · v{APP_VERSION}")
        self.minsize(600, 560)

        self.settings = load_settings()
        self.db = Database()

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        geo = self.settings.get("window_geometry", "520x720+80+80")
        try:
            self.geometry(geo)
        except Exception:
            self.geometry("520x720+80+80")
        self.attributes("-topmost", bool(self.settings.get("always_on_top", True)))

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_plan_tab()

    def _build_ui(self) -> None:
        self.tab = ctk.CTkTabview(self)
        self.tab.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab.add("今日计划")
        self.tab.add("睡前记录")
        self.tab.add("周期总结")
        self.tab.add("学习建议")
        self.tab.add("历史回顾")
        self.tab.add("设置")

        self._build_plan_tab()
        self._build_note_tab()
        self._build_summary_tab()
        self._build_advice_tab()
        self._build_history_tab()
        self._build_settings_tab()

    # --- 今日计划 ---
    def _build_plan_tab(self) -> None:
        frame = self.tab.tab("今日计划")
        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(top, text="日期").pack(side="left", padx=(0, 6))
        self.plan_date = ctk.CTkEntry(top, width=120, placeholder_text="YYYY-MM-DD")
        self.plan_date.insert(0, today_str())
        self.plan_date.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            top, text="昨天", width=56, command=lambda: self._shift_plan_date(-1)
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            top, text="今天", width=56, command=lambda: self._set_plan_date(today_str())
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            top, text="明天", width=56, command=lambda: self._shift_plan_date(1)
        ).pack(side="left", padx=2)

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        self.task_entry = ctk.CTkEntry(row, placeholder_text="新任务，回车或点击添加")
        self.task_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.task_entry.bind("<Return>", lambda e: self._add_task())
        ctk.CTkButton(row, text="添加", width=72, command=self._add_task).pack(
            side="right"
        )

        self.plan_date.bind("<FocusOut>", lambda e: self._refresh_plan_tab())
        self.plan_date.bind("<Return>", lambda e: self._refresh_plan_tab())

        self.task_scroll = ctk.CTkScrollableFrame(frame, label_text="任务列表")
        self.task_scroll.pack(fill="both", expand=True)

        bot = ctk.CTkFrame(frame, fg_color="transparent")
        bot.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(bot, text="点「选」指定任务，再编辑或删除").pack(side="left")
        ctk.CTkButton(bot, text="编辑标题", width=88, command=self._edit_selected_task).pack(
            side="right", padx=(4, 0)
        )
        ctk.CTkButton(bot, text="删除", width=72, fg_color="#c0392b", command=self._delete_selected_task).pack(
            side="right"
        )

        self._selected_task_id: int | None = None

    def _plan_date_value(self) -> str:
        return self.plan_date.get().strip() or today_str()

    def _select_task(self, tid: int) -> None:
        self._selected_task_id = tid

    def _set_plan_date(self, iso: str) -> None:
        self.plan_date.delete(0, "end")
        self.plan_date.insert(0, iso)
        self._refresh_plan_tab()

    def _shift_plan_delta(self, days: int) -> None:
        try:
            d = date.fromisoformat(self._plan_date_value())
        except ValueError:
            d = date.today()
        self._set_plan_date((d + timedelta(days=days)).isoformat())

    def _shift_plan_date(self, days: int) -> None:
        self._shift_plan_delta(days)

    def _refresh_plan_tab(self) -> None:
        for w in self.task_scroll.winfo_children():
            w.destroy()
        self._selected_task_id = None
        d = self._plan_date_value()
        for t in self.db.list_tasks(d):
            row = ctk.CTkFrame(self.task_scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)

            var = ctk.BooleanVar(value=t.done)

            pick = ctk.CTkButton(
                row,
                text="选",
                width=36,
                command=lambda tid=t.id: self._select_task(tid),
            )
            pick.pack(side="left", padx=(0, 6))

            cb = ctk.CTkCheckBox(
                row,
                text=t.title,
                variable=var,
                command=lambda tid=t.id, v=var: self.db.set_task_done(tid, v.get()),
            )
            cb.pack(side="left", fill="x", expand=True)

    def _add_task(self) -> None:
        title = self.task_entry.get().strip()
        if not title:
            return
        self.db.add_task(self._plan_date_value(), title)
        self.task_entry.delete(0, "end")
        self._refresh_plan_tab()

    def _edit_selected_task(self) -> None:
        tid = self._selected_task_id
        if tid is None:
            return
        tasks = self.db.list_tasks(self._plan_date_value())
        cur = next((x.title for x in tasks if x.id == tid), None)
        if cur is None:
            return
        new = simpledialog.askstring("编辑任务", "任务标题：", initialvalue=cur, parent=self)
        if new and new.strip():
            self.db.update_task_title(tid, new)
            self._refresh_plan_tab()

    def _delete_selected_task(self) -> None:
        tid = self._selected_task_id
        if tid is None:
            return
        self.db.delete_task(tid)
        self._selected_task_id = None
        self._refresh_plan_tab()

    # --- 睡前记录 ---
    def _build_note_tab(self) -> None:
        frame = self.tab.tab("睡前记录")
        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(top, text="记录日期").pack(side="left", padx=(0, 6))
        self.note_date = ctk.CTkEntry(top, width=120)
        self.note_date.insert(0, today_str())
        self.note_date.pack(side="left", padx=(0, 8))
        ctk.CTkButton(top, text="载入", width=64, command=self._load_note).pack(
            side="left"
        )

        self.note_box = ctk.CTkTextbox(frame, wrap="word", font=("", 14))
        self.note_box.pack(fill="both", expand=True, pady=(0, 8))
        self._load_note()

        ctk.CTkButton(frame, text="保存今日学习记录", command=self._save_note).pack(
            fill="x"
        )

    def _load_note(self) -> None:
        d = self.note_date.get().strip() or today_str()
        self.note_box.delete("1.0", "end")
        self.note_box.insert("1.0", self.db.get_note(d))

    def _save_note(self) -> None:
        d = self.note_date.get().strip() or today_str()
        self.db.upsert_note(d, self.note_box.get("1.0", "end").strip())
        messagebox.showinfo("LearningDesk", "已保存学习记录", parent=self)

    # --- 周期总结 ---
    def _build_summary_tab(self) -> None:
        frame = self.tab.tab("周期总结")
        bar = ctk.CTkFrame(frame, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(bar, text="生成本周总结", command=lambda: self._gen_summary("week")).pack(
            side="left", padx=(0, 6)
        )
        ctk.CTkButton(bar, text="生成半月总结", command=lambda: self._gen_summary("half")).pack(
            side="left", padx=(0, 6)
        )
        ctk.CTkButton(bar, text="生成本月总结", command=lambda: self._gen_summary("month")).pack(
            side="left"
        )

        self.summary_box = ctk.CTkTextbox(frame, wrap="word", font=("", 13))
        self.summary_box.pack(fill="both", expand=True, pady=(0, 8))
        self.summary_kind_var = ctk.StringVar(value="")

        cache_row = ctk.CTkFrame(frame, fg_color="transparent")
        cache_row.pack(fill="x")
        ctk.CTkButton(cache_row, text="读取上次生成的总结", command=self._load_cached_summary).pack(
            side="left"
        )

    def _gen_summary(self, kind: str) -> None:
        if kind == "week":
            key, body = build_week_summary(self.db)
            label = "week"
        elif kind == "half":
            key, body = build_half_month_summary(self.db)
            label = "half_month"
        else:
            key, body = build_month_summary(self.db)
            label = "month"
        self.db.save_summary_cache(label, key, body)
        self.summary_kind_var.set(f"{label}|{key}")
        self.summary_box.delete("1.0", "end")
        self.summary_box.insert("1.0", body)

    def _load_cached_summary(self) -> None:
        raw = self.summary_kind_var.get()
        if "|" not in raw:
            messagebox.showinfo("LearningDesk", "请先在上方生成一种总结。", parent=self)
            return
        label, key = raw.split("|", 1)
        cached = self.db.get_cached_summary(label, key)
        if not cached:
            messagebox.showinfo("LearningDesk", "没有可读取的缓存。", parent=self)
            return
        self.summary_box.delete("1.0", "end")
        self.summary_box.insert("1.0", cached)

    # --- 学习建议 ---
    def _build_advice_tab(self) -> None:
        frame = self.tab.tab("学习建议")
        ctk.CTkLabel(
            frame,
            text="结合「周总结」与「近 7 日每日计划 + 睡前记录」调用大模型生成建议（需先在「设置」填写 API）。",
            wraplength=460,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        self.advice_status = ctk.CTkLabel(frame, text="")
        self.advice_status.pack(anchor="w")

        ctk.CTkButton(frame, text="生成学习建议", command=self._run_advice).pack(
            fill="x", pady=(0, 8)
        )
        self.advice_box = ctk.CTkTextbox(frame, wrap="word", font=("", 14))
        self.advice_box.pack(fill="both", expand=True)

    def _run_advice(self) -> None:
        base = self.settings.get("api_base_url", "").strip()
        key = self.settings.get("api_key", "").strip()
        model = self.settings.get("model", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        if not base:
            self.advice_status.configure(text="请先在「设置」填写 Base URL")
            return

        _, weekly = build_week_summary(self.db)
        end = date.today()
        start = end - timedelta(days=6)
        day_blocks: list[str] = []
        for iso, note, tasks in self.db.iter_days_range(start, end):
            lines = [f"【{iso}】"]
            if tasks:
                for t in tasks:
                    mark = "已完成" if t.done else "未完成"
                    lines.append(f"  · 计划 [{mark}] {t.title}")
            else:
                lines.append("  · 计划：（当日无任务）")
            if note.strip():
                lines.append(f"  · 睡前记录：{note.strip()}")
            else:
                lines.append("  · 睡前记录：（未填写）")
            day_blocks.append("\n".join(lines))
        recent_detail = (
            "\n\n".join(day_blocks) if day_blocks else "（无近 7 日数据）"
        )

        messages = build_suggestion_prompt(weekly, recent_detail)
        self.advice_status.configure(text="请求中…")
        self.advice_box.delete("1.0", "end")

        def work():
            try:
                out = chat_completion(base, key, model, messages)
            except LLMError as e:
                self.after(0, lambda: self._advice_done_err(str(e)))
                return
            self.after(0, lambda: self._advice_done_ok(out))

        threading.Thread(target=work, daemon=True).start()

    def _advice_done_ok(self, text: str) -> None:
        self.advice_status.configure(text="完成")
        self.advice_box.insert("1.0", text)

    def _advice_done_err(self, msg: str) -> None:
        self.advice_status.configure(text=f"失败：{msg}")
        self.advice_box.insert("1.0", msg)

    # --- 历史回顾 ---
    def _build_history_tab(self) -> None:
        frame = self.tab.tab("历史回顾")
        intro = ctk.CTkLabel(
            frame,
            text="列出数据库中所有「有任务或写过睡前记录」的日期，点选即可回看当日计划与记录（只读）。",
            wraplength=460,
            justify="left",
        )
        intro.pack(anchor="w", pady=(0, 6))

        bar = ctk.CTkFrame(frame, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 8))
        self.history_count_label = ctk.CTkLabel(bar, text="")
        self.history_count_label.pack(side="left")
        ctk.CTkButton(bar, text="刷新列表", width=88, command=self._refresh_history_list).pack(
            side="right"
        )

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True)

        self.history_date_scroll = ctk.CTkScrollableFrame(
            body, label_text="日期", width=150
        )
        self.history_date_scroll.pack(side="left", fill="y", padx=(0, 8))

        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        self.history_day_title = ctk.CTkLabel(
            right, text="请选择左侧日期", anchor="w", font=("", 15, "bold")
        )
        self.history_day_title.pack(fill="x", pady=(0, 6))

        self.history_task_scroll = ctk.CTkScrollableFrame(
            right, label_text="当日计划", height=180
        )
        self.history_task_scroll.pack(fill="x", pady=(0, 8))

        self.history_note_box = ctk.CTkTextbox(right, wrap="word", font=("", 13))
        self.history_note_box.pack(fill="both", expand=True)

        self._refresh_history_list()

    def _refresh_history_list(self) -> None:
        for w in self.history_date_scroll.winfo_children():
            w.destroy()
        dates = self.db.list_dates_with_activity()
        self.history_count_label.configure(text=f"共 {len(dates)} 天有数据")
        if not dates:
            ctk.CTkLabel(
                self.history_date_scroll, text="暂无记录\n先去写计划或睡前记录吧"
            ).pack(anchor="w", pady=8)
            self._clear_history_detail()
            return
        for d in dates:
            ctk.CTkButton(
                self.history_date_scroll,
                text=d,
                anchor="w",
                height=32,
                command=lambda iso=d: self._show_history_day(iso),
            ).pack(fill="x", pady=2)
        self._show_history_day(dates[0])

    def _clear_history_detail(self) -> None:
        self.history_day_title.configure(text="暂无选中日期")
        for w in self.history_task_scroll.winfo_children():
            w.destroy()
        self.history_note_box.configure(state="normal")
        self.history_note_box.delete("1.0", "end")
        self.history_note_box.insert("1.0", "")
        self.history_note_box.configure(state="disabled")

    def _show_history_day(self, iso: str) -> None:
        self.history_day_title.configure(text=iso)
        for w in self.history_task_scroll.winfo_children():
            w.destroy()
        tasks = self.db.list_tasks(iso)
        if not tasks:
            ctk.CTkLabel(
                self.history_task_scroll, text="（当日无计划任务）", anchor="w"
            ).pack(fill="x", pady=4)
        else:
            for t in tasks:
                mark = "✓" if t.done else "○"
                ctk.CTkLabel(
                    self.history_task_scroll,
                    text=f"{mark}  {t.title}",
                    anchor="w",
                ).pack(fill="x", pady=2)
        note = self.db.get_note(iso)
        self.history_note_box.configure(state="normal")
        self.history_note_box.delete("1.0", "end")
        self.history_note_box.insert(
            "1.0", note.strip() if note.strip() else "（当日未写睡前记录）"
        )
        self.history_note_box.configure(state="disabled")

    # --- 设置 ---
    def _build_settings_tab(self) -> None:
        frame = self.tab.tab("设置")
        ctk.CTkLabel(
            frame,
            text=f"程序版本 v{APP_VERSION} · 数据目录：{app_data_dir()}",
            wraplength=480,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))
        ctk.CTkLabel(frame, text="OpenAI 兼容接口（填写后保存）").pack(anchor="w")

        ctk.CTkLabel(frame, text="Base URL（如 https://api.openai.com）").pack(
            anchor="w", pady=(8, 0)
        )
        self.set_base = ctk.CTkEntry(frame, placeholder_text="https://...")
        self.set_base.pack(fill="x")
        self.set_base.insert(0, self.settings.get("api_base_url", ""))

        ctk.CTkLabel(frame, text="API Key").pack(anchor="w", pady=(8, 0))
        self.set_key = ctk.CTkEntry(frame, placeholder_text="sk-...", show="*")
        self.set_key.pack(fill="x")
        self.set_key.insert(0, self.settings.get("api_key", ""))

        ctk.CTkLabel(frame, text="模型名").pack(anchor="w", pady=(8, 0))
        self.set_model = ctk.CTkEntry(frame)
        self.set_model.pack(fill="x")
        self.set_model.insert(0, self.settings.get("model", DEFAULT_MODEL))

        self.set_topmost = ctk.CTkSwitch(frame, text="窗口置顶（贴在桌面）")
        self.set_topmost.pack(anchor="w", pady=(12, 0))
        if self.settings.get("always_on_top", True):
            self.set_topmost.select()
        else:
            self.set_topmost.deselect()

        ctk.CTkButton(frame, text="保存设置", command=self._save_settings_ui).pack(
            fill="x", pady=(16, 0)
        )

    def _save_settings_ui(self) -> None:
        self.settings["api_base_url"] = self.set_base.get().strip()
        self.settings["api_key"] = self.set_key.get().strip()
        self.settings["model"] = self.set_model.get().strip() or DEFAULT_MODEL
        self.settings["always_on_top"] = bool(self.set_topmost.get())
        save_settings(self.settings)
        self.attributes("-topmost", self.settings["always_on_top"])
        messagebox.showinfo("LearningDesk", "设置已保存", parent=self)

    def _on_close(self) -> None:
        try:
            self.settings["window_geometry"] = self.geometry()
            save_settings(self.settings)
        except Exception:
            pass
        self.db.close()
        self.destroy()


def run_app() -> None:
    app = LearningDeskApp()
    app.mainloop()
