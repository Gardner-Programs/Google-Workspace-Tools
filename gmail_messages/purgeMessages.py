"""Purge emails from all users' inboxes by sender and/or subject.

Moves matching messages to spam by default, or permanently deletes them.
Uses Gmail batch endpoints and threaded user processing for max throughput.
"""
import csv
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import (
    get_gmail_service, get_service, paginate_users,
    rate_limited_execute, pick, pause, OUTPUT_DIR,
)
from text_utils import build_query
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Gmail per-user rate limit is 250 quota units/sec.
# messages.list = 5 units, batchModify/batchDelete = 50 units.
# 10 concurrent users keeps us well under the domain-wide 2500 units/sec cap.
PURGE_WORKERS = 10
BATCH_SIZE = 1000  # max IDs per batchModify/batchDelete call


def get_matching_ids(email, query):
    """Return list of message IDs matching the query in a user's mailbox."""
    service = get_gmail_service(email)
    ids = []
    page_token = None
    while True:
        result = rate_limited_execute(
            service.users().messages().list(
                userId="me", q=query, maxResults=500, pageToken=page_token
            )
        )
        for msg in result.get("messages", []):
            ids.append(msg["id"])
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return ids


def _chunked(lst, size):
    """Yield successive chunks of lst."""
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def spam_messages(email, message_ids):
    """Move messages to spam using batchModify (up to 1000 per call)."""
    service = get_gmail_service(email)
    for chunk in _chunked(message_ids, BATCH_SIZE):
        rate_limited_execute(
            service.users().messages().batchModify(
                userId="me",
                body={"ids": chunk, "addLabelIds": ["SPAM"], "removeLabelIds": ["INBOX"]},
            )
        )


def delete_messages(email, message_ids):
    """Permanently delete messages using batchDelete (up to 1000 per call)."""
    service = get_gmail_service(email)
    for chunk in _chunked(message_ids, BATCH_SIZE):
        rate_limited_execute(
            service.users().messages().batchDelete(
                userId="me", body={"ids": chunk}
            )
        )


def trash_messages(email, message_ids):
    """Move messages to trash using batchModify (up to 1000 per call)."""
    service = get_gmail_service(email)
    for chunk in _chunked(message_ids, BATCH_SIZE):
        rate_limited_execute(
            service.users().messages().batchModify(
                userId="me",
                body={"ids": chunk, "addLabelIds": ["TRASH"], "removeLabelIds": ["INBOX"]},
            )
        )


def process_user(email, query, action_func):
    """Search and act on messages for a single user. Returns (email, count)."""
    try:
        ids = get_matching_ids(email, query)
        if ids:
            action_func(email, ids)
        return email, len(ids), None
    except Exception as e:
        return email, 0, str(e)


def purge_all_users(sender, subject, message_id, action_func, action_name):
    """Run the purge across all active users."""
    query = build_query(sender, subject, message_id)
    print(f"\nGmail query: {query}")
    print(f"Action: {action_name}\n")

    print("Fetching user list...")
    service = get_service()
    users = paginate_users(service)
    emails = [u["primaryEmail"] for u in users]
    print(f"Found {len(emails)} users.\n")

    confirm = input(f"Proceed to {action_name} matching messages for all {len(emails)} users? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        return

    total_affected = 0
    errors = []
    lock = threading.Lock()
    counter = [0]

    def _worker(email):
        result = process_user(email, query, action_func)
        with lock:
            counter[0] += 1
            print(f"\r  Progress: {counter[0]}/{len(emails)} — {email}", end="", flush=True)
        return result

    with ThreadPoolExecutor(max_workers=PURGE_WORKERS) as pool:
        futures = [pool.submit(_worker, e) for e in emails]
        for future in as_completed(futures):
            email, count, error = future.result()
            if error:
                errors.append((email, error))
            elif count > 0:
                total_affected += count
                with lock:
                    print(f"\n    {email}: {count} message(s)")

    print(f"\n\nDone. {total_affected} total message(s) affected.")
    if errors:
        print(f"\n{len(errors)} error(s):")
        for email, err in errors:
            print(f"  {email}: {err}")


def purge_single_user(sender, subject, message_id, action_func, action_name):
    """Run the purge for a single user."""
    email = input("Enter email address: ").strip()
    if not email:
        print("No email provided.")
        return

    query = build_query(sender, subject, message_id)
    print(f"\nGmail query: {query}")
    print(f"Searching {email}...")

    ids = get_matching_ids(email, query)
    if not ids:
        print("No matching messages found.")
        return

    print(f"Found {len(ids)} message(s).")
    confirm = input(f"{action_name.capitalize()} all {len(ids)} messages? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        return

    action_func(email, ids)
    print(f"Done. {len(ids)} message(s) affected.")


def purge_from_csv(action_func, action_name):
    """Read unique Message IDs from a fraud CSV and purge across all users."""
    default_path = os.path.join(OUTPUT_DIR, "fraud.csv")
    csv_path = input(f"CSV file path [{default_path}]: ").strip() or default_path
    if not os.path.isfile(csv_path):
        print(f"File not found: {csv_path}")
        return

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        senders = set()
        subjects = set()
        for row in reader:
            sender = row.get("From (Header address)", "").strip()
            subject = row.get("Subject", "").strip()
            if sender:
                senders.add(sender)
            if subject:
                subjects.add(subject)

    if not senders and not subjects:
        print("No sender or subject data found in CSV.")
        return

    # Build a single OR query covering all unique senders/subjects from the CSV
    query_parts = []
    if senders:
        sender_query = " OR ".join(f"from:{s}" for s in sorted(senders))
        query_parts.append(f"({sender_query})")
    if subjects:
        subject_query = " OR ".join(f"subject:({s})" for s in sorted(subjects))
        query_parts.append(f"({subject_query})")
    query = " ".join(query_parts)

    print(f"\nUnique senders: {len(senders)}")
    for s in sorted(senders):
        print(f"  {s}")
    print(f"Unique subjects: {len(subjects)}")
    for s in sorted(subjects):
        print(f"  {s}")
    print(f"\nGmail query: {query}")
    print(f"Action: {action_name}\n")

    print("Fetching user list...")
    service = get_service()
    users = paginate_users(service)
    emails = [u["primaryEmail"] for u in users]
    print(f"Found {len(emails)} users.\n")

    confirm = input(
        f"Proceed to {action_name} matching messages "
        f"across {len(emails)} users? (yes/no): "
    ).strip().lower()
    if confirm != "yes":
        print("Aborted.")
        return

    total_affected = 0
    errors = []
    lock = threading.Lock()
    counter = [0]

    def _worker(email):
        try:
            ids = get_matching_ids(email, query)
            if ids:
                action_func(email, ids)
            with lock:
                counter[0] += 1
                print(f"\r  Progress: {counter[0]}/{len(emails)} — {email}", end="", flush=True)
            return email, len(ids), None
        except Exception as e:
            with lock:
                counter[0] += 1
                print(f"\r  Progress: {counter[0]}/{len(emails)} — {email}", end="", flush=True)
            return email, 0, str(e)

    with ThreadPoolExecutor(max_workers=PURGE_WORKERS) as pool:
        futures = [pool.submit(_worker, e) for e in emails]
        for future in as_completed(futures):
            email, count, error = future.result()
            if error:
                errors.append((email, error))
            elif count > 0:
                total_affected += count
                with lock:
                    print(f"\n    {email}: {count} message(s)")

    print(f"\n\nDone. {total_affected} total message(s) affected.")
    if errors:
        print(f"\n{len(errors)} error(s):")
        for email, err in errors:
            print(f"  {email}: {err}")


def get_search_criteria():
    """Prompt for sender, subject, and/or message ID. At least one must be provided."""
    print("\nProvide at least one search criterion.\n")
    message_id = input("RFC822 Message-ID (leave blank to skip): ").strip() or None
    sender = input("Sender email/name (leave blank to skip): ").strip() or None
    subject = input("Subject line (leave blank to skip): ").strip() or None
    if not sender and not subject and not message_id:
        print("You must provide at least one criterion.")
        return None, None, None
    return sender, subject, message_id


def main():
    while True:
        choice = pick("Purge Messages from Inboxes", [
            "Move to spam — single user",
            "Move to spam — all users",
            "Move to trash — single user",
            "Move to trash — all users",
            "Permanently delete — single user",
            "Permanently delete — all users",
            "Fraud CSV — move to spam (all users)",
            "Fraud CSV — move to trash (all users)",
            "Fraud CSV — permanently delete (all users)",
            "Exit",
        ])
        if choice == 10:
            return

        # CSV-based options
        if choice in (7, 8, 9):
            csv_actions = {
                7: (spam_messages, "move to spam"),
                8: (trash_messages, "move to trash"),
                9: (delete_messages, "permanently delete"),
            }
            action_func, action_name = csv_actions[choice]
            purge_from_csv(action_func, action_name)
            pause()
            continue

        sender, subject, message_id = get_search_criteria()
        if not sender and not subject and not message_id:
            pause()
            continue

        actions = {
            1: (purge_single_user, spam_messages, "move to spam"),
            2: (purge_all_users, spam_messages, "move to spam"),
            3: (purge_single_user, trash_messages, "move to trash"),
            4: (purge_all_users, trash_messages, "move to trash"),
            5: (purge_single_user, delete_messages, "permanently delete"),
            6: (purge_all_users, delete_messages, "permanently delete"),
        }

        run_func, action_func, action_name = actions[choice]
        run_func(sender, subject, message_id, action_func, action_name)
        pause()


if __name__ == "__main__":
    main()
