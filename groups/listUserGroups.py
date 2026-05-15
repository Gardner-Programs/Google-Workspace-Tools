"""List all groups a specific user belongs to."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_service


def main():
    email = input("Enter user email: ").strip()
    if not email:
        print("No email provided.")
        return

    service = get_service()
    page_token = None
    groups = []

    while True:
        result = service.groups().list(userKey=email, maxResults=200, pageToken=page_token).execute()
        groups.extend(result.get("groups", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    if not groups:
        print(f"{email} is not in any groups.")
        return

    print(f"\n{email} is in {len(groups)} group(s):\n")
    for g in groups:
        print(f"  {g['email']}")


if __name__ == "__main__":
    main()
