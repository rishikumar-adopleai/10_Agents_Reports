"""Inbound Messaging Webhook Ingest and Processing."""

import hashlib
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import logger
from backend.app.db.session import get_db
from backend.app.models.conversations import Conversation, Message
from backend.app.models.execution import OutboxEvent
from backend.app.models.sales import Contact
from backend.app.repositories.conversation_repo import (
    ConversationRepository,
    MessageRepository,
)
from backend.app.schemas.common import StandardResponse
from backend.app.schemas.conversations import InboundWebhookPayload
from backend.app.services.suppression_service import SuppressionService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Opt-out keywords according to CTIA compliance rules
OPT_OUT_KEYWORDS = {"stop", "cancel", "unsubscribe", "quit", "end", "revoke"}
NEGATIVE_KEYWORDS = {
    "not interested",
    "remove me",
    "don't contact",
    "leave me alone",
    "wrong number",
}


@router.post("/sms", response_model=StandardResponse[dict], status_code=status.HTTP_200_OK)
async def inbound_sms_webhook(
    payload: InboundWebhookPayload,
    session: AsyncSession = Depends(get_db),
):
    """
    Ingest, deduplicate, persist, and process inbound SMS message.
    Strict Business Rules:
    1. Deduplicate by provider message ID and hash before acknowledging.
    2. Check opt-out and negative keywords -> immediate hard suppression.
    3. If suppressed, cancel pending actions and stop auto-responder.
    4. Otherwise, queue lead responder agent task via Outbox.
    """
    sender = payload.sender_phone.strip()
    body = payload.body.strip()
    raw_hash = hashlib.sha256(
        f"{payload.provider}:{payload.message_id}:{sender}:{body}".encode()
    ).hexdigest()

    msg_repo = MessageRepository(session)
    existing_msg = await msg_repo.get_by_dedup_hash(raw_hash)
    if existing_msg:
        logger.info(f"Deduplicated inbound message {payload.message_id}")
        return StandardResponse(
            data={"status": "duplicate_ignored"}, message="Message already processed"
        )

    # Locate contact by phone
    from sqlalchemy import select

    res = await session.execute(select(Contact).where(Contact.phone == sender))
    contact = res.scalars().first()

    organization_id = contact.organization_id if contact else "org-default"

    # 1. Check for Opt-Out / Negative Reply
    clean_body = body.lower()
    is_opt_out = clean_body in OPT_OUT_KEYWORDS
    is_negative = any(neg in clean_body for neg in NEGATIVE_KEYWORDS)

    suppression_service = SuppressionService(session)
    if is_opt_out or is_negative:
        reason = "opt_out" if is_opt_out else "negative_reply"
        await suppression_service.record_suppression(
            organization_id=organization_id,
            reason=reason,
            contact_id=contact.id if contact else None,
            phone=sender,
            notes=f"Triggered by inbound message: '{body[:100]}'",
        )
        logger.warning(f"Contact {sender} marked suppressed with reason: {reason}")

    # 2. Find or create Conversation
    conv_repo = ConversationRepository(session)
    conv = None
    if contact:
        conv = await conv_repo.get_by_contact_channel(
            contact_id=contact.id,
            channel="sms",
            organization_id=organization_id,
        )

    if not conv:
        conv = Conversation(
            organization_id=organization_id,
            account_id=contact.account_id if contact else str(uuid.uuid4()),
            contact_id=contact.id if contact else str(uuid.uuid4()),
            channel="sms",
            status="active",
        )
        await conv_repo.create(conv)

    # 3. Persist Message
    new_message = Message(
        organization_id=organization_id,
        conversation_id=conv.id,
        direction="inbound",
        sender=sender,
        recipient=payload.recipient_phone,
        body=body,
        deduplication_hash=raw_hash,
        external_id=payload.message_id,
        status="received",
        is_verified=True,
    )
    await msg_repo.create(new_message)

    # 4. If not suppressed and not human takeover, queue event into Outbox for Lead Responder Agent
    if not is_opt_out and not is_negative and not conv.is_human_takeover:
        outbox_event = OutboxEvent(
            organization_id=organization_id,
            event_type="message.received",
            correlation_id=str(uuid.uuid4()),
            payload={
                "message_id": new_message.id,
                "conversation_id": conv.id,
                "contact_id": conv.contact_id,
                "sender": sender,
                "body": body,
            },
            status="pending",
        )
        session.add(outbox_event)
        await session.flush()

    return StandardResponse(
        data={"status": "ingested", "message_id": new_message.id},
        message="Inbound message persisted and queued",
    )
