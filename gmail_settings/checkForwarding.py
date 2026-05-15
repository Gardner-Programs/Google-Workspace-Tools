"""Check, enable/disable, or add a Gmail forwarding address.

Supports checking forwarding + forwarding filters for a single user
or every member of a group.
"""
import csv
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import (
    get_gmail_service, get_service, get_members,
    rate_limited_execute, pick, pause, MAX_WORKERS, DOMAIN, OUTPUT_DIR,
)

CSV_FIELDS = [
    "user", "source", "target", "disposition",
    "filter_id", "criteria",
]


def _is_internal(email):
    return email.lower().endswith(f"@{DOMAIN.lower()}")


def _get_forwarding(email):
    service = get_gmail_service(email)
    fwd = rate_limited_execute(
        service.users().settings().getAutoForwarding(userId="me")
    )
    filters_resp = rate_limited_execute(
        service.users().settings().filters().list(userId="me")
    )
    forwarding_filters = [
        f for f in filters_resp.get("filter", [])
        if f.get("action", {}).get("forward")
    ]
    return fwd, forwarding_filters


def _forwarding_to_rows(email, fwd, forwarding_filters):
    """Return one CSV row per forwarding source (auto + each filter)."""
    rows = []
    if fwd.get("enabled"):
        rows.append({
            "user": email,
            "source": "auto-forwarding",
            "target": fwd.get("emailAddress", ""),
            "disposition": fwd.get("disposition", ""),
            "filter_id": "",
            "criteria": "",
        })
    for f in forwarding_filters:
        criteria = "; ".join(f"{k}={v}" for k, v in f.get("criteria", {}).items())
        rows.append({
            "user": email,
            "source": "filter",
            "target": f.get("action", {}).get("forward", ""),
            "disposition": "",
            "filter_id": f.get("id", ""),
            "criteria": criteria,
        })
    return rows


def _print_user_forwarding(email, fwd, forwarding_filters):
    enabled = fwd.get("enabled", False)
    print(f"\n{email}")
    print(f"  Auto-forwarding enabled: {enabled}")
    if enabled or fwd.get("emailAddress"):
        print(f"  Auto-forwarding email:   {fwd.get('emailAddress', 'N/A')}")
        print(f"  Disposition:             {fwd.get('disposition', 'N/A')}")
    if forwarding_filters:
        print(f"  Forwarding filters ({len(forwarding_filters)}):")
        for f in forwarding_filters:
            criteria = "; ".join(f"{k}={v}" for k, v in f.get("criteria", {}).items())
            print(f"    - id={f.get('id', '')} forward={f['action']['forward']}")
            if criteria:
                print(f"      criteria: {criteria}")
    else:
        print("  Forwarding filters:      none")


def _write_csv(rows, filename):
    if not rows:
        return
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, filename)
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved to {csv_path}")


def check_forwarding(email):
    if not _is_internal(email):
        print(f"Skipping {email}: external account (not in {DOMAIN}).")
        return
    try:
        fwd, forwarding_filters = _get_forwarding(email)
    except Exception as exc:
        print(f"Error checking {email}: {exc}")
        return
    _print_user_forwarding(email, fwd, forwarding_filters)


def check_group_forwarding(group_email):
    service = get_service()
    members = get_members(service, group_email)
    if members is None:
        return
    all_emails = [m["email"] for m in members if m.get("type") == "USER" and m.get("email")]
    if not all_emails:
        print(f"No user members found in {group_email}.")
        return

    emails = [e for e in all_emails if _is_internal(e)]
    external = [e for e in all_emails if not _is_internal(e)]

    if external:
        print(f"\nSkipping {len(external)} external member(s) (cannot delegate):")
        for e in sorted(external):
            print(f"  {e}")

    if not emails:
        print(f"\nNo internal members in {group_email} to check.")
        return

    print(f"\nChecking {len(emails)} internal member(s) of {group_email}...")
    results = {}
    errors = {}

    def _worker(user_email):
        try:
            return user_email, _get_forwarding(user_email), None
        except Exception as exc:
            return user_email, None, str(exc)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_worker, e) for e in emails]
        for future in as_completed(futures):
            user_email, data, err = future.result()
            if err:
                errors[user_email] = err
            else:
                results[user_email] = data

    all_rows = []
    for user_email in sorted(results):
        fwd, forwarding_filters = results[user_email]
        _print_user_forwarding(user_email, fwd, forwarding_filters)
        all_rows.extend(_forwarding_to_rows(user_email, fwd, forwarding_filters))

    active = [
        e for e, (fwd, flt) in results.items()
        if fwd.get("enabled") or flt
    ]
    print(f"\nSummary: {len(active)}/{len(results)} internal member(s) have forwarding or forwarding filters.")
    if active:
        print("  " + "\n  ".join(sorted(active)))
    if external:
        print(f"Skipped {len(external)} external member(s).")
    if errors:
        print(f"\n{len(errors)} error(s):")
        for e, msg in errors.items():
            print(f"  {e}: {msg}")

    if all_rows:
        safe_group = group_email.replace("@", "_at_").replace(".", "_")
        _write_csv(all_rows, f"forwarding_group_{safe_group}.csv")
    else:
        print("\nNo forwarding or forwarding filters found — nothing to save.")


def change_forwarding(email, enabled):
    if not _is_internal(email):
        print(f"Cannot modify forwarding for {email}: external account (not in {DOMAIN}).")
        return
    try:
        service = get_gmail_service(email)
        service.users().settings().updateAutoForwarding(
            userId="me", body={"enabled": enabled}
        ).execute()
        print(f"Forwarding {'enabled' if enabled else 'disabled'}.")
    except Exception as exc:
        print(f"Error updating {email}: {exc}")


def add_forwarding_address(email):
    if not _is_internal(email):
        print(f"Cannot add forwarding address for {email}: external account (not in {DOMAIN}).")
        return
    forward_email = input("Forwarding address to add: ").strip()
    try:
        service = get_gmail_service(email)
        result = service.users().settings().forwardingAddresses().create(
            userId="me", body={"forwardingEmail": forward_email}
        ).execute()
        print(json.dumps(result, indent=2))
    except Exception as exc:
        print(f"Error adding forwarding address for {email}: {exc}")


def user_menu(email):
    while True:
        choice = pick(f"Forwarding ({email})", [
            "Check forwarding + filters", "Enable forwarding", "Disable forwarding",
            "Add forwarding address", "Exit"
        ])
        if choice == 1:
            check_forwarding(email)
            pause()
        elif choice == 2:
            change_forwarding(email, True)
            pause()
        elif choice == 3:
            change_forwarding(email, False)
            pause()
        elif choice == 4:
            add_forwarding_address(email)
            pause()
        else:
            return


def main():
    mode = pick("Check forwarding for", ["Single user", "Group (all members)", "Exit"])
    if mode == 3:
        return

    if mode == 2:
        group_email = input("Enter group email: ").strip()
        if not group_email:
            print("No group provided.")
            return
        check_group_forwarding(group_email)
        pause()
        return

    email = input("Enter email address: ").strip()
    if not email:
        print("No email provided.")
        return
    user_menu(email)


if __name__ == "__main__":
    main()
