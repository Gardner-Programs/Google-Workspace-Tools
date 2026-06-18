"""Add a single user to multiple groups (paste messy list, emails are extracted)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_service
from text_utils import extract_emails


def add_member_to_group(service, group_email, user_email, role="MEMBER"):
    body = {"email": user_email, "role": role}
    try:
        service.members().insert(groupKey=group_email, body=body).execute()
        return True, "Added"
    except Exception as e:
        error_msg = str(e)
        if "Member already exists" in error_msg:
            return False, "Already a member"
        return False, error_msg


def read_multiline_input(prompt):
    print(prompt)
    print("  (paste your list, then press Enter on an empty line to finish)\n")
    lines = []
    while True:
        line = input()
        if line.strip() == "":
            break
        lines.append(line)
    return "\n".join(lines)


def main():
    print("""
+==========================================+
|     Add User to Multiple Groups CLI      |
+==========================================+
""")

    user_email = input("Enter the user email to add: ").strip()
    if not user_email or "@" not in user_email:
        print("Invalid email. Exiting.")
        sys.exit(1)

    raw_text = read_multiline_input(
        "\nPaste the group emails (can be messy - emails will be extracted):"
    )

    if not raw_text.strip():
        print("No input provided. Exiting.")
        sys.exit(1)

    group_emails = list(dict.fromkeys(extract_emails(raw_text)))
    group_emails = [e for e in group_emails if e.lower() != user_email.lower()]

    if not group_emails:
        print("\nNo group emails found in the pasted text. Exiting.")
        sys.exit(1)

    print(f"\nFound {len(group_emails)} group(s):")
    for i, g in enumerate(group_emails, 1):
        print(f"  {i}. {g}")

    print(f"\nUser to add: {user_email}")
    confirm = input("\nProceed? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        sys.exit(0)

    print("\nConnecting to Google Admin API...")
    service = get_service()

    print()
    success_count = 0
    skip_count = 0
    fail_count = 0

    for g in group_emails:
        ok, msg = add_member_to_group(service, g, user_email)
        if ok:
            print(f"  + {g} - {msg}")
            success_count += 1
        elif msg == "Already a member":
            print(f"  - {g} - {msg}")
            skip_count += 1
        else:
            print(f"  x {g} - {msg}")
            fail_count += 1

    print(f"\n{'=' * 44}")
    print(f"  Added: {success_count}  |  Skipped: {skip_count}  |  Failed: {fail_count}")
    print(f"{'=' * 44}")


if __name__ == "__main__":
    main()
