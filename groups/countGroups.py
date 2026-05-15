"""Show total group count and list empty groups with optional CSV export."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_service, paginate_groups, threaded_get_members, ask_export


def main():
    service = get_service()
    groups = paginate_groups(service)

    print(f"Fetching members for {len(groups)} group(s)...")
    members_map = threaded_get_members(groups)

    empty_groups = [g for g in groups if not members_map.get(g["email"])]

    print(f"\n  Total groups: {len(groups)}")
    print(f"  Empty groups: {len(empty_groups)}")

    if empty_groups:
        print("\n  Empty groups:")
        for g in empty_groups:
            print(f"    {g['email']:<50} {g.get('name', '')}")

    ask_export(
        [{"Email": g["email"], "Name": g.get("name", "")} for g in empty_groups],
        "empty_groups.csv",
    )


if __name__ == "__main__":
    main()
