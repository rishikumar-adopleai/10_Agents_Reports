"""Apollo.io Account and Contact Enrichment Adapter."""

from typing import Any, Dict, Optional

import httpx

from backend.app.core.config import settings
from backend.app.integrations.base import BaseIntegrationAdapter, IntegrationHealth


class ApolloAdapter(BaseIntegrationAdapter):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.APOLLO_API_KEY
        self.base_url = settings.APOLLO_BASE_URL

    @property
    def provider_name(self) -> str:
        return "apollo"

    async def check_health(self) -> IntegrationHealth:
        if self.api_key.startswith("mock"):
            return IntegrationHealth(
                provider=self.provider_name,
                status="healthy",
                latency_ms=4,
                details={"mode": "mock"},
            )
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(
                    f"{self.base_url}/organizations/enrich",
                    json={"api_key": self.api_key, "domain": "example.com"},
                )
                if res.status_code in [200, 404]:
                    return IntegrationHealth(
                        provider=self.provider_name, status="healthy", latency_ms=40
                    )
                return IntegrationHealth(provider=self.provider_name, status="degraded")
        except Exception as e:
            return IntegrationHealth(
                provider=self.provider_name, status="unavailable", details={"error": str(e)}
            )

    async def enrich_organization(self, domain: str) -> Dict[str, Any]:
        """Fetch organization profile and buying signals from Apollo."""
        if self.api_key.startswith("mock"):
            return {
                "name": domain.split(".")[0].capitalize(),
                "domain": domain,
                "estimated_num_employees": 250,
                "industry": "Software & Technology",
                "technologies": ["AWS", "Salesforce", "PostgreSQL", "React"],
            }

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                f"{self.base_url}/organizations/enrich",
                json={"api_key": self.api_key, "domain": domain},
            )
            res.raise_for_status()
            return res.json().get("organization", {})
