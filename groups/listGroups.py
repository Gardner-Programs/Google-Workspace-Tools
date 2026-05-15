"""List all groups in the domain with optional CSV export."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_service, paginate_groups, ask_export


def main():
    service = get_service()
    groups = paginate_groups(service)
    print(f"\nFound {len(groups)} groups\n")
    for g in groups:
        print(f"  {g['email']:<50} {g.get('name', '')}")
    ask_export(groups, "allGroups.csv")


if __name__ == "__main__":
    main()
