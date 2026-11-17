"""
Node 3: Safety, Stop, Compliance & Out of Office Checker.
File: backend/app/agents/lead_responder/safety_checker.py

Evaluates incoming message for:
1. Hard Opt-Out ("STOP", "Unsubscribe", "Cancel") -> halt_opt_out (immediate suppression)
2. Wrong Number -> halt_wrong_number (invalidates identifier without suppressing account)
3. Negative disinterest ("Not interested", "Leave me alone") -> halt_not_interested (stops outreach)
4. Out of Office (OOO) -> halt_ooo (Option 3: extracts return date, does NOT suppress)
5. Existing suppression -> halt_suppressed
6. Genuine inbound messages -> proceed_to_reply (3-attempt restriction applies only to unsolicited outreach)
"""

import re
from typing import Any, Dict, Optional, Tuple

OPT_OUT_KEYWORDS = {"stop", "cancel", "unsubscribe", "quit", "end", "revoke"}
WRONG_NUMBER_PHRASES = {"wrong number", "who is this", "wrong person", "not my number", "wrong contact", "incorrect number"}
NOT_INTERESTED_PHRASES = {
    "not interested",
    "remove me",
    "don't contact",
    "dont contact",
    "leave me alone",
    "take me off",
    "stop messaging",
    "no thanks",
    "not looking",
    "please remove",
}

OOO_PATTERNS = [
    re.compile(r"out of (the )?office", re.IGNORECASE),
    re.compile(r"away from (my )?(desk|phone)", re.IGNORECASE),
    re.compile(r"auto(mated)? reply", re.IGNORECASE),
    re.compile(r"i am on vacation", re.IGNORECASE),
    re.compile(r"limited access to (email|phone)", re.IGNORECASE),
    re.compile(r"will return (on |by )?([A-Za-z]+ \d{1,2}|\w+day)", re.IGNORECASE),
]

RETURN_DATE_REGEX = re.compile(
    r"(?:back|return(?:ing)?|until)\s+(?:on\s+)?([A-Za-z]+ \d{1,2}(?:st|nd|rd|th)?|\w+day)",
    re.IGNORECASE,
)


class SafetyChecker:
    """Evaluates inbound text against compliance rules, separating STOP, wrong number, and OOO."""

    def evaluate(
        self,
        customer_context: Dict[str, Any],
        contact_store=None,
    ) -> Dict[str, Any]:
        reply_text = str(customer_context.get("inbound_message") or "").strip()
        clean_text = reply_text.lower()
        sender_id = customer_context.get("phone") or customer_context.get("email") or customer_context.get("sender_id") or ""
        lead_name = customer_context.get("name") or "there"

        # 1. Check if already suppressed (Fix 7)
        if customer_context.get("is_suppressed"):
            return {
                "is_safe_to_proceed": False,
                "is_ooo": False,
                "stop_reason": "already_suppressed",
                "action": "halt_suppressed",
                "detail": f"Sender {sender_id} is already in the suppression list.",
            }

        # 2. Check Opt-Out Keywords (STOP) (Fix 7 & 8)
        words = set(re.findall(r"\b\w+\b", clean_text))
        is_opt_out = bool(words & OPT_OUT_KEYWORDS) or clean_text in OPT_OUT_KEYWORDS
        if is_opt_out:
            return {
                "is_safe_to_proceed": False,
                "is_ooo": False,
                "stop_reason": "explicit_opt_out",
                "action": "halt_opt_out",
                "detail": f"Opt-out keyword detected: \"{reply_text}\"",
            }

        # 3. Check Wrong Number (Fix 8: Invalidate specific identifier only)
        is_wrong_number = any(phrase in clean_text for phrase in WRONG_NUMBER_PHRASES)
        if is_wrong_number:
            return {
                "is_safe_to_proceed": False,
                "is_ooo": False,
                "stop_reason": "wrong_number",
                "action": "halt_wrong_number",
                "detail": f"Wrong number phrase detected: \"{reply_text}\"",
            }

        # 4. Check Negative Disinterest (Fix 8)
        is_negative = any(phrase in clean_text for phrase in NOT_INTERESTED_PHRASES)
        if is_negative:
            return {
                "is_safe_to_proceed": False,
                "is_ooo": False,
                "stop_reason": "not_interested",
                "action": "halt_not_interested",
                "detail": f"Negative disinterest detected: \"{reply_text}\"",
            }

        # 5. Check Out of Office (OOO) -> Option 3 (Fix 7 & 8: Do NOT suppress)
        is_ooo = any(pattern.search(reply_text) for pattern in OOO_PATTERNS)
        if is_ooo:
            match = RETURN_DATE_REGEX.search(reply_text)
            return_date = match.group(1) if match else "next week"

            immediate_reply = (
                f"Thanks for letting me know, {lead_name.split()[0]}! Enjoy your time away. "
                f"I'll follow up with you after {return_date}."
            )
            scheduled_followup = (
                f"Hi {lead_name.split()[0]}, hope you had a great time away! Circling back as promised. "
                f"Would you have 15 minutes later this week to connect?"
            )

            return {
                "is_safe_to_proceed": False,
                "is_ooo": True,
                "stop_reason": "out_of_office",
                "action": "halt_ooo",
                "detail": f"Out of Office detected. Return date: {return_date}",
                "ooo_plan": {
                    "return_date": return_date,
                    "immediate_acknowledgment": immediate_reply,
                    "scheduled_followup": scheduled_followup,
                },
            }

        # 6. Safe to proceed normally (Fix 9: outreach limits do not block genuine inbound replies)
        return {
            "is_safe_to_proceed": True,
            "is_ooo": False,
            "stop_reason": None,
            "action": "proceed_to_reply",
            "detail": "Message passed all safety checks.",
        }
