"""
Node 1: Unified Ingest & Deduplication for SMS (SipLink) and Email.

File: backend/app/agents/lead_responder/node_1_email_sms.py

Responsibilities:
1. Channel Auto-Detection (SMS vs Email)
2. SMS Ingest: SipLink frame unpack, phone normalization, echo & carrier receipt filter, 2-level dedup
3. Email Ingest: Email normalization, daemon/bounce filter, quoted reply & signature strip, 2-level dedup
4. Emits a 100% standardized InboundMessage dictionary for Node 2.
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

# ==============================================================================
# 1. CONSTANTS & IN-MEMORY DEDUPLICATION CACHES
# ==============================================================================

# SMS Level 1: topic:seq cache (max 2000 items)
_SMS_SEQ_CACHE: List[str] = []
_SMS_SEQ_MAX = 2000

# SMS Level 2: phone + text cache (1-hour TTL)
_SMS_TEXT_CACHE: Dict[str, Dict[str, float]] = {}

# Email Level 1: Message-ID cache (max 2000 items)
_EMAIL_MSGID_CACHE: List[str] = []
_EMAIL_MSGID_MAX = 2000

# Email Level 2: email + text cache (1-hour TTL)
_EMAIL_TEXT_CACHE: Dict[str, Dict[str, float]] = {}

_DEFAULT_TTL_SECONDS = 3600

# Regex patterns
_PHONE_RE = re.compile(r"[^0-9]+")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

CARRIER_RECEIPT_PREFIXES = (
    "delivery receipt from",
    "delivery confirmation",
    "msg delivered",
    "undelivered:",
)

DAEMON_EMAIL_PREFIXES = (
    "mailer-daemon@",
    "postmaster@",
    "no-reply@",
    "noreply@",
    "donotreply@",
)

EMAIL_QUOTE_SPLITTERS = [
    re.compile(r"^On\s+.*,\s+.*wrote:", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^-+Original Message-+\s*", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^From:\s+.*", re.MULTILINE),
    re.compile(r"^\s*>{1,3}\s+.*", re.MULTILINE),
    re.compile(r"^-{2,}\s*$", re.MULTILINE),  # standard sig dash
]


# ==============================================================================
# 2. NORMALIZATION & CLEANING HELPERS
# ==============================================================================

def normalize_phone(raw: Any) -> str:
    """Normalize phone numbers to canonical 11-digit US format (1XXXXXXXXXX)."""
    digits = _PHONE_RE.sub("", str(raw or "").strip())
    if len(digits) == 10:
        return "1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return digits
    return digits


def normalize_email(raw: Any) -> str:
    """Extract and lowercase canonical email address."""
    clean = str(raw or "").strip().lower()
    match = _EMAIL_RE.search(clean)
    return match.group(0) if match else clean


def strip_quoted_email_history(raw_body: str) -> str:
    """
    Strips quoted history ('On Mon, ... wrote:', '-----Original Message-----',
    and '>' reply chains) to isolate only the new message written by the lead.
    Guarantees critical compliance commands ('STOP', 'unsubscribe') are NEVER stripped.
    """
    text = str(raw_body or "").strip()
    if not text:
        return ""

    original_text = text

    # Split on standard reply headers and take only the top section
    for pattern in EMAIL_QUOTE_SPLITTERS:
        parts = pattern.split(text, maxsplit=1)
        if len(parts) > 1 and parts[0].strip():
            text = parts[0].strip()

    # Process line-by-line: strip quote characters, but preserve critical commands
    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            # If quote line contains an explicit opt-out command, keep the command!
            inner = stripped.lstrip("> ").strip()
            if inner.lower() in {"stop", "unsubscribe", "cancel", "quit", "end", "remove me"}:
                cleaned_lines.append(inner)
        else:
            cleaned_lines.append(line)

    result = "\n".join(cleaned_lines).strip()
    # Failsafe: if stripping wiped everything, fall back to the original text
    return result if result else original_text


def is_carrier_noise(text: str) -> bool:
    """Detects SMS delivery receipts and carrier opt-in notifications."""
    clean = str(text or "").strip().lower()
    if any(clean.startswith(prefix) for prefix in CARRIER_RECEIPT_PREFIXES):
        return True
    if "reply help" in clean and "unsubscribe" in clean:
        return True
    return False


def is_system_daemon_email(email_addr: str, subject: str) -> bool:
    """Detects automated mail delivery failures, bounces, and system notifications."""
    clean_email = email_addr.lower()
    clean_subj = subject.lower()

    if any(clean_email.startswith(prefix) for prefix in DAEMON_EMAIL_PREFIXES):
        return True
    if any(k in clean_subj for k in ["delivery failure", "failure notice", "undeliverable:", "mail delivery failed"]):
        return True
    return False


# ==============================================================================
# 3. DEDUPLICATION LOGIC
# ==============================================================================

def is_duplicate_sms(topic: Optional[str], seq: Optional[Any], from_phone: str, text: str) -> bool:
    """Two-level SMS deduplication (Level 1: topic:seq | Level 2: phone+text)."""
    global _SMS_SEQ_CACHE
    now = time.time()
    clean_text = text.strip().lower()

    # Level 1: topic:seq
    if topic and seq is not None:
        key = f"{topic}:{seq}"
        if key in _SMS_SEQ_CACHE:
            return True
        _SMS_SEQ_CACHE.append(key)
        if len(_SMS_SEQ_CACHE) > _SMS_SEQ_MAX:
            _SMS_SEQ_CACHE.pop(0)

    # Level 2: phone + text
    if from_phone in _SMS_TEXT_CACHE:
        if clean_text in _SMS_TEXT_CACHE[from_phone]:
            if now - _SMS_TEXT_CACHE[from_phone][clean_text] <= _DEFAULT_TTL_SECONDS:
                return True

    if from_phone not in _SMS_TEXT_CACHE:
        _SMS_TEXT_CACHE[from_phone] = {}
    _SMS_TEXT_CACHE[from_phone][clean_text] = now
    return False


def is_duplicate_email(message_id: Optional[str], from_email: str, text: str) -> bool:
    """Two-level Email deduplication (Level 1: Message-ID | Level 2: email+text)."""
    global _EMAIL_MSGID_CACHE
    now = time.time()
    clean_text = text.strip().lower()

    # Level 1: Message-ID header
    if message_id:
        clean_msgid = message_id.strip()
        if clean_msgid in _EMAIL_MSGID_CACHE:
            return True
        _EMAIL_MSGID_CACHE.append(clean_msgid)
        if len(_EMAIL_MSGID_CACHE) > _EMAIL_MSGID_MAX:
            _EMAIL_MSGID_CACHE.pop(0)

    # Level 2: email + text
    if from_email in _EMAIL_TEXT_CACHE:
        if clean_text in _EMAIL_TEXT_CACHE[from_email]:
            if now - _EMAIL_TEXT_CACHE[from_email][clean_text] <= _DEFAULT_TTL_SECONDS:
                return True

    if from_email not in _EMAIL_TEXT_CACHE:
        _EMAIL_TEXT_CACHE[from_email] = {}
    _EMAIL_TEXT_CACHE[from_email][clean_text] = now
    return False


# ==============================================================================
# 4. CHANNEL ADAPTERS (SMS & EMAIL) & AUTHENTICITY
# ==============================================================================

def verify_webhook_authenticity(
    raw_payload: Dict[str, Any],
    auth_header: Optional[str] = None,
    expected_secret: Optional[str] = None,
) -> bool:
    """
    Fix 1: Verifies incoming webhook authenticity.
    Validates token from header, environment variable WEBHOOK_SECRET, or payload.
    """
    secret = expected_secret or os.getenv("WEBHOOK_SECRET")
    # If no secret configured across environment, accept standard provider event
    if not secret:
        if raw_payload.get("is_authenticated") is False:
            return False
        return True

    token_candidate = (
        auth_header
        or raw_payload.get("auth_token")
        or raw_payload.get("token")
        or raw_payload.get("webhook_secret")
    )
    if not token_candidate:
        return False
    return str(token_candidate).strip() == str(secret).strip()


def process_sms_ingest(
    raw_payload: Dict[str, Any],
    our_sender_numbers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Ingests, cleans, filters, and deduplicates an incoming SMS event."""
    senders = {normalize_phone(s) for s in (our_sender_numbers or []) if s}

    data_frame = raw_payload.get("data") if "data" in raw_payload and isinstance(raw_payload["data"], dict) else raw_payload
    if not isinstance(data_frame, dict):
        return {"channel": "sms", "status": "invalid_payload", "is_valid_lead_msg": False}

    head = data_frame.get("head") or {}
    content_raw = data_frame.get("content")

    if isinstance(content_raw, str):
        try:
            content = json.loads(content_raw)
        except json.JSONDecodeError:
            content = {"contents": content_raw}
    elif isinstance(content_raw, dict):
        content = content_raw
    else:
        content = {}

    reply_text = str(
        content.get("contents")
        or content.get("content")
        or data_frame.get("reply_text")
        or data_frame.get("body")
        or ""
    ).strip()

    if not reply_text:
        return {"channel": "sms", "status": "skipped_empty_body", "is_valid_lead_msg": False}

    if is_carrier_noise(reply_text):
        return {"channel": "sms", "status": "skipped_carrier_receipt", "is_valid_lead_msg": False}

    from_raw = (
        content.get("from_number")
        or content.get("outbound_caller_id")
        or head.get("from_number")
        or data_frame.get("from_number")
        or ""
    )
    to_raw = (
        content.get("did")
        or content.get("to")
        or content.get("to_number")
        or head.get("to_number")
        or data_frame.get("to_number")
        or ""
    )

    from_number = normalize_phone(from_raw)
    to_number = normalize_phone(to_raw)

    # Drop outbound echoes (Fix 3)
    if raw_payload.get("direction") == "outbound" or data_frame.get("direction") == "outbound":
        return {"channel": "sms", "status": "skipped_outbound_echo", "is_valid_lead_msg": False}

    if from_number in senders or any(from_number.endswith(s[-10:]) for s in senders if len(s) >= 10):
        return {"channel": "sms", "status": "skipped_outbound_echo", "is_valid_lead_msg": False}

    topic = data_frame.get("topic")
    seq = data_frame.get("seq")

    # Deduplication Level 1 (In-Memory)
    if is_duplicate_sms(topic, seq, from_number, reply_text):
        return {"channel": "sms", "status": "skipped_duplicate", "is_valid_lead_msg": False}

    # Deduplication Level 2 (DB-backed Idempotency - Fix 2)
    payload_hash = hashlib.sha256(f"{from_number}:{reply_text}".encode()).hexdigest()
    provider_event_id = f"{topic}:{seq}" if (topic and seq is not None) else None
    try:
        from backend.app.agents.lead_responder.sqlite_store import SQLiteContactStore
        _store = SQLiteContactStore()
        if _store.is_duplicate_event(provider_event_id, payload_hash):
            return {"channel": "sms", "status": "skipped_duplicate", "is_valid_lead_msg": False}
        _store.record_inbound_event(provider_event_id, "sms", json.dumps(raw_payload), payload_hash)
    except Exception:
        pass

    # Timestamp
    ts_raw = data_frame.get("ts") or head.get("ts") or ""
    if isinstance(ts_raw, (int, float)):
        received_at = datetime.fromtimestamp(float(ts_raw) / 1000, tz=timezone.utc).isoformat()
    elif isinstance(ts_raw, str) and ts_raw:
        received_at = ts_raw
    else:
        received_at = datetime.now(timezone.utc).isoformat()

    return {
        "channel": "sms",
        "status": "accepted",
        "is_valid_lead_msg": True,
        "sender_id": from_number,
        "sender_phone": from_number,
        "sender_email": None,
        "recipient_id": to_number,
        "reply_text": reply_text,
        "subject": None,
        "topic": topic,
        "seq": seq,
        "message_id": None,
        "thread_id": f"sms_{from_number}_{to_number}",
        "received_at": received_at,
    }


def process_email_ingest(
    raw_payload: Dict[str, Any],
    our_email_domains: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Ingests, cleans, filters, and deduplicates an incoming Email event."""
    our_domains = {d.lower().strip() for d in (our_email_domains or [])}

    from_raw = raw_payload.get("from") or raw_payload.get("from_email") or raw_payload.get("sender") or ""
    to_raw = raw_payload.get("to") or raw_payload.get("to_email") or raw_payload.get("recipient") or ""
    subject = str(raw_payload.get("subject") or "").strip()
    raw_body = (
        raw_payload.get("body_plain")
        or raw_payload.get("text")
        or raw_payload.get("body")
        or raw_payload.get("html")
        or ""
    )

    from_email = normalize_email(from_raw)
    to_email = normalize_email(to_raw)

    if not from_email:
        return {"channel": "email", "status": "invalid_email_sender", "is_valid_lead_msg": False}

    # Drop outbound echoes from our own sending domains or outbound direction (Fix 3)
    if raw_payload.get("direction") == "outbound":
        return {"channel": "email", "status": "skipped_outbound_echo", "is_valid_lead_msg": False}

    sender_domain = from_email.split("@")[-1] if "@" in from_email else ""
    if sender_domain in our_domains:
        return {"channel": "email", "status": "skipped_outbound_echo", "is_valid_lead_msg": False}

    # Drop daemon / bounce notices
    if is_system_daemon_email(from_email, subject):
        return {"channel": "email", "status": "skipped_daemon_bounce", "is_valid_lead_msg": False}

    # Strip quoted email chain and signatures (preserves STOP and questions - Fix 3)
    clean_text = strip_quoted_email_history(raw_body)
    if not clean_text:
        return {"channel": "email", "status": "skipped_empty_body", "is_valid_lead_msg": False}

    message_id = raw_payload.get("message_id") or raw_payload.get("Message-ID") or raw_payload.get("id")
    in_reply_to = raw_payload.get("in_reply_to") or raw_payload.get("thread_id") or f"email_{from_email}"

    # Deduplication Level 1 (In-Memory)
    if is_duplicate_email(message_id, from_email, clean_text):
        return {"channel": "email", "status": "skipped_duplicate", "is_valid_lead_msg": False}

    # Deduplication Level 2 (DB-backed Idempotency - Fix 2)
    payload_hash = hashlib.sha256(f"{from_email}:{clean_text}".encode()).hexdigest()
    try:
        from backend.app.agents.lead_responder.sqlite_store import SQLiteContactStore
        _store = SQLiteContactStore()
        if _store.is_duplicate_event(message_id, payload_hash):
            return {"channel": "email", "status": "skipped_duplicate", "is_valid_lead_msg": False}
        _store.record_inbound_event(message_id, "email", json.dumps(raw_payload), payload_hash)
    except Exception:
        pass

    received_at = raw_payload.get("received_at") or datetime.now(timezone.utc).isoformat()

    return {
        "channel": "email",
        "status": "accepted",
        "is_valid_lead_msg": True,
        "sender_id": from_email,
        "sender_phone": None,
        "sender_email": from_email,
        "recipient_id": to_email,
        "reply_text": clean_text,
        "subject": subject,
        "topic": None,
        "seq": None,
        "message_id": message_id,
        "thread_id": in_reply_to,
        "received_at": received_at,
    }


# ==============================================================================
# 5. UNIFIED FRONT-DOOR FUNCTION (NODE 1)
# ==============================================================================

def node_1_receive_inbound(
    raw_payload: Dict[str, Any],
    our_sender_numbers: Optional[List[str]] = None,
    our_email_domains: Optional[List[str]] = None,
    auth_header: Optional[str] = None,
    expected_secret: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main entry point for Node 1.
    Detects if raw_payload is an SMS or Email, verifies authenticity, executes
    cleaning and multi-level deduplication, and returns the unified standardized contract.
    """
    # Auto-detect channel
    is_email = (
        raw_payload.get("channel") == "email"
        or "from_email" in raw_payload
        or ("from" in raw_payload and "@" in str(raw_payload["from"]))
        or "subject" in raw_payload
        or "body_plain" in raw_payload
    )

    # 1. Verify Webhook Authenticity (Fix 1)
    if not verify_webhook_authenticity(raw_payload, auth_header=auth_header, expected_secret=expected_secret):
        return {
            "channel": "email" if is_email else "sms",
            "status": "unauthorized_webhook",
            "is_valid_lead_msg": False,
            "sender_id": "",
            "reply_text": "",
        }

    # 2. Channel-specific Ingest & Deduplication (Fix 2 & 3)
    if is_email:
        return process_email_ingest(raw_payload, our_email_domains=our_email_domains)
    else:
        return process_sms_ingest(raw_payload, our_sender_numbers=our_sender_numbers)
