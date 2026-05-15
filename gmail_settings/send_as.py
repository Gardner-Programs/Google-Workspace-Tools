"""Check and clear display names from sendAs aliases."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_service, get_gmail_service, paginate_users, pick, pause


def check_sendAs(user):
    """Clear display name for the user's primary sendAs alias."""
    service = get_gmail_service(user)
    send_list = service.users().settings().sendAs().list(userId=user).execute()
    addresses = send_list.get("sendAs", None)
    if addresses:
        for address in addresses:
            if address["sendAsEmail"] == user and address["displayName"] != "":
                address["displayName"] = ""
                service.users().settings().sendAs().update(
                    userId="me", sendAsEmail=user, body=address
                ).execute()
                print(f"  {user} — display name cleared")
                return
    print(f"  {user} — no change needed")


def list_sendAs(user):
    service = get_gmail_service(user)
    send_list = service.users().settings().sendAs().list(userId=user).execute()
    for alias in send_list.get("sendAs", []):
        print(f"\n  sendAsEmail:  {alias.get('sendAsEmail', '')}")
        print(f"  displayName:  {alias.get('displayName', '')}")
        print(f"  replyTo:      {alias.get('replyToAddress', '')}")
        print(f"  isPrimary:    {alias.get('isPrimary', False)}")
        print(f"  default:      {alias.get('isDefault', False)}")


def wipe_sendAs(user):
    """Reset a user's sendAs to Gmail defaults: clear replyTo and displayName
    on the primary alias, delete all non-primary aliases."""
    service = get_gmail_service(user)
    send_list = service.users().settings().sendAs().list(userId=user).execute()
    aliases = send_list.get("sendAs", [])
    changes = []

    for alias in aliases:
        if alias.get("isPrimary", False):
            dirty = False
            if alias.get("replyToAddress", ""):
                alias["replyToAddress"] = ""
                dirty = True
            if alias.get("displayName", ""):
                alias["displayName"] = ""
                dirty = True
            if dirty:
                service.users().settings().sendAs().update(
                    userId="me", sendAsEmail=alias["sendAsEmail"], body=alias
                ).execute()
                changes.append(f"  Primary alias — cleared replyTo and displayName")
        else:
            addr = alias["sendAsEmail"]
            service.users().settings().sendAs().delete(userId="me", sendAsEmail=addr).execute()
            changes.append(f"  Removed alias: {addr}")

    if changes:
        print(f"\n{user} — reset to defaults:")
        for c in changes:
            print(c)
    else:
        print(f"  {user} — already at defaults")


def remove_sendAs(user):
    """List non-primary sendAs aliases and let the user pick one to delete."""
    service = get_gmail_service(user)
    send_list = service.users().settings().sendAs().list(userId=user).execute()
    aliases = [a for a in send_list.get("sendAs", []) if not a.get("isPrimary", False)]

    if not aliases:
        print(f"  {user} — no non-primary sendAs aliases to remove")
        return

    print(f"\nNon-primary sendAs aliases for {user}:\n")
    for i, alias in enumerate(aliases, 1):
        print(f"  {i}) {alias.get('sendAsEmail', '')}  (replyTo: {alias.get('replyToAddress', '') or 'none'})")

    choice = input(f"\nRemove which alias? (1-{len(aliases)}, or 'all'): ").strip()
    if choice.lower() == "all":
        to_remove = aliases
    elif choice.isdigit() and 1 <= int(choice) <= len(aliases):
        to_remove = [aliases[int(choice) - 1]]
    else:
        print("Cancelled.")
        return

    for alias in to_remove:
        addr = alias["sendAsEmail"]
        service.users().settings().sendAs().delete(userId="me", sendAsEmail=addr).execute()
        print(f"  Removed: {addr}")


def main():
    while True:
        choice = pick("Send As Settings", [
            "Clear display name — single user",
            "Clear display name — all users",
            "List sendAs for a user",
            "Remove sendAs alias — single user",
            "Wipe to defaults — single user",
            "Exit",
        ])
        if choice == 1:
            email = input("Enter email: ").strip()
            if email:
                check_sendAs(email)
            pause()
        elif choice == 2:
            service = get_service()
            users = paginate_users(service, query="isSuspended=false")
            print(f"Checking {len(users)} active users...")
            for user in users:
                email = user["primaryEmail"]
                if user.get("orgUnitPath") != "/Non-User Accounts":
                    check_sendAs(email)
            pause()
        elif choice == 3:
            email = input("Enter email: ").strip()
            if email:
                list_sendAs(email)
            pause()
        elif choice == 4:
            email = input("Enter email: ").strip()
            if email:
                remove_sendAs(email)
            pause()
        elif choice == 5:
            email = input("Enter email: ").strip()
            if email:
                wipe_sendAs(email)
            pause()
        else:
            return


if __name__ == "__main__":
    main()
