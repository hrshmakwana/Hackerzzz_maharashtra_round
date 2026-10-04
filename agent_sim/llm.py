"""Thin wrapper around the google-genai SDK with retries and a response cache.

The cache key is sha256(model + request), so replaying a prefix of a recorded Gemini run
costs zero tokens.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

from blackbox_sdk.schema import canonical_json, sha256

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
CACHE_PATH = ROOT / "data" / "llm_cache.jsonl"
_cache_lock = threading.Lock()
_cache: Optional[dict] = None


class LLMUnavailable(RuntimeError):
    pass


def gemini_available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY")) and bool(os.getenv("GEMINI_MODEL"))


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        _cache = {}
        if CACHE_PATH.exists():
            for line in CACHE_PATH.read_text().splitlines():
                try:
                    row = json.loads(line)
                    _cache[row["key"]] = row["value"]
                except (ValueError, KeyError):
                    continue
    return _cache


def cache_get(key: str) -> Any:
    with _cache_lock:
        return _load_cache().get(key)


def cache_put(key: str, value: Any) -> None:
    with _cache_lock:
        _load_cache()[key] = value
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CACHE_PATH.open("a") as f:
            f.write(json.dumps({"key": key, "value": value}, ensure_ascii=False) + "\n")


class GeminiClient:
    def __init__(self, model: Optional[str] = None):
        key = os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL")
        if not key:
            raise LLMUnavailable("GEMINI_API_KEY is not set")
        if not self.model:
            raise LLMUnavailable("GEMINI_MODEL is not set (pick a Flash model in AI Studio)")
        from google import genai

        self._genai = genai
        self.client = genai.Client(api_key=key)

    def _config(self, system: Optional[str], temperature: float, json_mode: bool,
                tools: Optional[list] = None):
        from google.genai import types

        kw: dict[str, Any] = {"temperature": temperature,
                              "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True)}
        if system:
            kw["system_instruction"] = system
        if json_mode:
            kw["response_mime_type"] = "application/json"
        if tools:
            kw["tools"] = tools
        return types.GenerateContentConfig(**kw)

    def call(self, contents: Any, *, system: Optional[str] = None, temperature: float = 0.0,
             json_mode: bool = False, tools: Optional[list] = None, retries: int = 5):
        delay = 2.0
        for attempt in range(retries):
            try:
                return self.client.models.generate_content(
                    model=self.model, contents=contents,
                    config=self._config(system, temperature, json_mode, tools))
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                transient = any(code in msg for code in ("429", "500", "502", "503", "504",
                                                         "RESOURCE_EXHAUSTED", "UNAVAILABLE",
                                                         "DEADLINE"))
                if not transient or attempt == retries - 1:
                    raise
                wait = delay
                m = re.search(r"retry in ([\d.]+)s", msg) or re.search(r"retryDelay['\"]?: ?['\"]?(\d+)", msg)
                if m:
                    wait = max(wait, float(m.group(1)) + 0.5)
                time.sleep(min(wait, 60))
                delay *= 2

    def text(self, prompt: str, *, system: Optional[str] = None, temperature: float = 0.0,
             use_cache: bool = True) -> str:
        key = sha256(canonical_json({"m": self.model, "p": prompt, "s": system, "t": temperature}))
        if use_cache and (hit := cache_get(key)) is not None:
            return hit
        resp = self.call(prompt, system=system, temperature=temperature)
        out = (resp.text or "").strip()
        if use_cache:
            cache_put(key, out)
        return out

    def json(self, prompt: str, *, system: Optional[str] = None, use_cache: bool = True) -> dict:
        key = sha256(canonical_json({"m": self.model, "p": prompt, "s": system, "j": 1}))
        if use_cache and (hit := cache_get(key)) is not None:
            return hit
        resp = self.call(prompt, system=system, json_mode=True)
        raw = (resp.text or "").strip()
        try:
            data = json.loads(raw)
        except ValueError:
            m = re.search(r"\{.*\}", raw, re.S)
            data = json.loads(m.group(0)) if m else {}
        if use_cache:
            cache_put(key, data)
        return data


# ------------------------------------------------------------------- groq


def groq_available() -> bool:
    return bool(os.getenv("GROQ_API_KEY"))


class GroqClient:
    """Groq's OpenAI-compatible chat API (free tier), used as an independent reviewer."""

    URL = "https://api.groq.com/openai/v1"

    def __init__(self, model: Optional[str] = None):
        self.key = os.getenv("GROQ_API_KEY")
        if not self.key:
            raise LLMUnavailable("GROQ_API_KEY is not set")
        self.model = model or os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b"

    def _post(self, payload: dict, retries: int = 4) -> dict:
        import httpx

        delay = 2.0
        for attempt in range(retries):
            r = httpx.post(f"{self.URL}/chat/completions", json=payload, timeout=60,
                           headers={"Authorization": f"Bearer {self.key}"})
            if r.status_code in (429, 500, 502, 503) and attempt < retries - 1:
                wait = float(r.headers.get("retry-after", delay))
                time.sleep(min(max(wait, delay), 30))
                delay *= 2
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("Groq request failed")

    def json(self, prompt: str, *, system: Optional[str] = None, use_cache: bool = True) -> dict:
        key = sha256(canonical_json({"m": "groq:" + self.model, "p": prompt, "s": system, "j": 1}))
        if use_cache and (hit := cache_get(key)) is not None:
            return hit
        messages = ([{"role": "system", "content": system}] if system else []) + \
            [{"role": "user", "content": prompt}]
        data = self._post({"model": self.model, "messages": messages, "temperature": 0,
                           "response_format": {"type": "json_object"}})
        raw = (data["choices"][0]["message"].get("content") or "").strip()
        try:
            out = json.loads(raw)
        except ValueError:
            m = re.search(r"\{.*\}", raw, re.S)
            out = json.loads(m.group(0)) if m else {}
        if use_cache:
            cache_put(key, out)
        return out


def model_label(model: str) -> str:
    """Short, human name for a model id."""
    m = model.lower().split("/")[-1]
    if "gemini" in m:
        return "Gemini"
    if "gpt-oss" in m:
        return "GPT-OSS"
    if "llama" in m:
        return "Llama"
    if "qwen" in m:
        return "Qwen"
    if "deepseek" in m:
        return "DeepSeek"
    if "kimi" in m:
        return "Kimi"
    return m.split("-")[0].capitalize()


MAKERS = {"Gemini": "Google", "GPT-OSS": "OpenAI", "Llama": "Meta", "Qwen": "Alibaba",
          "DeepSeek": "DeepSeek", "Kimi": "Moonshot"}
DEFAULT_GROQ_MODELS = "openai/gpt-oss-120b,qwen/qwen3.8-27b"


def groq_models() -> list[str]:
    raw = os.getenv("GROQ_MODELS") or os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODELS
    return [m.strip() for m in raw.split(",") if m.strip()]


def reviewers() -> list[tuple[str, Any]]:
    """Independent AIs (from different companies) available to double-check a diagnosis."""
    out: list[tuple[str, Any]] = []
    if gemini_available():
        c = GeminiClient()
        out.append((model_label(c.model or "gemini"), c))
    if groq_available():
        for m in groq_models():
            out.append((model_label(m), GroqClient(m)))
    return out
