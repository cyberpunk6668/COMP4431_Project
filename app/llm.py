"""Restricted DeepSeek adapter; fixed official endpoint prevents key exfiltration."""
import asyncio

import httpx

from app.config import Settings

ENDPOINT = "https://api.deepseek.com/chat/completions"


class ProviderError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class DeepSeek:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, messages: list[dict], *, json_output: bool = False) -> str:
        payload = {
            "model": self.settings.model, "messages": messages, "stream": False,
            "thinking": {"type": "disabled"}, "max_tokens": 1400, "temperature": 0.2,
        }
        if json_output:
            payload["response_format"] = {"type": "json_object"}
        try:
            async with asyncio.timeout(self.settings.timeout):
                async with httpx.AsyncClient(timeout=httpx.Timeout(self.settings.timeout, connect=10), follow_redirects=False) as client:
                    response = await client.post(ENDPOINT, headers={"Authorization": f"Bearer {self.settings.api_key}"}, json=payload)
            if response.status_code != 200:
                codes = {401: "authentication_failed", 402: "insufficient_balance", 429: "rate_limited"}
                raise ProviderError(codes.get(response.status_code, "provider_unavailable"))
            payload = response.json()
            if not isinstance(payload, dict):
                raise ProviderError("invalid_response")
            choices = payload.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise ProviderError("invalid_response")
            choice = choices[0]
            if choice.get("finish_reason") != "stop":
                raise ProviderError("incomplete_response")
            if not isinstance(choice.get("message"), dict):
                raise ProviderError("invalid_response")
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ProviderError("empty_response")
            return content.strip()
        except (httpx.RequestError, TimeoutError):
            raise ProviderError("network_or_timeout") from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("invalid_response") from None
