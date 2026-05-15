"""Check, enable, or disable a user's Gmail vacation responder."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_gmail_service, pick, pause


def check_vacation(email):
    service = get_gmail_service(email)
    vacation = service.users().settings().getVacation(userId="me").execute()
    enabled = vacation.get("enableAutoReply", False)
    print(f"\nAuto-reply enabled: {enabled}")
    if enabled:
        print(f"  Subject:  {vacation.get('responseSubject', '')}")
        print(f"  Body:     {vacation.get('responseBodyPlainText', vacation.get('responseBodyHtml', ''))}")
        print(f"  Contacts: {vacation.get('restrictToContacts', False)}")
        print(f"  Domain:   {vacation.get('restrictToDomain', False)}")


def enable_vacation(email):
    subject = input("Subject: ").strip()
    print("Body HTML (enter a blank line to finish):")
    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    body_html = "\n".join(lines)
    restrict_contacts = input("Restrict to contacts? (y/n) [n]: ").strip().lower() == "y"
    restrict_domain = input("Restrict to domain? (y/n) [n]: ").strip().lower() == "y"
    start = input("Start time (epoch ms, Enter to skip): ").strip() or None
    end = input("End time (epoch ms, Enter to skip): ").strip() or None

    vacation_body = {
        "enableAutoReply": True,
        "responseSubject": subject,
        "responseBodyHtml": body_html,
        "restrictToContacts": restrict_contacts,
        "restrictToDomain": restrict_domain,
    }
    if start:
        vacation_body["startTime"] = start
    if end:
        vacation_body["endTime"] = end

    service = get_gmail_service(email)
    service.users().settings().updateVacation(userId="me", body=vacation_body).execute()
    print("Vacation responder enabled.")


def disable_vacation(email):
    service = get_gmail_service(email)
    service.users().settings().updateVacation(
        userId="me", body={"enableAutoReply": False}
    ).execute()
    print("Vacation responder disabled.")


def main():
    email = input("Enter email address: ").strip()
    if not email:
        print("No email provided.")
        return

    while True:
        choice = pick(f"Vacation Responder ({email})", [
            "Check vacation settings", "Enable vacation", "Disable vacation", "Exit"
        ])
        if choice == 1:
            check_vacation(email)
            pause()
        elif choice == 2:
            enable_vacation(email)
            pause()
        elif choice == 3:
            disable_vacation(email)
            pause()
        else:
            return


if __name__ == "__main__":
    main()
