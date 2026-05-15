"""Pull all group members and sort them by the org unit of their accounts."""
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import (
    DOMAIN, MAX_WORKERS, get_service, paginate_groups, get_members,
    rate_limited_execute, ask_export,
)


def get_user_org_unit(service, email):
    try:
        user = rate_limited_execute(
            service.users().get(userKey=email, fields="orgUnitPath")
        )
        return user.get("orgUnitPath", "/Unknown")
    except Exception:
        return "/External or Unknown"


def fetch_group_members_with_org(group):
    service = get_service()
    group_email = group["email"]
    group_name = group.get("name", "Unknown")
    members = get_members(service, group_email) or []

    rows = []
    for m in members:
        member_email = m.get("email", "")
        member_type = m.get("type", "")
        role = m.get("role", "MEMBER")

        if member_type == "USER" and member_email.endswith(f"@{DOMAIN}"):
            org_unit = get_user_org_unit(service, member_email)
        else:
            org_unit = "/External" if member_type == "GROUP" or not member_email.endswith(f"@{DOMAIN}") else "/Unknown"

        rows.append({
            "Group Name": group_name,
            "Group Email": group_email,
            "Member Email": member_email,
            "Member Role": role,
            "Member Type": member_type,
            "Org Unit": org_unit,
        })
    return rows


def main():
    service = get_service()

    single = input("Enter a group email (or press Enter for ALL groups): ").strip()
    if single:
        groups = [{"email": single, "name": single}]
    else:
        print("Fetching all groups...")
        groups = paginate_groups(service)
        print(f"Found {len(groups)} groups.")

    print(f"Fetching members and org units for {len(groups)} group(s)...")

    all_rows = []
    counter = [0]
    total = len(groups)
    lock = threading.Lock()

    def _fetch(group):
        rows = fetch_group_members_with_org(group)
        with lock:
            all_rows.extend(rows)
            counter[0] += 1
            print(f"\r  Progress: {counter[0]}/{total} groups", end="", flush=True)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_fetch, g) for g in groups]
        for f in as_completed(futures):
            f.result()
    print()

    if not all_rows:
        print("No members found.")
        return

    all_rows.sort(key=lambda r: (r["Org Unit"], r["Group Name"], r["Member Email"]))

    org_counts = defaultdict(int)
    for r in all_rows:
        org_counts[r["Org Unit"]] += 1

    print(f"\nTotal member associations: {len(all_rows)}")
    print(f"Org Units found: {len(org_counts)}\n")
    for ou in sorted(org_counts.keys()):
        print(f"  {ou:<50} {org_counts[ou]} members")

    ask_export(all_rows, "Group_Members_By_OrgUnit.csv")


if __name__ == "__main__":
    main()
