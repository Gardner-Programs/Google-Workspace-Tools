"""List all members across all groups (or a single group) with optional CSV export."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_service, paginate_groups, threaded_get_members, ask_export


def main():
    service = get_service()
    single = input("Enter a group email (or press Enter for ALL groups): ").strip()

    if single:
        groups = [{"email": single, "name": single}]
    else:
        groups = paginate_groups(service)

    print(f"Fetching members for {len(groups)} group(s)...")
    members_map = threaded_get_members(groups)

    rows = []
    for g in groups:
        group_email = g["email"]
        group_name = g.get("name", "Unknown")
        members = members_map.get(group_email)

        if members is None:
            rows.append({
                "Group Name": group_name, "Group Email": group_email,
                "Member Email": "ERROR", "Member Role": "ERROR",
            })
            continue
        if not members:
            rows.append({
                "Group Name": group_name, "Group Email": group_email,
                "Member Email": "EMPTY_GROUP", "Member Role": "N/A",
            })
            continue
        for m in members:
            rows.append({
                "Group Name": group_name, "Group Email": group_email,
                "Member Email": m.get("email", "Unknown/External"),
                "Member Role": m.get("role", "MEMBER"),
            })

    print(f"\nTotal associations: {len(rows)}")
    ask_export(rows, "Groups_Members_Export.csv")


if __name__ == "__main__":
    main()
