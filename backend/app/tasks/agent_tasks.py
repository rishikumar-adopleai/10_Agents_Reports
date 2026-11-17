"""Celery Background Agent Execution and Outbox Dispatch Tasks."""

import asyncio
from typing import Any, Dict

from backend.app.agents.orchestrator import AgentOrchestrator
from backend.app.core.logging import logger
from backend.app.db.session import AsyncSessionLocal
from backend.app.schemas.agents import AgentExecutionRequest
from backend.app.tasks.celery_app import celery


@celery.task(bind=True, name="tasks.execute_agent_async", max_retries=3, default_retry_delay=10)
def execute_agent_async(self, request_dict: Dict[str, Any]):
    """Execute an agent task asynchronously within a Celery background worker."""
    req = AgentExecutionRequest(**request_dict)
    logger.info(f"Celery executing agent {req.agent_id} async")

    async def _run():
        async with AsyncSessionLocal() as session:
            orchestrator = AgentOrchestrator(session)
            result = await orchestrator.execute_agent(req)
            await session.commit()
            return result.model_dump()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio

            nest_asyncio.apply()
            return loop.run_until_complete(_run())
        return asyncio.run(_run())
    except Exception as exc:
        logger.error(f"Celery task failed: {exc}. Retrying...")
        raise self.retry(exc=exc)


@celery.task(name="tasks.poll_outbox_events")
def poll_outbox_events():
    """Poll transactional outbox table and dispatch pending domain events."""

    async def _poll():
        from backend.app.repositories.execution_repo import OutboxRepository

        async with AsyncSessionLocal() as session:
            outbox_repo = OutboxRepository(session)
            events = await outbox_repo.get_pending_events(limit=20)
            for event in events:
                logger.info(f"Dispatching outbox event: {event.event_type} [id={event.id}]")
                event.status = "published"
                await outbox_repo.update(event, {"status": "published"})
            await session.commit()

    asyncio.run(_poll())
