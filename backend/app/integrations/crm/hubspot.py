"""HubSpot CRM Integration Adapter."""

from typing import Any, Dict, Optional

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.integrations.base import BaseIntegrationAdapter, IntegrationHealth


class HubSpotAdapter(BaseIntegrationAdapter):
    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or settings.HUBSPOT_ACCESS_TOKEN
        self.base_url = settings.HUBSPOT_BASE_URL

    @property
    def provider_name(self) -> str:
        return "hubspot"

    async def check_health(self) -> IntegrationHealth:
        if self.access_token.startswith("mock"):
            return IntegrationHealth(
                provider=self.provider_name,
                status="healthy",
                latency_ms=5,
                details={"mode": "mock"},
            )
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    f"{self.base_url}/crm/v3/objects/contacts?limit=1",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                )
                if res.status_code == 200:
                    return IntegrationHealth(
                        provider=self.provider_name, status="healthy", latency_ms=25
                    )
                return IntegrationHealth(
                    provider=self.provider_name,
                    status="degraded",
                    details={"status_code": res.status_code},
                )
        except Exception as e:
            return IntegrationHealth(
                provider=self.provider_name, status="unavailable", details={"error": str(e)}
            )

    async def sync_contact(self, email: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update contact in HubSpot CRM."""
        if self.access_token.startswith("mock"):
            logger.info(f"[Mock HubSpot] Synced contact {email} with properties {properties}")
            return {"id": "mock-hs-contact-12345", "email": email, "properties": properties}

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                f"{self.base_url}/crm/v3/objects/contacts",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json={"properties": {"email": email, **properties}},
            )
            res.raise_for_status()
            return res.json()
