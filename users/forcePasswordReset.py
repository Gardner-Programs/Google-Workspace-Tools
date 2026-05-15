"""Force all users under /All Sites to reset their password on next login."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_service, paginate_users, rate_limited_execute, pick, pause, MAX_WORKERS


OU_PREFIX = "/All Sites"
WORKERS = 10


def get_all_sites_users():
    """Fetch all active users whose orgUnitPath starts with /All Sites."""
    service = get_service()
    users = paginate_users(service, query="isSuspended=false", excluded_ous=[])
    return [u for u in users if u.get("orgUnitPath", "").startswith(OU_PREFIX)]


def force_reset(user_email):
    """Set changePasswordAtNextLogin=True for a single user."""
    service = get_service()
    rate_limited_execute(
        service.users().update(
            userKey=user_email,
            body={"changePasswordAtNextLogin": True},
        )
    )


def reset_single_user():
    """Force password reset for a single user."""
    email = input("Enter email address: ").strip()
    if not email:
        print("No email provided.")
        return

    confirm = input(f"Force password reset on next login for {email}? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        return

    try:
        force_reset(email)
        print(f"Done. {email} will be required to reset their password on next login.")
    except Exception as e:
        print(f"Error: {e}")


def reset_all_sites():
    """Force password reset for all users under /All Sites."""
    print(f"Fetching active users under '{OU_PREFIX}'...")
    users = get_all_sites_users()
    print(f"Found {len(users)} users.\n")

    if not users:
        return

    for u in users[:10]:
        print(f"  {u['primaryEmail']}  ({u.get('orgUnitPath', '')})")
    if len(users) > 10:
        print(f"  ... and {len(users) - 10} more")

    confirm = input(f"\nForce password reset on next login for all {len(users)} users? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        return

    lock = threading.Lock()
    counter = [0]
    errors = []

    def _worker(email):
        try:
            force_reset(email)
        except Exception as e:
            with lock:
                errors.append((email, str(e)))
        with lock:
            counter[0] += 1
            print(f"\r  Progress: {counter[0]}/{len(users)} — {email}", end="", flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(_worker, u["primaryEmail"]) for u in users]
        for f in as_completed(futures):
            f.result()

    print(f"\n\nDone. {len(users) - len(errors)} user(s) set to reset password on next login.")
    if errors:
        print(f"\n{len(errors)} error(s):")
        for email, err in errors:
            print(f"  {email}: {err}")


def main():
    while True:
        choice = pick("Force Password Reset", [
            "Single user",
            "All users under /All Sites",
            "Exit",
        ])
        if choice == 1:
            reset_single_user()
            pause()
        elif choice == 2:
            reset_all_sites()
            pause()
        else:
            return


if __name__ == "__main__":
    main()
