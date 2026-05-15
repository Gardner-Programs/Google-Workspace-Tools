"""List, create, or delete Gmail filters.

Supports listing filters for a single user or every member of a group.
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


def _is_internal(email):
    return email.lower().endswith(f"@{DOMAIN.lower()}")


def _get_filters(email):
    """Return (service, filters_list) for the given user."""
    service = get_gmail_service(email)
    results = rate_limited_execute(
        service.users().settings().filters().list(userId="me")
    )
    return service, results.get("filter", [])


CSV_FIELDS = [
    "user", "filter_id",
    "from", "to", "subject", "has_words", "doesnt_have",
    "has_attachment", "size_mb", "size_comparison",
    "forward", "add_labels", "remove_labels", "other_actions",
]


def _resolve_labels(service, label_ids, cache):
    names = []
    for l_id in label_ids:
        if l_id not in cache:
            try:
                lbl = rate_limited_execute(
                    service.users().labels().get(userId="me", id=l_id)
                )
                cache[l_id] = lbl.get("name", l_id)
            except Exception:
                cache[l_id] = l_id
        names.append(cache[l_id])
    return names


def _filter_to_row(email, f, service, label_cache):
    criteria = f.get("criteria", {})
    action = f.get("action", {})

    add_names = _resolve_labels(service, action.get("addLabelIds", []), label_cache)
    remove_names = _resolve_labels(service, action.get("removeLabelIds", []), label_cache)

    other = {
        k: v for k, v in action.items()
        if k not in ("addLabelIds", "removeLabelIds", "forward")
    }

    size_bytes = criteria.get("size", "")
    size_mb = round(size_bytes / 1048576, 2) if isinstance(size_bytes, int) and size_bytes else ""

    return {
        "user": email,
        "filter_id": f.get("id", ""),
        "from": criteria.get("from", ""),
        "to": criteria.get("to", ""),
        "subject": criteria.get("subject", ""),
        "has_words": criteria.get("query", ""),
        "doesnt_have": criteria.get("negatedQuery", ""),
        "has_attachment": criteria.get("hasAttachment", ""),
        "size_mb": size_mb,
        "size_comparison": criteria.get("sizeComparison", ""),
        "forward": action.get("forward", ""),
        "add_labels": ", ".join(add_names),
        "remove_labels": ", ".join(remove_names),
        "other_actions": "; ".join(f"{k}={v}" for k, v in other.items()),
    }


def _print_filters(email, filters, service):
    if not filters:
        print(f"\n{email}: no filters.")
        return []

    print(f"\n=== {email} ({len(filters)} filter(s)) ===")
    label_cache = {}
    rows = []
    for f in filters:
        row = _filter_to_row(email, f, service, label_cache)
        print(f"\nFilter ID: {row['filter_id']}")
        match_parts = [
            (k, row[k]) for k in
            ("from", "to", "subject", "has_words", "doesnt_have",
            "has_attachment", "size_mb", "size_comparison")
            if row[k] not in ("", None, False)
        ]
        if match_parts:
            print("  MATCHES:")
            for k, v in match_parts:
                print(f"    {k}: {v}")
        action_parts = []
        if row["forward"]:
            action_parts.append(("forward", row["forward"]))
        if row["add_labels"]:
            action_parts.append(("add_labels", row["add_labels"]))
        if row["remove_labels"]:
            action_parts.append(("remove_labels", row["remove_labels"]))
        if row["other_actions"]:
            action_parts.append(("other", row["other_actions"]))
        if action_parts:
            print("  ACTIONS:")
            for k, v in action_parts:
                print(f"    {k}: {v}")
        print("-" * 40)
        rows.append(row)
    return rows


def _write_csv(rows, filename):
    if not rows:
        return
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, filename)
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved to {csv_path}")


def check_filters(email):
    if not _is_internal(email):
        print(f"Skipping {email}: external account (not in {DOMAIN}).")
        return
    try:
        service, filters = _get_filters(email)
    except Exception as exc:
        print(f"Error fetching filters for {email}: {exc}")
        return

    rows = _print_filters(email, filters, service)
    if len(filters) > 10:
        _write_csv(rows, f"filters_{email.replace('@', '_at_')}.csv")


def check_group_filters(group_email):
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

    print(f"\nFetching filters for {len(emails)} internal member(s) of {group_email}...")
    results = {}
    errors = {}

    def _worker(user_email):
        try:
            svc, flt = _get_filters(user_email)
            return user_email, svc, flt, None
        except Exception as exc:
            return user_email, None, None, str(exc)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_worker, e) for e in emails]
        for future in as_completed(futures):
            user_email, svc, flt, err = future.result()
            if err:
                errors[user_email] = err
            else:
                results[user_email] = (svc, flt)

    all_rows = []
    users_with_filters = []
    for user_email in sorted(results):
        svc, flt = results[user_email]
        rows = _print_filters(user_email, flt, svc)
        all_rows.extend(rows)
        if flt:
            users_with_filters.append(user_email)

    print(f"\nSummary: {len(users_with_filters)}/{len(results)} internal member(s) have filters "
          f"({len(all_rows)} total).")
    if users_with_filters:
        print("  " + "\n  ".join(users_with_filters))
    if external:
        print(f"Skipped {len(external)} external member(s).")
    if errors:
        print(f"\n{len(errors)} error(s):")
        for e, msg in errors.items():
            print(f"  {e}: {msg}")

    if all_rows:
        safe_group = group_email.replace("@", "_at_").replace(".", "_")
        _write_csv(all_rows, f"filters_group_{safe_group}.csv")


def create_filter(email):
    if not _is_internal(email):
        print(f"Cannot create filter for {email}: external account (not in {DOMAIN}).")
        return

    print("\n=== Create Filter ===")
    print("Enter criteria (Enter to skip):\n")
    filter_from = input("  From: ").strip()
    filter_to = input("  To: ").strip()
    subject = input("  Subject: ").strip()
    has_words = input("  Has the words: ").strip()
    doesnt_have = input("  Doesn't have: ").strip()
    size_str = input("  Size in MB (0 to skip): ").strip()
    size = int(size_str) * 1048576 if size_str and size_str != "0" else 0
    if size:
        size_comp = input("  Size comparison (larger/smaller) [larger]: ").strip() or "larger"
    else:
        size_comp = "larger"
    has_attach = input("  Has attachment? (y/n) [n]: ").strip().lower() == "y"

    criteria = {}
    if filter_from:
        criteria["from"] = filter_from
    if filter_to:
        criteria["to"] = filter_to
    if subject:
        criteria["subject"] = subject
    if has_words:
        criteria["query"] = has_words
    if doesnt_have:
        criteria["negatedQuery"] = doesnt_have
    if size:
        criteria["size"] = size
        criteria["sizeComparison"] = size_comp
    if has_attach:
        criteria["hasAttachment"] = True

    if not criteria:
        print("Error: need at least one criterion.")
        return

    print("\nActions (y/n):\n")
    add_labels = []
    remove_labels = []

    if input("  Skip the inbox (archive)? [n]: ").strip().lower() == "y":
        remove_labels.append("INBOX")
    if input("  Mark as read? [n]: ").strip().lower() == "y":
        remove_labels.append("UNREAD")
    if input("  Star it? [n]: ").strip().lower() == "y":
        add_labels.append("STARRED")
    if input("  Delete it? [n]: ").strip().lower() == "y":
        add_labels.append("TRASH")
    if input("  Always mark important? [n]: ").strip().lower() == "y":
        add_labels.append("IMPORTANT")
    if input("  Never mark important? [n]: ").strip().lower() == "y":
        remove_labels.append("IMPORTANT")

    apply_label = input("  Apply label (name, Enter to skip): ").strip()
    try:
        service = get_gmail_service(email)
    except Exception as exc:
        print(f"Error connecting for {email}: {exc}")
        return

    if apply_label:
        try:
            all_labels = service.users().labels().list(userId='me').execute()
            label_map = {l["name"]: l["id"] for l in all_labels.get("labels", [])}
            if apply_label in label_map:
                add_labels.append(label_map[apply_label])
            else:
                new_label = service.users().labels().create(
                    userId="me", body={"name": apply_label}
                ).execute()
                add_labels.append(new_label["id"])
                print(f"  Created label: {apply_label}")
        except Exception as exc:
            print(f"  Error resolving label: {exc}")
            return

    forward_to = input("  Forward to (email, Enter to skip): ").strip()

    action = {}
    if add_labels:
        action["addLabelIds"] = add_labels
    if remove_labels:
        action["removeLabelIds"] = remove_labels
    if forward_to:
        action["forward"] = forward_to

    filter_content = {"criteria": criteria, "action": action}
    print(f"\n{json.dumps(filter_content, indent=2)}")
    if input("\nCreate this filter? (y/n): ").strip().lower() != "y":
        print("Cancelled.")
        return

    if forward_to:
        try:
            service.users().settings().forwardingAddresses().create(
                userId="me", body={"forwardingEmail": forward_to}
            ).execute()
        except Exception as e:
            print(f"  Note (forwarding address): {e}")

    try:
        result = service.users().settings().filters().create(
            userId="me", body=filter_content
        ).execute()
        print(f"Filter created: {result.get('id', '')}")
    except Exception as exc:
        print(f"Error creating filter: {exc}")


def delete_filter(email):
    if not _is_internal(email):
        print(f"Cannot delete filter for {email}: external account (not in {DOMAIN}).")
        return
    filter_id = input("Filter ID to delete: ").strip()
    if not filter_id:
        return
    try:
        service = get_gmail_service(email)
        service.users().settings().filters().delete(userId="me", id=filter_id).execute()
        print(f"Filter {filter_id} deleted.")
    except Exception as exc:
        print(f"Error deleting filter {filter_id} for {email}: {exc}")


def user_menu(email):
    while True:
        choice = pick(f"Filters ({email})", [
            "List filters", "Create filter", "Delete filter", "Exit"
        ])
        if choice == 1:
            check_filters(email)
            pause()
        elif choice == 2:
            create_filter(email)
            pause()
        elif choice == 3:
            delete_filter(email)
            pause()
        else:
            return


def main():
    mode = pick("Check filters for", ["Single user", "Group (all members)", "Exit"])
    if mode == 3:
        return

    if mode == 2:
        group_email = input("Enter group email: ").strip()
        if not group_email:
            print("No group provided.")
            return
        check_group_filters(group_email)
        pause()
        return

    email = input("Enter email address: ").strip()
    if not email:
        print("No email provided.")
        return
    user_menu(email)


if __name__ == "__main__":
    main()
