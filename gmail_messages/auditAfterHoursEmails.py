"""Audit a user's after-hours email activity within a given timeframe.

Lists messages sent/received outside configured business hours and weekends.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import ask_export, get_gmail_service, pause, pick, rate_limited_execute

DEFAULT_TZ = "America/New_York"
DEFAULT_START_HOUR = 8
DEFAULT_END_HOUR = 17


def prompt_date(label):
    while True:
        raw = input(f"{label} (YYYY-MM-DD): ").strip()
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("  Invalid format. Use YYYY-MM-DD.")


def prompt_int(label, default):
    raw = input(f"{label} [{default}]: ").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"  Invalid integer, using {default}.")
        return default


def prompt_timezone():
    raw = input(f"Timezone [{DEFAULT_TZ}]: ").strip() or DEFAULT_TZ
    try:
        return ZoneInfo(raw)
    except ZoneInfoNotFoundError:
        print(f"  Unknown timezone, falling back to {DEFAULT_TZ}.")
        return ZoneInfo(DEFAULT_TZ)


def is_after_hours(dt, start_hour, end_hour, include_weekends):
    if include_weekends and dt.weekday() >= 5:
        return True
    return dt.hour < start_hour or dt.hour >= end_hour


def list_message_ids(service, query):
    ids = []
    page_token = None
    while True:
        result = rate_limited_execute(
            service.users().messages().list(
                userId="me", q=query, maxResults=500, pageToken=page_token
            )
        )
        ids.extend(result.get("messages", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return ids


def fetch_metadata(service, gmail_id):
    msg = rate_limited_execute(
        service.users().messages().get(
            userId="me",
            id=gmail_id,
            format="metadata",
            metadataHeaders=["Subject", "From", "To"],
        )
    )
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "internal_date_ms": int(msg.get("internalDate", 0)),
        "subject": headers.get("Subject", ""),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
    }


def audit(email, start_date, end_date, direction, start_hour, end_hour, tz, include_weekends):
    service = get_gmail_service(email)
    after = start_date.strftime("%Y/%m/%d")
    before = (end_date).strftime("%Y/%m/%d")
    scope = {"sent": "in:sent", "received": "in:inbox", "both": "(in:sent OR in:inbox)"}[direction]
    query = f"{scope} after:{after} before:{before}"

    print(f"\nQuery: {query}")
    print("Listing messages...")
    ids = list_message_ids(service, query)
    print(f"Found {len(ids)} messages in range. Inspecting timestamps...")

    all_rows = []
    for i, entry in enumerate(ids, 1):
        print(f"\r  Progress: {i}/{len(ids)}", end="", flush=True)
        try:
            meta = fetch_metadata(service, entry["id"])
        except Exception as e:
            print(f"\n  Error fetching {entry['id']}: {e}")
            continue
        local_dt = datetime.fromtimestamp(meta["internal_date_ms"] / 1000, tz=tz)
        after_hours = is_after_hours(local_dt, start_hour, end_hour, include_weekends)
        all_rows.append({
            "gmail_id": entry["id"],
            "thread_id": entry.get("threadId", ""),
            "timestamp_local": local_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "weekday": local_dt.strftime("%A"),
            "after_hours": after_hours,
            "from": meta["from"],
            "to": meta["to"],
            "subject": meta["subject"],
        })
    print()
    after_hours_rows = [r for r in all_rows if r["after_hours"]]
    return all_rows, after_hours_rows


def run_audit():
    email = input("Enter email address: ").strip()
    if not email:
        print("No email provided.")
        return

    start_date = prompt_date("Start date")
    end_date = prompt_date("End date (exclusive)")
    if end_date <= start_date:
        print("End date must be after start date.")
        return

    direction_choice = pick("Message direction", ["Sent only", "Received only", "Both"])
    direction = {1: "sent", 2: "received", 3: "both"}[direction_choice]

    tz = prompt_timezone()
    start_hour = prompt_int("Business hours start (0-23)", DEFAULT_START_HOUR)
    end_hour = prompt_int("Business hours end (0-23)", DEFAULT_END_HOUR)
    weekends_choice = pick("Count weekends as after-hours?", ["Yes", "No"])
    include_weekends = weekends_choice == 1

    all_rows, after_hours_rows = audit(
        email, start_date, end_date, direction, start_hour, end_hour, tz, include_weekends
    )

    if not all_rows:
        print("No messages found in range.")
        return

    print(f"\n{len(all_rows)} total message(s), {len(after_hours_rows)} after-hours:\n")
    for r in after_hours_rows[:50]:
        print(f"  {r['timestamp_local']}  ({r['weekday']})")
        print(f"    From: {r['from']}")
        print(f"    To:   {r['to']}")
        print(f"    Subj: {r['subject']}\n")
    if len(after_hours_rows) > 50:
        print(f"  ... and {len(after_hours_rows) - 50} more (see CSV)")

    base = f"{email.replace('@', '_at_')}_{start_date.isoformat()}_to_{end_date.isoformat()}"
    print("\n-- All messages --")
    ask_export(all_rows, f"all_{base}.csv")
    print("\n-- After-hours only --")
    ask_export(after_hours_rows, f"afterhours_{base}.csv")


def last_work_week(today=None):
    """Return (Monday, Friday) of the most recently completed work week."""
    today = today or date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_friday = last_monday + timedelta(days=4)
    return last_monday, last_friday


def quick_audit_last_week():
    """Audit sent after-hours messages for last Mon-Fri."""
    email = input("Enter email address: ").strip()
    if not email:
        print("No email provided.")
        return

    monday, friday = last_work_week()
    # Gmail `before:` is exclusive — use the day after Friday to include Friday.
    end_date = friday + timedelta(days=1)
    tz = ZoneInfo(DEFAULT_TZ)

    print(f"\nAuditing sent messages for {email}")
    print(f"Window: {monday} (Mon) through {friday} (Fri)")
    print(f"After-hours: outside {DEFAULT_START_HOUR:02d}:00-{DEFAULT_END_HOUR:02d}:00 {DEFAULT_TZ}, weekends excluded from window")

    all_rows, after_hours_rows = audit(
        email=email,
        start_date=monday,
        end_date=end_date,
        direction="sent",
        start_hour=DEFAULT_START_HOUR,
        end_hour=DEFAULT_END_HOUR,
        tz=tz,
        include_weekends=True,
    )

    if not all_rows:
        print("No sent messages found in range.")
        return

    print(f"\n{len(all_rows)} total sent, {len(after_hours_rows)} after-hours:\n")
    for r in after_hours_rows[:50]:
        print(f"  {r['timestamp_local']}  ({r['weekday']})")
        print(f"    To:   {r['to']}")
        print(f"    Subj: {r['subject']}\n")
    if len(after_hours_rows) > 50:
        print(f"  ... and {len(after_hours_rows) - 50} more (see CSV)")

    base = f"sent_{email.replace('@', '_at_')}_{monday.isoformat()}_to_{friday.isoformat()}"
    print("\n-- All sent messages --")
    ask_export(all_rows, f"all_{base}.csv")
    print("\n-- After-hours sent messages --")
    ask_export(after_hours_rows, f"afterhours_{base}.csv")


def main():
    while True:
        choice = pick("After-Hours Email Audit", [
            "Quick: last Mon-Fri, sent only",
            "Custom audit",
            "Exit",
        ])
        if choice == 1:
            quick_audit_last_week()
            pause()
        elif choice == 2:
            run_audit()
            pause()
        else:
            return


if __name__ == "__main__":
    main()
