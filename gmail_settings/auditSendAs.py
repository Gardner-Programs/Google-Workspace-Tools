"""Audit all users' sendAs settings for anomalies.

Flags any user whose sendAs aliases don't match their profile:
  - replyToAddress set to a different address
  - Non-primary sendAs aliases (can send as someone else)
  - displayName on primary alias differs from directory name
Outputs all findings to CSV.
"""
import csv
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import (
    get_gmail_service, get_service, get_members, paginate_users,
    rate_limited_execute, pause, OUTPUT_DIR, DOMAIN,
)


def _is_internal(email):
    return email.lower().endswith(f"@{DOMAIN.lower()}")

AUDIT_WORKERS = 10


def audit_user_sendas(email, display_name):
    """Check a single user's sendAs settings for anything non-default.

    Returns a list of finding dicts.
    """
    findings = []
    service = get_gmail_service(email)

    try:
        send_as = rate_limited_execute(
            service.users().settings().sendAs().list(userId="me")
        )
    except Exception as e:
        return [{"user": email, "directory_name": display_name,
                 "type": "error", "sendas_email": "", "display_name": "",
                 "reply_to": "", "is_primary": "", "detail": str(e)}]

    for alias in send_as.get("sendAs", []):
        sendas_email = alias.get("sendAsEmail", "")
        sendas_display = alias.get("displayName", "")
        reply_to = alias.get("replyToAddress", "")
        is_primary = alias.get("isPrimary", False)

        issues = []

        if is_primary:
            # Flag if reply-to is set to anything
            if reply_to:
                issues.append(f"replyTo set to {reply_to}")

            # Flag if display name doesn't match directory
            if sendas_display and display_name and sendas_display != display_name:
                issues.append(f"displayName '{sendas_display}' differs from directory '{display_name}'")
        else:
            # Any non-primary alias is suspicious
            issues.append(f"Non-primary sendAs alias: {sendas_email}")
            if reply_to:
                issues.append(f"replyTo set to {reply_to}")

        if issues:
            findings.append({
                "user": email,
                "directory_name": display_name,
                "type": "primary" if is_primary else "alias",
                "sendas_email": sendas_email,
                "display_name": sendas_display,
                "reply_to": reply_to,
                "is_primary": str(is_primary),
                "detail": "; ".join(issues),
            })

    return findings


def audit_all():
    """Scan all active users for sendAs anomalies."""
    print("\nFetching user list...")
    service = get_service()
    users = paginate_users(service)
    print(f"Scanning {len(users)} users...\n")

    # Build a map of email -> directory display name
    user_map = {}
    for u in users:
        full_name = u.get("name", {})
        name = f"{full_name.get('givenName', '')} {full_name.get('familyName', '')}".strip()
        user_map[u["primaryEmail"]] = name

    all_findings = []
    lock = threading.Lock()
    counter = [0]

    def _worker(email):
        findings = audit_user_sendas(email, user_map.get(email, ""))
        with lock:
            counter[0] += 1
            print(f"\r  Progress: {counter[0]}/{len(users)} — {email}", end="", flush=True)
        return findings

    with ThreadPoolExecutor(max_workers=AUDIT_WORKERS) as pool:
        futures = [pool.submit(_worker, e) for e in user_map]
        for future in as_completed(futures):
            results = future.result()
            if results:
                all_findings.extend(results)
                with lock:
                    for r in results:
                        if r["type"] != "error":
                            print(f"\n  *** {r['user']}: {r['detail']}")

    matches = [f for f in all_findings if f["type"] != "error"]
    errors = [f for f in all_findings if f["type"] == "error"]

    print(f"\n\nScan complete. {len(matches)} finding(s) across all users.")
    if errors:
        print(f"{len(errors)} error(s) encountered.")

    if not matches:
        return

    # Write CSV
    filename = "audit_sendas.csv"
    filepath = os.path.join(OUTPUT_DIR, filename)
    fieldnames = ["user", "directory_name", "type", "sendas_email",
                  "display_name", "reply_to", "is_primary", "detail"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matches)
    print(f"Results saved to {filepath}")


def audit_group(group_email):
    """Scan sendAs for all internal members of a group."""
    service = get_service()
    members = get_members(service, group_email)
    if members is None:
        return

    all_emails = [m["email"] for m in members if m.get("type") == "USER" and m.get("email")]
    emails = [e for e in all_emails if _is_internal(e)]
    external = [e for e in all_emails if not _is_internal(e)]

    if external:
        print(f"\nSkipping {len(external)} external member(s):")
        for e in sorted(external):
            print(f"  {e}")
    if not emails:
        print(f"\nNo internal members in {group_email} to check.")
        return

    # Resolve directory names for the group members
    user_map = {}
    for e in emails:
        try:
            u = rate_limited_execute(service.users().get(userKey=e))
            name = u.get("name", {})
            user_map[e] = f"{name.get('givenName', '')} {name.get('familyName', '')}".strip()
        except Exception:
            user_map[e] = ""

    print(f"\nScanning {len(emails)} internal member(s) of {group_email}...\n")
    all_findings = []
    lock = threading.Lock()
    counter = [0]

    def _worker(email):
        findings = audit_user_sendas(email, user_map.get(email, ""))
        with lock:
            counter[0] += 1
            print(f"\r  Progress: {counter[0]}/{len(emails)} — {email}", end="", flush=True)
        return findings

    with ThreadPoolExecutor(max_workers=AUDIT_WORKERS) as pool:
        futures = [pool.submit(_worker, e) for e in emails]
        for future in as_completed(futures):
            results = future.result()
            if results:
                all_findings.extend(results)
                with lock:
                    for r in results:
                        if r["type"] != "error":
                            print(f"\n  *** {r['user']}: {r['detail']}")

    matches = [f for f in all_findings if f["type"] != "error"]
    errors = [f for f in all_findings if f["type"] == "error"]

    print(f"\n\nScan complete. {len(matches)} finding(s) across {len(emails)} member(s).")
    if errors:
        print(f"{len(errors)} error(s) encountered.")

    if not matches:
        return

    safe_group = group_email.replace("@", "_at_").replace(".", "_")
    filename = f"audit_sendas_group_{safe_group}.csv"
    filepath = os.path.join(OUTPUT_DIR, filename)
    fieldnames = ["user", "directory_name", "type", "sendas_email",
                  "display_name", "reply_to", "is_primary", "detail"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matches)
    print(f"Results saved to {filepath}")


def audit_single():
    """Scan a single user's sendAs settings."""
    email = input("Enter email address: ").strip()
    if not email:
        print("No email provided.")
        return

    # Get their directory name
    service = get_service()
    try:
        user = service.users().get(userKey=email).execute()
        full_name = user.get("name", {})
        display_name = f"{full_name.get('givenName', '')} {full_name.get('familyName', '')}".strip()
    except Exception:
        display_name = ""

    print(f"\nScanning {email} (directory name: {display_name or 'unknown'})...\n")
    findings = audit_user_sendas(email, display_name)

    matches = [f for f in findings if f["type"] != "error"]
    errors = [f for f in findings if f["type"] == "error"]

    if not matches:
        print("  No anomalies — sendAs settings match profile defaults.")
    else:
        for f in matches:
            print(f"  [{f['type']}] {f['sendas_email']}")
            print(f"    {f['detail']}")
            if f['reply_to']:
                print(f"    replyTo: {f['reply_to']}")
            print()

    if errors:
        for e in errors:
            print(f"  Error: {e['detail']}")


def main():
    from _master import pick
    while True:
        choice = pick("Audit SendAs Settings", [
            "Scan single user",
            "Scan group (all members)",
            "Scan all users",
            "Exit",
        ])
        if choice == 1:
            audit_single()
            pause()
        elif choice == 2:
            group_email = input("Enter group email: ").strip()
            if group_email:
                audit_group(group_email)
            pause()
        elif choice == 3:
            audit_all()
            pause()
        else:
            return


if __name__ == "__main__":
    main()
