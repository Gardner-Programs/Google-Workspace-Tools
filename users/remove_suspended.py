"""Remove all suspended users from every group they belong to."""
import os
import time
import concurrent.futures
from pathlib import Path
from googleapiclient.errors import HttpError
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_service, DOMAIN, OUTPUT_DIR

LOG_DIR = Path(os.path.join(OUTPUT_DIR, 'Removed Email Log'))
MAX_WORKERS = 30


def write_log(email, removed_groups):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / f"{email}.txt"
        with open(log_file, "a") as f:
            f.write(str(removed_groups) + "\n")
    except OSError as e:
        print(f"Error writing log file for {email}: {e}")


def get_all_suspended_users():
    service = get_service()
    all_suspended_users = []
    page_token = None

    print("Fetching full suspended user directory...")
    query = "isSuspended=true"

    while True:
        try:
            result = service.users().list(
                domain=DOMAIN, maxResults=500, orderBy="email",
                query=query, pageToken=page_token
            ).execute()
        except Exception as e:
            print(f"Critical API Error fetching users: {e}")
            break

        all_suspended_users.extend(result.get("users", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    print(f"Directory fetch complete. Found {len(all_suspended_users)} suspended users.")
    return all_suspended_users


def remove_users_groups(email):
    service = get_service()
    removed_groups = []
    page_token = None

    print(f"Checking groups for suspended user: {email}")

    while True:
        try:
            result = service.groups().list(
                userKey=email, maxResults=200, pageToken=page_token
            ).execute()

            for group in result.get('groups', []):
                group_email = group.get('email')
                try:
                    service.members().delete(groupKey=group_email, memberKey=email).execute()
                    print(f" - REMOVED {email} from {group_email}")
                    removed_groups.append(group_email)
                except HttpError as e:
                    print(f" ! ERROR removing {email} from {group_email}: {e}")
                except Exception as e:
                    print(f" ! UNEXPECTED ERROR: {e}")

            page_token = result.get('nextPageToken')
            if not page_token:
                break

        except HttpError as e:
            print(f"Error listing groups for {email}: {e}")
            return f"Error listing groups for {email}: {e}"
        except Exception as e:
            return f"Unexpected error for {email}: {e}"

    if removed_groups:
        write_log(email, removed_groups)
        return f"Removed {len(removed_groups)} groups for {email}"
    return None


if __name__ == '__main__':
    suspended_users = get_all_suspended_users()

    if suspended_users:
        print(f"Starting removal process with {MAX_WORKERS} workers (Ramp-up enabled)...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for user in suspended_users:
                email = user.get('primaryEmail')
                future = executor.submit(remove_users_groups, email)
                futures.append(future)
                time.sleep(0.08)

            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    print(f"Thread generated an exception: {exc}")

    print("Process finished.")
