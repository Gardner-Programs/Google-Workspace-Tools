"""Delete groups listed in a CSV file."""
import csv
import tkinter as tk
from tkinter import filedialog
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _master import get_service


def main():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title="Select CSV with group emails", filetypes=[("CSV Files", "*.csv")])
    if not file_path:
        print("No file selected. Exiting.")
        return

    groups = []
    with open(file_path, 'r') as f:
        reader = csv.reader(f)
        next(reader)
        for line in reader:
            groups.append(str(line[3]))

    print(f"Found {len(groups)} groups to delete.")
    confirm = input("Proceed? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    service = get_service()
    for email in groups:
        try:
            service.groups().delete(groupKey=email).execute()
            print(f"  Deleted: {email}")
        except Exception as e:
            print(f"  Error deleting {email}: {e}")


if __name__ == "__main__":
    main()
