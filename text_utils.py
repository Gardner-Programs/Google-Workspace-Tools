"""Pure text helpers extracted from the admin scripts.

``extract_emails`` pulls email addresses out of pasted free-text; ``build_query``
assembles a Gmail search query from optional parts. Both are pure (no Google
API), so they can be tested without the _master/authenticator import chain.
"""

from __future__ import annotations

import re


def extract_emails(messy_text: str) -> list[str]:
    """Return all email-looking substrings from arbitrary pasted text."""
    return re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", messy_text)


def build_query(sender=None, subject=None, message_id=None) -> str:
    """Build a Gmail search query from sender, subject, and/or RFC822 Message-ID."""
    parts = []
    if message_id:
        parts.append(f"rfc822msgid:{message_id}")
    if sender:
        parts.append(f"from:({sender})")
    if subject:
        parts.append(f"subject:({subject})")
    return " ".join(parts)
