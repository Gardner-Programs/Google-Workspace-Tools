"""Audit all users' filters and forwarding rules for a specific address.

Scans every active user for:
  - Auto-forwarding enabled to the target address
  - Filters that forward to or match the target address
  - Forwarding addresses that include the target
Outputs all matches to CSV for investigation.
"""
import csv
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import (
    get_gmail_service, get_service, paginate_users,
    rate_limited_execute, pick, pause, OUTPUT_DIR,
)

AUDIT_WORKERS = 10


def audit_user(email, target):
    """Check a single user's forwarding and filters for the target address.

    Returns a list of finding dicts.
    """
    target_lower = target.lower()
    findings = []
    service = get_gmail_service(email)

    # 1. Check auto-forwarding
    try:
        fwd = rate_limited_execute(
            service.users().settings().getAutoForwarding(userId="me")
        )
        if fwd.get("enabled"):
            fwd_addr = fwd.get("emailAddress", "")
            if target_lower in fwd_addr.lower():
                findings.append({
                    "user": email,
                    "type": "auto-forwarding",
                    "detail": f"Forwarding to {fwd_addr}",
                    "disposition": fwd.get("disposition", ""),
                    "filter_id": "",
                    "criteria": "",
                    "actions": "",
                })
    except Exception as e:
        findings.append({
            "user": email, "type": "error", "detail": f"auto-forwarding: {e}",
            "disposition": "", "filter_id": "", "criteria": "", "actions": "",
        })

    # 2. Check forwarding addresses (registered, even if not active)
    try:
        addrs = rate_limited_execute(
            service.users().settings().forwardingAddresses().list(userId="me")
        )
        for addr in addrs.get("forwardingAddresses", []):
            fwd_email = addr.get("forwardingEmail", "")
            if target_lower in fwd_email.lower():
                findings.append({
                    "user": email,
                    "type": "forwarding-address",
                    "detail": f"{fwd_email} (status: {addr.get('verificationStatus', 'unknown')})",
                    "disposition": "",
                    "filter_id": "",
                    "criteria": "",
                    "actions": "",
                })
    except Exception as e:
        findings.append({
            "user": email, "type": "error", "detail": f"forwarding-addresses: {e}",
            "disposition": "", "filter_id": "", "criteria": "", "actions": "",
        })

    # 3. Check sendAs / reply-to addresses
    try:
        send_as = rate_limited_execute(
            service.users().settings().sendAs().list(userId="me")
        )
        for alias in send_as.get("sendAs", []):
            reply_to = alias.get("replyToAddress", "")
            send_as_email = alias.get("sendAsEmail", "")
            if reply_to and target_lower in reply_to.lower():
                findings.append({
                    "user": email,
                    "type": "reply-to",
                    "detail": f"sendAs '{send_as_email}' has replyTo: {reply_to}",
                    "disposition": "",
                    "filter_id": "",
                    "criteria": "",
                    "actions": "",
                })
            if send_as_email and target_lower in send_as_email.lower() and send_as_email.lower() != email.lower():
                findings.append({
                    "user": email,
                    "type": "send-as alias",
                    "detail": f"Can send as: {send_as_email}",
                    "disposition": "",
                    "filter_id": "",
                    "criteria": "",
                    "actions": "",
                })
    except Exception as e:
        findings.append({
            "user": email, "type": "error", "detail": f"sendAs: {e}",
            "disposition": "", "filter_id": "", "criteria": "", "actions": "",
        })

    # 4. Check filters
    try:
        result = rate_limited_execute(
            service.users().settings().filters().list(userId="me")
        )
        for f in result.get("filter", []):
            f_id = f.get("id", "")
            criteria = f.get("criteria", {})
            action = f.get("action", {})

            # Check if target appears in filter criteria
            criteria_match = any(
                target_lower in str(v).lower()
                for v in criteria.values()
            )

            # Check if filter forwards to target
            forward_match = target_lower in action.get("forward", "").lower()

            if criteria_match or forward_match:
                criteria_str = "; ".join(f"{k}={v}" for k, v in criteria.items())
                action_parts = []
                for k, v in action.items():
                    action_parts.append(f"{k}={v}")
                actions_str = "; ".join(action_parts)

                match_type = []
                if criteria_match:
                    match_type.append("criteria")
                if forward_match:
                    match_type.append("forward")

                findings.append({
                    "user": email,
                    "type": f"filter ({', '.join(match_type)})",
                    "detail": f"Filter forwards/matches target",
                    "disposition": "",
                    "filter_id": f_id,
                    "criteria": criteria_str,
                    "actions": actions_str,
                })
    except Exception as e:
        findings.append({
            "user": email, "type": "error", "detail": f"filters: {e}",
            "disposition": "", "filter_id": "", "criteria": "", "actions": "",
        })

    return findings


def audit_all_users(target):
    """Scan all active users for the target address in forwarding/filters."""
    print(f"\nSearching for: {target}")
    print("Fetching user list...")
    service = get_service()
    users = paginate_users(service)
    emails = [u["primaryEmail"] for u in users]
    print(f"Scanning {len(emails)} users...\n")

    all_findings = []
    lock = threading.Lock()
    counter = [0]

    def _worker(email):
        findings = audit_user(email, target)
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
                            print(f"\n  *** {r['user']}: {r['type']} — {r['detail']}")

    # Separate real findings from errors
    matches = [f for f in all_findings if f["type"] != "error"]
    errors = [f for f in all_findings if f["type"] == "error"]

    print(f"\n\nScan complete. {len(matches)} match(es) found.")
    if errors:
        print(f"{len(errors)} error(s) encountered.")

    if not matches:
        return

    # Write CSV
    safe_target = target.replace("@", "_at_").replace(".", "_")
    filename = f"audit_forwarding_{safe_target}.csv"
    filepath = os.path.join(OUTPUT_DIR, filename)
    fieldnames = ["user", "type", "detail", "disposition", "filter_id", "criteria", "actions"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matches)
    print(f"Results saved to {filepath}")


def audit_single_user(target):
    """Scan a single user for the target address."""
    email = input("Enter email address: ").strip()
    if not email:
        print("No email provided.")
        return

    print(f"\nSearching {email} for: {target}\n")
    findings = audit_user(email, target)

    matches = [f for f in findings if f["type"] != "error"]
    errors = [f for f in findings if f["type"] == "error"]

    if not matches:
        print("No matches found.")
    else:
        for f in matches:
            print(f"  {f['type']}: {f['detail']}")
            if f["filter_id"]:
                print(f"    Filter ID: {f['filter_id']}")
                print(f"    Criteria: {f['criteria']}")
                print(f"    Actions: {f['actions']}")

    if errors:
        print(f"\n{len(errors)} error(s):")
        for e in errors:
            print(f"  {e['detail']}")


def main():
    target = input("Enter address to search for: ").strip()
    if not target:
        print("No address provided.")
        return

    while True:
        choice = pick(f"Audit Forwarding/Filters for '{target}'", [
            "Scan single user",
            "Scan all users",
            "Change target address",
            "Exit",
        ])
        if choice == 1:
            audit_single_user(target)
            pause()
        elif choice == 2:
            audit_all_users(target)
            pause()
        elif choice == 3:
            target = input("Enter new address to search for: ").strip()
            if not target:
                print("No address provided.")
                return
        else:
            return


if __name__ == "__main__":
    main()
