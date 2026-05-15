"""
Shared utilities for Google Workspace admin scripts.

Import from this module instead of duplicating auth, pagination,
rate-limiting, and export logic in every script.

Usage:
    from _master import get_service, paginate_groups, get_members, ask_export
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas
from customScripts.authenticator import admin_directory_v1_api, gmail_v1_api

DOMAIN = "yourdomain.com"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)
MAX_WORKERS = 5
CALLS_PER_SECOND = 20

_rate_lock = threading.Lock()
_last_call_time = 0.0


def rate_limited_execute(request):
    """Execute a Google API request while respecting rate limits."""
    global _last_call_time
    with _rate_lock:
        now = time.monotonic()
        min_interval = 1.0 / CALLS_PER_SECOND
        wait = min_interval - (now - _last_call_time)
        if wait > 0:
            time.sleep(wait)
        _last_call_time = time.monotonic()
    return request.execute()


def get_service():
    """Return a fresh Admin Directory API service instance (thread-safe)."""
    return admin_directory_v1_api()


def get_gmail_service(user):
    """Return a Gmail API service delegated to the given user."""
    return gmail_v1_api(user)


# ── Group helpers ────────────────────────────────────────────


def paginate_groups(service):
    """Fetch all groups in the domain with pagination."""
    all_groups = []
    page_token = None
    while True:
        result = rate_limited_execute(
            service.groups().list(
                domain=DOMAIN, maxResults=500, orderBy="email", pageToken=page_token
            )
        )
        all_groups.extend(result.get("groups", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return all_groups


def get_members(service, group_email):
    """Fetch all members of a single group. Returns list or None on error."""
    members = []
    page_token = None
    while True:
        try:
            result = rate_limited_execute(
                service.members().list(
                    groupKey=group_email, maxResults=200, pageToken=page_token
                )
            )
        except Exception as e:
            print(f"  Error fetching members for {group_email}: {e}")
            return None
        members.extend(result.get("members", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return members


def threaded_get_members(groups):
    """Fetch members for multiple groups concurrently. Returns dict of email -> members list."""
    results = {}
    lock = threading.Lock()
    total = len(groups)
    counter = [0]

    def _fetch(group):
        local_service = get_service()
        email = group["email"]
        members = get_members(local_service, email)
        with lock:
            results[email] = members
            counter[0] += 1
            print(f"\r  Progress: {counter[0]}/{total} groups", end="", flush=True)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_fetch, g) for g in groups]
        for future in as_completed(futures):
            future.result()
    print()
    return results


# ── User helpers ─────────────────────────────────────────────


def paginate_users(service, query=None, excluded_ous=None, projection=None):
    """Fetch users with optional query filter and OU exclusion."""
    if excluded_ous is None:
        excluded_ous = ["/Non-User Accounts", "/Offboarded Employees", "/All Sites/Data Hold"]
    user_list = []
    kwargs = dict(domain=DOMAIN, maxResults=500, orderBy="email")
    if query:
        kwargs["query"] = query
    if projection:
        kwargs["projection"] = projection
    request = service.users().list(**kwargs)
    while request:
        result = request.execute()
        for user in result.get("users", []):
            if user.get("orgUnitPath") not in excluded_ous:
                user_list.append(user)
        request = service.users().list_next(previous_request=request, previous_response=result)
    return user_list


# ── Export / UI helpers ──────────────────────────────────────


def ask_export(data, default_name):
    """Prompt user to export results to CSV."""
    choice = input("\nExport to CSV? (y/n): ").strip().lower()
    if choice == "y":
        filename = input(f"Filename [{default_name}]: ").strip() or default_name
        filepath = os.path.join(OUTPUT_DIR, filename)
        df = pandas.DataFrame(data)
        df.to_csv(filepath, index=False)
        print(f"Saved to {filepath}")


def pick(prompt, options):
    """Display a numbered menu and return the chosen option (1-indexed)."""
    print(f"\n{prompt}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    while True:
        choice = input("> ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return int(choice)
        print(f"Enter a number 1-{len(options)}")


def pause():
    input("\nPress Enter to continue...")
