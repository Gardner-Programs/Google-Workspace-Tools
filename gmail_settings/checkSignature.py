"""Check or set a user's Gmail signature."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_gmail_service, pick, pause


def check_signature(email):
    service = get_gmail_service(email)
    aliases = service.users().settings().sendAs().list(userId='me').execute()
    for alias in aliases.get("sendAs", []):
        addr = alias.get("sendAsEmail", "")
        sig = alias.get("signature", "")
        print(f"\n--- {addr} ---")
        print(sig if sig else "(no signature set)")


def change_signature(email):
    source = pick("Set signature from:", ["HTML file path", "Paste HTML", "Clear signature"])
    if source == 1:
        path = input("File path: ").strip()
        with open(path, "r") as f:
            html = f.read()
    elif source == 2:
        print("Paste HTML (enter a blank line to finish):")
        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        html = "\n".join(lines)
    else:
        html = ""
    service = get_gmail_service(email)
    service.users().settings().sendAs().patch(
        userId="me", sendAsEmail=email, body={"signature": html}
    ).execute()
    print(f"Signature updated for {email}")


def main():
    email = input("Enter email address: ").strip()
    if not email:
        print("No email provided.")
        return

    while True:
        choice = pick(f"Signature Manager ({email})", [
            "Check signature", "Set signature", "Exit"
        ])
        if choice == 1:
            check_signature(email)
            pause()
        elif choice == 2:
            change_signature(email)
            pause()
        else:
            return


if __name__ == "__main__":
    main()
