"""OpenAI-compatible chat completions."""

from __future__ import annotations

from typing import Any

import requests


class LLMError(Exception):
    pass


def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: int = 120,
) -> str:
    url = base_url.rstrip("/") + "/v1/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.6,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as e:
        raise LLMError(f"网络请求失败：{e}") from e
    if r.status_code >= 400:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:2000]}")
    try:
        data = r.json()
    except ValueError as e:
        raise LLMError("响应不是合法 JSON") from e
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"无法解析模型输出：{data!r}") from e


def build_suggestion_prompt(
    weekly_summary: str, recent_daily_plan_and_notes: str
) -> list[dict[str, str]]:
    system = (
        "你是一名学习教练。根据用户提供的「周总结」以及「近 7 日按日列出的每日计划（含完成与否）"
        "与睡前学习记录」，用简洁的中文给出下一步学习建议：分条列出，包含巩固、补缺、下周重点，"
        "控制在 400 字以内。"
    )
    user = (
        "【周总结】（已含各日计划与记录的结构化汇总）\n\n"
        f"{weekly_summary}\n\n"
        "【近 7 日按日明细】（每日计划 + 睡前记录，便于你对照）\n\n"
        f"{recent_daily_plan_and_notes}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
