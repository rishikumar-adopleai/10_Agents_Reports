"""Agent Orchestration and Execution Engine."""

import asyncio
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.registry import agent_registry
from backend.app.core.exceptions import NotFoundError
from backend.app.core.logging import agent_execution_id_ctx, logger
from backend.app.models.execution import AgentTask, DomainEvent, OutboxEvent
from backend.app.repositories.execution_repo import AgentTaskRepository
from backend.app.schemas.agents import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentStatus,
)


class AgentOrchestrator:
    """Orchestrates agent execution, state management, audit logging, and outbox emission."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.task_repo = AgentTaskRepository(session)

    async def execute_agent(
        self,
        request: AgentExecutionRequest,
        timeout_seconds: int = 60,
    ) -> AgentExecutionResult:
        agent = agent_registry.get(request.agent_id)
        if not agent:
            raise NotFoundError(f"Agent '{request.agent_id}' is not registered in the system")

        execution_id = f"exec-{uuid.uuid4().hex[:16]}"
        agent_execution_id_ctx.set(execution_id)
        start_time = time.time()

        # 1. Create durable AgentTask record in PostgreSQL
        agent_task = AgentTask(
            organization_id=request.organization_id,
            agent_id=request.agent_id,
            execution_id=execution_id,
            status=AgentStatus.WAITING_FOR_INPUT.value,
            input_payload=request.parameters,
            uncertainty=0.0,
            cost_metadata={"start_time": start_time},
        )
        await self.task_repo.create(agent_task)

        # 2. Execute with bounded timeout
        try:
            logger.info(f"Starting execution of agent {request.agent_id} [exec={execution_id}]")
            result = await asyncio.wait_for(
                agent.execute(request, self.session),
                timeout=timeout_seconds,
            )
            elapsed_ms = int((time.time() - start_time) * 1000)

            # Update AgentTask with results
            agent_task.status = result.status.value
            agent_task.output_payload = result.structured_result
            agent_task.uncertainty = result.uncertainty
            agent_task.cost_metadata = {
                "elapsed_ms": elapsed_ms,
                "timeout_seconds": timeout_seconds,
            }
            await self.task_repo.update(
                agent_task,
                {
                    "status": agent_task.status,
                    "output_payload": agent_task.output_payload,
                    "uncertainty": agent_task.uncertainty,
                    "cost_metadata": agent_task.cost_metadata,
                },
            )

            # 3. Emit Domain Event and Outbox Event
            domain_event = DomainEvent(
                organization_id=request.organization_id,
                event_type=f"agent.{request.agent_id}.{result.status.value}",
                correlation_id=request.correlation_id,
                payload={
                    "execution_id": execution_id,
                    "agent_id": request.agent_id,
                    "status": result.status.value,
                    "account_id": request.account_id,
                    "contact_id": request.contact_id,
                    "proposed_next_actions": result.proposed_next_actions,
                },
            )
            self.session.add(domain_event)

            outbox_event = OutboxEvent(
                organization_id=request.organization_id,
                event_type=f"agent.{request.agent_id}.completed",
                correlation_id=request.correlation_id,
                payload=domain_event.payload,
                status="pending",
            )
            self.session.add(outbox_event)
            await self.session.flush()

            logger.info(
                f"Completed agent {request.agent_id} in {elapsed_ms}ms with status {result.status.value}"
            )
            return result

        except asyncio.TimeoutError:
            logger.error(f"Agent {request.agent_id} timed out after {timeout_seconds}s")
            agent_task.status = AgentStatus.RETRYABLE_FAILURE.value
            agent_task.error_message = f"Execution exceeded timeout limit of {timeout_seconds}s"
            await self.task_repo.update(
                agent_task,
                {
                    "status": agent_task.status,
                    "error_message": agent_task.error_message,
                },
            )
            return AgentExecutionResult(
                agent_id=request.agent_id,
                execution_id=execution_id,
                status=AgentStatus.RETRYABLE_FAILURE,
                error_details=f"Agent timed out after {timeout_seconds}s",
            )
        except Exception as e:
            logger.exception(f"Agent {request.agent_id} failed: {str(e)}")
            agent_task.status = AgentStatus.TERMINAL_FAILURE.value
            agent_task.error_message = str(e)
            await self.task_repo.update(
                agent_task,
                {
                    "status": agent_task.status,
                    "error_message": agent_task.error_message,
                },
            )
            return AgentExecutionResult(
                agent_id=request.agent_id,
                execution_id=execution_id,
                status=AgentStatus.TERMINAL_FAILURE,
                error_details=str(e),
            )
