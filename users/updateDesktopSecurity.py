"""
Update the 'Enhanced desktop security' custom attribute for all active users.
Sets the local Windows account username to the first half of their email (before @).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_service, paginate_users, rate_limited_execute

SCHEMA_NAME = "Enhanced_desktop_security"
FIELD_NAME = "Local_Windows_accounts"


def main():
    service = get_service()

    print("Fetching active users...")
    users = paginate_users(service, query="isSuspended=false", projection="full")
    print(f"Found {len(users)} active users.\n")

    updated = 0
    skipped = 0
    failed = 0

    for user in users:
        email = user["primaryEmail"]
        username = email.split("@")[0]

        # Get existing entries for this field so we don't overwrite them
        current = user.get("customSchemas", {}).get(SCHEMA_NAME, {}).get(FIELD_NAME, [])
        if isinstance(current, list):
            existing_entries = current
        elif isinstance(current, dict):
            existing_entries = [current]
        else:
            existing_entries = []

        # Deduplicate existing entries by value (case-insensitive)
        seen = set()
        deduped = []
        for entry in existing_entries:
            val = entry.get("value") if isinstance(entry, dict) else None
            if val and val.lower() not in seen:
                seen.add(val.lower())
                deduped.append(entry)

        # Add username if not already present (case-insensitive)
        needs_username = username.lower() not in seen
        if needs_username:
            deduped.append({"value": username, "type": "custom", "customType": ""})

        # Skip if nothing changed (no dupes removed and username already present)
        if not needs_username and len(deduped) == len(existing_entries):
            skipped += 1
            continue

        new_entries = deduped

        body = {
            "customSchemas": {
                SCHEMA_NAME: {
                    FIELD_NAME: new_entries
                }
            }
        }

        try:
            rate_limited_execute(
                service.users().update(userKey=email, body=body)
            )
            print(f"  Updated {email} -> {username}")
            updated += 1
        except Exception as e:
            print(f"  FAILED {email}: {e}")
            failed += 1

    print(f"\nDone. Updated: {updated} | Skipped (already set): {skipped} | Failed: {failed}")


if __name__ == "__main__":
    main()
