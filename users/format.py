"""Move users to an org unit or delete users from a list."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_service


def change_org_unit(user_list, org_unit="/Offboarded Employees"):
    service = get_service()
    for user in user_list:
        results = service.users().patch(userKey=user, body={"orgUnitPath": org_unit}).execute()
        print(user + " is updated.")


def delete_users(user_list):
    service = get_service()
    for user in user_list:
        service.users().delete(userKey=user).execute()
        print(user + " is deleted.")


def main():
    print("Paste user emails (one per line, blank line to finish):")
    users = []
    while True:
        line = input().strip()
        if not line:
            break
        users.append(line)

    if not users:
        print("No users provided.")
        return

    print(f"\n{len(users)} user(s) loaded.")
    mode = input("1) Move to org unit  2) Delete users\n> ").strip()

    if mode == "1":
        org_unit = input("Org unit path [/Offboarded Employees]: ").strip() or "/Offboarded Employees"
        change_org_unit(users, org_unit)
    elif mode == "2":
        confirm = input(f"DELETE {len(users)} users? Type 'yes' to confirm: ").strip()
        if confirm == "yes":
            delete_users(users)
        else:
            print("Cancelled.")


if __name__ == "__main__":
    main()
