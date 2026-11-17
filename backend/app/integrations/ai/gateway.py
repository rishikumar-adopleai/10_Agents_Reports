"""Configurable LLM Provider Gateway."""

import json
from typing import Any, Dict, Optional

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.integrations.base import BaseIntegrationAdapter, IntegrationHealth


class LLMGateway(BaseIntegrationAdapter):
    def __init__(self):
        self.provider = settings.AI_PROVIDER
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.OPENAI_MODEL
        self.fallback_model = settings.OPENAI_FALLBACK_MODEL
        self.timeout = settings.AI_TIMEOUT_SECONDS

    @property
    def provider_name(self) -> str:
        return "llm_gateway"

    async def check_health(self) -> IntegrationHealth:
        return IntegrationHealth(
            provider=self.provider_name,
            status="healthy",
            latency_ms=10,
            details={"provider": self.provider, "primary_model": self.model},
        )

    async def generate_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[str] = "json_object",
    ) -> Dict[str, Any]:
        """Generate structured completion using primary or fallback model."""
        if self.provider == "mock" or self.api_key.startswith("mock"):
            logger.info("Using deterministic Mock LLM Gateway response")
            return {
                "decision": "approved",
                "reasoning": "Inputs conform to enterprise ICP and business rules.",
                "confidence": 0.96,
            }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": response_format} if response_format else None,
            "temperature": 0.2,
        }

        try:
            async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
                res = await client.post(
                    "https://api.openai.com/v1/chat/completions", headers=headers, json=payload
                )
                res.raise_for_status()
                data = res.json()
                content = data["choices"][0]["message"]["content"]
                return (
                    json.loads(content)
                    if response_format == "json_object"
                    else {"content": content}
                )
        except Exception as e:
            logger.warning(
                f"Primary model {self.model} failed: {str(e)}. Attempting fallback {self.fallback_model}"
            )
            payload["model"] = self.fallback_model
            async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
                res = await client.post(
                    "https://api.openai.com/v1/chat/completions", headers=headers, json=payload
                )
                res.raise_for_status()
                data = res.json()
                content = data["choices"][0]["message"]["content"]
                return (
                    json.loads(content)
                    if response_format == "json_object"
                    else {"content": content}
                )
