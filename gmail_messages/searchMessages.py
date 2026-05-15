"""Search Gmail messages by subject line and return message IDs."""
import csv
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_gmail_service, get_service, paginate_users, ask_export, pick, pause, rate_limited_execute, OUTPUT_DIR


def search_by_subject(email, subject):
    """Search a single user's mailbox for messages matching a subject line.

    Returns a list of dicts with gmail_id, thread_id, rfc822_message_id, and subject.
    """
    service = get_gmail_service(email)
    query = f"subject:({subject})"
    raw_ids = []
    page_token = None

    while True:
        result = rate_limited_execute(
            service.users().messages().list(
                userId="me", q=query, maxResults=500, pageToken=page_token
            )
        )
        raw_ids.extend(result.get("messages", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    messages = []
    for entry in raw_ids:
        msg = rate_limited_execute(
            service.users().messages().get(
                userId="me", id=entry["id"], format="metadata",
                metadataHeaders=["Message-ID", "Subject"],
            )
        )
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        messages.append({
            "gmail_id": entry["id"],
            "thread_id": entry.get("threadId", ""),
            "rfc822_message_id": headers.get("Message-ID", ""),
            "subject": headers.get("Subject", ""),
        })

    return messages


def search_single_user():
    """Search one user's mailbox by subject."""
    email = input("Enter email address: ").strip()
    if not email:
        print("No email provided.")
        return

    subject = input("Enter subject line to search: ").strip()
    if not subject:
        print("No subject provided.")
        return

    print(f"\nSearching {email} for subject: {subject}")
    messages = search_by_subject(email, subject)

    if not messages:
        print("No messages found.")
        return

    print(f"\nFound {len(messages)} message(s):\n")
    rows = []
    for msg in messages:
        print(f"  RFC822 Message-ID: {msg['rfc822_message_id']}")
        print(f"    Subject: {msg['subject']}")
        print(f"    Gmail ID: {msg['gmail_id']}  |  Thread ID: {msg['thread_id']}")
        print()
        rows.append({"email": email, **msg})

    ask_export(rows, f"messages_{email.replace('@', '_at_')}.csv")


def search_all_users():
    """Search all active users' mailboxes by subject."""
    subject = input("Enter subject line to search: ").strip()
    if not subject:
        print("No subject provided.")
        return

    print("\nFetching user list...")
    service = get_service()
    users = paginate_users(service)
    print(f"Searching {len(users)} users for subject: {subject}\n")

    all_rows = []
    for i, user in enumerate(users, 1):
        email = user["primaryEmail"]
        print(f"\r  Progress: {i}/{len(users)} — {email}", end="", flush=True)
        try:
            messages = search_by_subject(email, subject)
        except Exception as e:
            print(f"\n  Error searching {email}: {e}")
            continue
        for msg in messages:
            all_rows.append({"email": email, **msg})

    print(f"\n\nFound {len(all_rows)} message(s) across all users.")

    if not all_rows:
        return

    for row in all_rows:
        print(f"  {row['email']}  |  RFC822: {row['rfc822_message_id']}  |  Gmail ID: {row['gmail_id']}")

    ask_export(all_rows, "messages_all_users.csv")


def main():
    while True:
        choice = pick("Search Messages by Subject", [
            "Search single user",
            "Search all users",
            "Exit",
        ])
        if choice == 1:
            search_single_user()
            pause()
        elif choice == 2:
            search_all_users()
            pause()
        else:
            return


if __name__ == "__main__":
    main()
