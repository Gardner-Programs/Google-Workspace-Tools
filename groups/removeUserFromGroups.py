"""Remove one or more users from all groups they belong to (threaded)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from _master import (
    get_service,
    paginate_groups,
    threaded_get_members,
    rate_limited_execute,
    OUTPUT_DIR,
    MAX_WORKERS,
)


def collect_emails():
    """Return deduped lowercase emails from a CSV path or pasted input."""
    print("Enter a CSV file path, or paste emails (one per line or comma-separated).")
    print("Submit a blank line when done:")
    raw_lines = []
    first = input().strip()
    if first and os.path.isfile(first):
        with open(first) as fh:
            raw_lines = fh.readlines()
    else:
        if first:
            raw_lines.append(first)
        while True:
            line = input()
            if not line.strip():
                break
            raw_lines.append(line)

    emails, seen = [], set()
    for line in raw_lines:
        for part in line.replace(",", " ").split():
            cleaned = part.strip().strip('"').strip("'").lower()
            if "@" in cleaned and cleaned not in seen:
                seen.add(cleaned)
                emails.append(cleaned)
    return emails


def main():
    targets = collect_emails()
    if not targets:
        print("No emails provided.")
        return

    print(f"\n{len(targets)} target user(s):")
    for e in targets:
        print(f"  {e}")
    print("\nThis will remove the above user(s) from EVERY group they belong to.")
    if input('Type "yes" to confirm: ').strip().lower() != "yes":
        print("Aborted.")
        return

    service = get_service()
    print("\nFetching all groups...")
    all_groups = paginate_groups(service)
    print(f"  {len(all_groups)} groups in domain")

    print("Fetching members of every group (threaded)...")
    members_by_group = threaded_get_members(all_groups)

    targets_set = set(targets)
    removals = []  # (user_email, group_email)
    for group_email, members in members_by_group.items():
        if not members:
            continue
        for m in members:
            mem_email = (m.get("email") or "").lower()
            if mem_email in targets_set:
                removals.append((mem_email, group_email))

    if not removals:
        print("\nNo target users were found in any group. Nothing to do.")
        return

    print(f"\n{len(removals)} membership(s) to remove. Removing (threaded)...")

    results = {e: [] for e in targets}
    failures = []
    lock = threading.Lock()
    counter = [0]
    total = len(removals)

    def _remove(user_email, group_email):
        local_service = get_service()
        try:
            rate_limited_execute(
                local_service.members().delete(
                    groupKey=group_email, memberKey=user_email
                )
            )
            with lock:
                results[user_email].append(group_email)
        except Exception as exc:
            with lock:
                failures.append((user_email, group_email, str(exc)))
        finally:
            with lock:
                counter[0] += 1
                print(f"\r  Progress: {counter[0]}/{total}", end="", flush=True)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_remove, em, gr) for em, gr in removals]
        for fut in as_completed(futures):
            fut.result()
    print()

    print("\n── Summary ──")
    for email, groups in results.items():
        print(f"  {email}: removed from {len(groups)} group(s)")
    if failures:
        print(f"\n{len(failures)} failure(s):")
        for em, gr, err in failures[:10]:
            print(f"  {em} from {gr}: {err}")
        if len(failures) > 10:
            print(f"  ... and {len(failures) - 10} more")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(OUTPUT_DIR, f"removed_groups_{timestamp}.csv")
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write("email,group_email,status\n")
        for email, groups in results.items():
            for g in groups:
                fh.write(f"{email},{g},removed\n")
        for em, gr, err in failures:
            err_clean = err.replace(",", ";").replace("\n", " ").replace("\r", " ")
            fh.write(f"{em},{gr},failed: {err_clean}\n")
    print(f"\nLog saved to {log_path}")


if __name__ == "__main__":
    main()
