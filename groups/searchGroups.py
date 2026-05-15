"""Search groups with name/email, empty-only, and member-count filters."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_service, paginate_groups, threaded_get_members, ask_export


def main():
    print("\n── Search Filters (leave blank to skip) ──")
    query = input("  Name/email contains: ").strip()
    empty_only = input("  Empty groups only? (y/n): ").strip().lower() == "y"

    min_members = None
    max_members = None
    if not empty_only:
        val = input("  Min members: ").strip()
        min_members = int(val) if val else None
        val = input("  Max members: ").strip()
        max_members = int(val) if val else None

    need_member_count = empty_only or min_members is not None or max_members is not None

    service = get_service()
    groups = paginate_groups(service)

    if query:
        groups = [
            g for g in groups
            if query.lower() in g["email"].lower()
            or query.lower() in g.get("name", "").lower()
        ]

    if need_member_count:
        print(f"Fetching members for {len(groups)} group(s)...")
        members_map = threaded_get_members(groups)

    results = []
    for g in groups:
        if need_member_count:
            count = len(members_map[g["email"]]) if members_map.get(g["email"]) else 0
            if empty_only and count > 0:
                continue
            if min_members is not None and count < min_members:
                continue
            if max_members is not None and count > max_members:
                continue
            g["member_count"] = count
        results.append(g)

    print(f"\nFound {len(results)} matching groups\n")
    for g in results:
        count_str = f"  ({g['member_count']} members)" if "member_count" in g else ""
        print(f"  {g['email']:<50} {g.get('name', '')}{count_str}")

    ask_export(results, "search_results.csv")


if __name__ == "__main__":
    main()
