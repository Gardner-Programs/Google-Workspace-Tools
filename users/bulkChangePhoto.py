"""Bulk update user profile photos from a folder of headshot images."""
import os
import base64
import csv
import tkinter as tk
from tkinter import filedialog
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_service


def main():
    root = tk.Tk()
    root.withdraw()

    # Select CSV with email mappings
    csv_path = filedialog.askopenfilename(title="Select CSV (Name, Email)", filetypes=[("CSV Files", "*.csv")])
    if not csv_path:
        print("No CSV selected. Exiting.")
        return

    emails = []
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        next(reader)
        for line in reader:
            emails.append({"Name": str(line[1]).lower(), "Email": str(line[0]).lower()})

    # Select photo folder
    photo_dir = filedialog.askdirectory(title="Select folder containing headshot images")
    if not photo_dir:
        print("No folder selected. Exiting.")
        return

    files = os.listdir(photo_dir)
    service = get_service()
    errors = []

    for filepath in files:
        # Try to match filename to email
        formatted = filepath.replace("1-", "").lower()
        formatted = formatted.replace("-", ".")
        formatted = formatted.replace(".jpg", "@yourdomain.com")

        for entry in emails:
            if entry["Email"] == formatted:
                try:
                    full_path = os.path.join(photo_dir, filepath)
                    with open(full_path, "rb") as image_file:
                        data = base64.urlsafe_b64encode(image_file.read()).decode('ascii')
                    user_photo = {"kind": "admin#directory#user#photo", "photoData": data, "mimeType": "JPG"}
                    service.users().photos().update(userKey=entry["Email"], body=user_photo).execute()
                    print(f"  Updated: {entry['Name']}")
                except Exception as e:
                    print(f"  Error for {entry['Name']}: {e}")
                    errors.append(entry)
                break

    if errors:
        print(f"\n{len(errors)} errors:")
        for e in errors:
            print(f"  {e['Email']}")


if __name__ == "__main__":
    main()
