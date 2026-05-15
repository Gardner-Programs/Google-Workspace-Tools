"""Find users by full name and move them to Headquarters > Recruiting OU."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_service

TARGET_OU = "/All Sites/Headquarters/Recruiting"

NAMES = [
    "Valeria Cardona",
    "Brittany Long",
    "Jennifer Bloom",
    "Taya Easterday",
    "Jamie Buchanan",
    "Jessica Carroll",
    "Maria Weybright",
    "Robert Ochoa",
    "Isabella Cursino",
]


def fetch_active_users(service):
    users = []
    request = service.users().list(
        domain="yourdomain.com", maxResults=500, orderBy="email", query="isSuspended=false"
    )
    while request:
        result = request.execute()
        users.extend(result.get("users", []))
        request = service.users().list_next(previous_request=request, previous_response=result)
    return users


def main():
    service = get_service()
    print(f"Fetching active users...")
    users = fetch_active_users(service)
    print(f"  {len(users)} active users.\n")

    by_full_name = {}
    for u in users:
        name = u.get("name", {}).get("fullName", "").strip().lower()
        if name:
            by_full_name.setdefault(name, []).append(u)

    matched, missing, ambiguous = [], [], []
    for n in NAMES:
        candidates = by_full_name.get(n.lower(), [])
        if len(candidates) == 1:
            matched.append((n, candidates[0]))
        elif len(candidates) == 0:
            missing.append(n)
        else:
            ambiguous.append((n, candidates))

    print("=== Matched ===")
    for n, u in matched:
        print(f"  {n:30s} -> {u['primaryEmail']}  (current OU: {u.get('orgUnitPath')})")
    if missing:
        print("\n=== Not found ===")
        for n in missing:
            print(f"  {n}")
    if ambiguous:
        print("\n=== Ambiguous (multiple matches) ===")
        for n, cands in ambiguous:
            print(f"  {n}:")
            for c in cands:
                print(f"    - {c['primaryEmail']}  (OU: {c.get('orgUnitPath')})")

    if not matched:
        print("\nNothing to move.")
        return

    print(f"\nTarget OU: {TARGET_OU}")
    confirm = input(f"\nMove {len(matched)} user(s) to {TARGET_OU}? Type 'yes' to confirm: ").strip()
    if confirm != "yes":
        print("Cancelled.")
        return

    for n, u in matched:
        email = u["primaryEmail"]
        if u.get("orgUnitPath") == TARGET_OU:
            print(f"  SKIP {email} (already in target OU)")
            continue
        try:
            service.users().patch(userKey=email, body={"orgUnitPath": TARGET_OU}).execute()
            print(f"  MOVED {email}")
        except Exception as e:
            print(f"  FAILED {email}: {e}")


if __name__ == "__main__":
    main()
