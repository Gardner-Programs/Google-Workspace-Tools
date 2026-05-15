"""Investigate a user's mailbox for likely phishing emails around a compromise window.

Pulls messages in a date range, extracts key headers and URLs,
scores each message on phishing indicators, and ranks results.
"""
import base64
import csv
import os
import re
from datetime import datetime, timedelta
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_gmail_service, rate_limited_execute, ask_export, pick, pause, OUTPUT_DIR


# ── Phishing indicators and scoring ────────────────────────────

SUSPICIOUS_SENDER_KEYWORDS = [
    "security", "support", "admin", "helpdesk", "account", "verify",
    "noreply", "notification", "alert", "service", "team", "billing",
    "confirm", "update", "suspended", "locked", "urgent",
]

SUSPICIOUS_SUBJECT_KEYWORDS = [
    "urgent", "action required", "verify", "confirm", "suspend",
    "unusual", "sign-in", "signin", "login", "password", "expire",
    "unauthorized", "security alert", "account", "locked", "review",
    "shared document", "shared file", "voicemail", "invoice",
    "payment", "reset", "update required", "important",
]

OAUTH_URL_PATTERNS = [
    r"accounts\.google\.com/o/oauth2",
    r"accounts\.google\.com/signin/oauth",
    r"accounts\.google\.com/AccountChooser",
    r"login\.microsoftonline\.com",
    r"consent\.google\.com",
]

SUSPICIOUS_URL_PATTERNS = [
    r"bit\.ly", r"tinyurl\.com", r"goo\.gl", r"t\.co/",
    r"rb\.gy", r"is\.gd", r"shorte\.st", r"ow\.ly",
    r"forms\.gle", r"docs\.google\.com/forms",
    r"sites\.google\.com/",            # Google Sites used for phishing
    r"storage\.googleapis\.com",        # GCS hosted phishing pages
    r"firebasestorage\.googleapis\.com",
    r"appspot\.com",
    r"web\.app",
    r"page\.link",
    r"\.workers\.dev",                  # Cloudflare Workers
    r"ngrok\.io",
    r"trycloudflare\.com",
    r"sharepoint\.com/:.",              # Sharepoint sharing links
]


def extract_urls(text):
    """Pull all URLs from a block of text."""
    return re.findall(r'https?://[^\s<>"\')\]]+', text, re.IGNORECASE)


def decode_body(payload):
    """Recursively extract and decode message body text from the payload."""
    parts_to_check = []
    if "parts" in payload:
        for part in payload["parts"]:
            parts_to_check.append(part)
    else:
        parts_to_check.append(payload)

    text = ""
    for part in parts_to_check:
        mime = part.get("mimeType", "")
        if "parts" in part:
            text += decode_body(part)
        elif mime in ("text/plain", "text/html"):
            data = part.get("body", {}).get("data", "")
            if data:
                try:
                    text += base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                except Exception:
                    pass
    return text


def score_message(msg_info):
    """Score a message on phishing likelihood. Returns (score, reasons)."""
    score = 0
    reasons = []

    sender = msg_info["from"].lower()
    subject = msg_info["subject"].lower()
    reply_to = msg_info["reply_to"].lower()
    return_path = msg_info["return_path"].lower()
    body = msg_info["body_text"].lower()
    urls = msg_info["urls"]

    # Sender domain mismatch with reply-to
    if reply_to and reply_to != sender:
        sender_domain = sender.split("@")[-1] if "@" in sender else ""
        reply_domain = reply_to.split("@")[-1] if "@" in reply_to else ""
        if sender_domain and reply_domain and sender_domain != reply_domain:
            score += 3
            reasons.append(f"Reply-To domain mismatch: {reply_to}")

    # Return-Path mismatch
    if return_path and "@" in return_path and "@" in sender:
        rp_domain = return_path.split("@")[-1].rstrip(">")
        s_domain = sender.split("@")[-1].rstrip(">")
        if rp_domain != s_domain:
            score += 2
            reasons.append(f"Return-Path domain mismatch: {return_path}")

    # Sender keyword matches
    for kw in SUSPICIOUS_SENDER_KEYWORDS:
        if kw in sender:
            score += 1
            reasons.append(f"Sender contains '{kw}'")
            break

    # Subject keyword matches
    for kw in SUSPICIOUS_SUBJECT_KEYWORDS:
        if kw in subject:
            score += 2
            reasons.append(f"Subject contains '{kw}'")
            break

    # OAuth / consent URLs
    for url in urls:
        for pattern in OAUTH_URL_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                score += 5
                reasons.append(f"OAuth/consent URL: {url[:120]}")
                break

    # Suspicious hosting / shortener URLs
    for url in urls:
        for pattern in SUSPICIOUS_URL_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                score += 3
                reasons.append(f"Suspicious URL: {url[:120]}")
                break

    # Urgency language in body
    urgency_phrases = [
        "your account will be", "immediate action", "click here to verify",
        "confirm your identity", "unauthorized access", "suspicious activity",
        "your account has been", "within 24 hours", "will be suspended",
        "will be locked", "review your activity", "unusual activity",
        "sign-in attempt", "verify your account", "action required",
    ]
    for phrase in urgency_phrases:
        if phrase in body:
            score += 2
            reasons.append(f"Urgency phrase: '{phrase}'")
            break

    # External sender (not from the org domain)
    if "@yourdomain.com" not in sender:
        score += 1
        reasons.append("External sender")

    # HTML with hidden or mismatched links (href != display text)
    if msg_info["has_html"]:
        # Look for <a href="X">Y</a> where X and display text differ significantly
        href_mismatches = re.findall(
            r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
            msg_info["body_text"], re.IGNORECASE,
        )
        for href, display in href_mismatches:
            display_clean = display.strip().lower()
            if display_clean.startswith("http") and href.lower()[:30] != display_clean[:30]:
                score += 3
                reasons.append(f"Mismatched link: displays '{display_clean[:60]}' but links to '{href[:60]}'")
                break

    return score, reasons


def pull_messages(email, after_date, before_date):
    """Pull messages from a user's mailbox in the given date range.

    Returns a list of scored message dicts, sorted by score descending.
    """
    service = get_gmail_service(email)
    query = f"after:{after_date} before:{before_date}"

    print(f"  Querying: {query}")

    # Collect message IDs
    raw_ids = []
    page_token = None
    while True:
        result = rate_limited_execute(
            service.users().messages().list(
                userId="me", q=query, maxResults=500, pageToken=page_token,
            )
        )
        raw_ids.extend(result.get("messages", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    print(f"  Found {len(raw_ids)} messages in range. Fetching details...")

    messages = []
    for i, entry in enumerate(raw_ids, 1):
        if i % 25 == 0 or i == len(raw_ids):
            print(f"\r  Fetching: {i}/{len(raw_ids)}", end="", flush=True)

        msg = rate_limited_execute(
            service.users().messages().get(
                userId="me", id=entry["id"], format="full",
            )
        )

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        payload = msg.get("payload", {})
        body_text = decode_body(payload)
        has_html = "text/html" in str(payload)
        urls = extract_urls(body_text)
        label_ids = msg.get("labelIds", [])

        msg_info = {
            "gmail_id": entry["id"],
            "thread_id": entry.get("threadId", ""),
            "date": headers.get("Date", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "reply_to": headers.get("Reply-To", ""),
            "return_path": headers.get("Return-Path", ""),
            "message_id": headers.get("Message-ID", ""),
            "auth_results": headers.get("Authentication-Results", "")[:300],
            "urls": urls,
            "url_count": len(urls),
            "has_html": has_html,
            "body_text": body_text,
            "labels": ", ".join(label_ids),
            "in_inbox": "INBOX" in label_ids,
        }

        phish_score, reasons = score_message(msg_info)
        msg_info["phish_score"] = phish_score
        msg_info["reasons"] = "; ".join(reasons)

        messages.append(msg_info)

    print()

    # Sort by phish score descending
    messages.sort(key=lambda m: m["phish_score"], reverse=True)
    return messages


def display_results(messages, top_n=20):
    """Print the top scored messages."""
    showing = messages[:top_n]
    print(f"\n{'='*80}")
    print(f"  TOP {len(showing)} MESSAGES BY PHISHING SCORE")
    print(f"{'='*80}\n")

    for i, msg in enumerate(showing, 1):
        score_bar = "#" * min(msg["phish_score"], 20)
        print(f"  [{i:>2}] Score: {msg['phish_score']:>3}  {score_bar}")
        print(f"       Date:    {msg['date']}")
        print(f"       From:    {msg['from']}")
        print(f"       Subject: {msg['subject']}")
        if msg["reply_to"]:
            print(f"       Reply-To: {msg['reply_to']}")
        print(f"       URLs:    {msg['url_count']}  |  Labels: {msg['labels']}")
        print(f"       Reasons: {msg['reasons']}")
        if msg["urls"]:
            for url in msg["urls"][:3]:
                print(f"         -> {url[:120]}")
        print(f"       Gmail ID: {msg['gmail_id']}")
        print()


def export_results(messages, email):
    """Export scored results to CSV."""
    rows = []
    for msg in messages:
        rows.append({
            "phish_score": msg["phish_score"],
            "date": msg["date"],
            "from": msg["from"],
            "subject": msg["subject"],
            "reply_to": msg["reply_to"],
            "return_path": msg["return_path"],
            "url_count": msg["url_count"],
            "urls": " | ".join(msg["urls"][:10]),
            "reasons": msg["reasons"],
            "labels": msg["labels"],
            "gmail_id": msg["gmail_id"],
            "thread_id": msg["thread_id"],
            "message_id": msg["message_id"],
            "auth_results": msg["auth_results"],
        })
    ask_export(rows, f"phishing_investigation_{email.replace('@', '_at_')}.csv")


def investigate():
    """Run a phishing investigation on a single user."""
    email = input("Enter email address to investigate: ").strip()
    if not email:
        print("No email provided.")
        return

    print("\nBased on the OAuth logs, key dates to investigate:")
    print("  - 2026-03-31: Suspicious login from California (198.51.100.23)")
    print("  - Example: OAuth phishing attempt blocked (add incident notes here)")
    print("\nEnter a date range to search (format: YYYY/MM/DD)")

    after = input("  After date [2026/03/28]: ").strip() or "2026/03/28"
    before = input("  Before date [2026/04/03]: ").strip() or "2026/04/03"

    print(f"\nInvestigating {email} from {after} to {before}...\n")
    messages = pull_messages(email, after, before)

    if not messages:
        print("No messages found in that range.")
        return

    display_results(messages)
    export_results(messages, email)


def investigate_url():
    """Search a user's mailbox for messages containing a specific URL or domain."""
    email = input("Enter email address: ").strip()
    if not email:
        print("No email provided.")
        return

    target = input("Enter URL or domain to search for: ").strip()
    if not target:
        print("No URL provided.")
        return

    service = get_gmail_service(email)
    query = f"rfc822msgid:{target}" if "@" in target else target
    # Use a broad search for the URL/domain in the body
    query = f'"{target}"'

    print(f"\nSearching {email} for: {target}")
    raw_ids = []
    page_token = None
    while True:
        result = rate_limited_execute(
            service.users().messages().list(
                userId="me", q=query, maxResults=100, pageToken=page_token,
            )
        )
        raw_ids.extend(result.get("messages", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    print(f"Found {len(raw_ids)} message(s) containing '{target}'.\n")

    for entry in raw_ids[:20]:
        msg = rate_limited_execute(
            service.users().messages().get(
                userId="me", id=entry["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
        )
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        print(f"  {headers.get('Date', '?')}")
        print(f"    From:    {headers.get('From', '?')}")
        print(f"    Subject: {headers.get('Subject', '?')}")
        print(f"    ID:      {entry['id']}")
        print()


def view_message():
    """View full details of a specific message by Gmail ID."""
    email = input("Enter email address: ").strip()
    if not email:
        print("No email provided.")
        return

    msg_id = input("Enter Gmail message ID: ").strip()
    if not msg_id:
        print("No message ID provided.")
        return

    service = get_gmail_service(email)
    msg = rate_limited_execute(
        service.users().messages().get(userId="me", id=msg_id, format="full")
    )

    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    body = decode_body(msg.get("payload", {}))
    urls = extract_urls(body)

    print(f"\n{'='*80}")
    print(f"  MESSAGE DETAILS")
    print(f"{'='*80}")
    print(f"  Date:           {headers.get('Date', '')}")
    print(f"  From:           {headers.get('From', '')}")
    print(f"  To:             {headers.get('To', '')}")
    print(f"  Reply-To:       {headers.get('Reply-To', '')}")
    print(f"  Return-Path:    {headers.get('Return-Path', '')}")
    print(f"  Subject:        {headers.get('Subject', '')}")
    print(f"  Message-ID:     {headers.get('Message-ID', '')}")
    print(f"  Auth-Results:   {headers.get('Authentication-Results', '')[:500]}")
    print(f"  Labels:         {', '.join(msg.get('labelIds', []))}")
    print(f"\n  URLs found ({len(urls)}):")
    for url in urls:
        print(f"    {url[:150]}")

    print(f"\n{'─'*80}")
    print(f"  BODY PREVIEW (first 3000 chars):")
    print(f"{'─'*80}")
    # Strip HTML tags for readability
    clean = re.sub(r'<[^>]+>', ' ', body)
    clean = re.sub(r'\s+', ' ', clean).strip()
    print(f"  {clean[:3000]}")
    print()


def main():
    while True:
        choice = pick("Phishing Investigation", [
            "Investigate mailbox (score messages in date range)",
            "Search for URL/domain in mailbox",
            "View full message by ID",
            "Exit",
        ])
        if choice == 1:
            investigate()
            pause()
        elif choice == 2:
            investigate_url()
            pause()
        elif choice == 3:
            view_message()
            pause()
        else:
            return


if __name__ == "__main__":
    main()
