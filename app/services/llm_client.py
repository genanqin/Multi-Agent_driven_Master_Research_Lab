from __future__ import annotations

from dataclasses import dataclass

import requests

from app.config import get_settings


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


class LLMClient:
    """Small adapter kept ready for the later large-model API key."""

    _recent_errors: list[str] = []

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return self.settings.llm_provider != "mock" and bool(self.settings.llm_api_key)

    def complete(self, messages: list[LLMMessage], temperature: float = 0.3) -> str:
        if not self.enabled:
            return self._mock_response(messages)
        if not self.settings.llm_base_url:
            self.record_error("missing LLM_BASE_URL")
            raise ValueError("LLM_BASE_URL is required when LLM_PROVIDER is not mock")

        try:
            response = requests.post(
                self.settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
                json={
                    "model": self.settings.llm_model,
                    "messages": [message.__dict__ for message in messages],
                    "temperature": temperature,
                    "max_tokens": 800,
                    "thinking": {"type": "disabled"},
                },
                timeout=45,
            )
            response.raise_for_status()
            payload = response.json()
            return payload["choices"][0]["message"]["content"]
        except Exception as exc:
            self.record_error(f"{type(exc).__name__}: {exc}")
            raise

    def _mock_response(self, messages: list[LLMMessage]) -> str:
        last = messages[-1].content if messages else ""
        return f"本地规则引擎响应：{last[:180]}"

    @classmethod
    def record_error(cls, message: str) -> None:
        cleaned = " ".join(str(message).split())
        if cleaned:
            cls._recent_errors.append(cleaned[:180])
            cls._recent_errors = cls._recent_errors[-8:]

    @classmethod
    def clear_recent_errors(cls) -> None:
        cls._recent_errors.clear()

    @classmethod
    def consume_recent_errors(cls) -> list[str]:
        errors = list(cls._recent_errors)
        cls.clear_recent_errors()
        return errors
