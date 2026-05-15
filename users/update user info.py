from customScripts.authenticator import admin_directory_v1_api, gmail_v1_api
from email.mime.text import MIMEText
import base64
import time
from datetime import datetime
import tkinter as tk
from tkinter import filedialog
import csv
import sys

users = []

def get_active_users():
    """
    Fetches all active users from the domain.
    """
    service = admin_directory_v1_api()
    excluded_ous = ["/Non-User Accounts", "/Offboarded Employees", "/All Sites/Data Hold"]
    user_list = []
    
    print("Fetching active users from Google Workspace...")
    request = service.users().list(
        domain="yourdomain.com", 
        maxResults=500, 
        orderBy="email", 
        query="isSuspended=false"
    )
    
    while request:
        result = request.execute()
        batch = result.get("users", [])
        for user in batch:
            if user.get("orgUnitPath") not in excluded_ous:
                user_list.append(user)
        request = service.users().list_next(previous_request=request, previous_response=result)
        
    return user_list

def select_csv_file():
    """
    Opens a file dialog to select the CSV file.
    """
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    file_path = filedialog.askopenfilename(
        title="Select User CSV File",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
    )
    return file_path

def update_managers_from_csv(csv_path, active_users_list):
    """
    Reads the CSV and updates manager fields.
    """
    service = admin_directory_v1_api()
    
    # Create a set of active user emails for quick lookup (lowercase for case-insensitive comparison)
    active_emails = {u['primaryEmail'].lower() for u in active_users_list}
    
    try:
        # Open the CSV file
        with open(csv_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            
            # Verify headers exist
            headers = reader.fieldnames
            if 'Email' not in headers or 'DirectReport' not in headers:
                print("Error: CSV must contain 'Email' and 'DirectReport' columns.")
                return

            print(f"Processing file: {csv_path}...")
            
            for row in reader:
                user_email = row.get('Email', '').strip()
                manager_email = row.get('DirectReport', '').strip()

                # Basic validation
                if not user_email or not manager_email:
                    continue
                
                # Check if user exists in the active users list we fetched
                if user_email.lower() in active_emails:
                    try:
                        print(f"Updating manager for {user_email} to {manager_email}...")
                        
                        # Prepare the update body
                        body = {
                            "relations": [
                                {
                                    "value": manager_email,
                                    "type": "manager"
                                }
                            ]
                        }
                        
                        # Execute the update
                        service.users().patch(userKey=user_email, body=body).execute()
                        print(f"SUCCESS: Updated {user_email}")
                        
                    except Exception as e:
                        print(f"FAILED to update {user_email}. Error: {e}")
                else:
                    print(f"SKIPPING: {user_email} (Not found in active user list or excluded OU)")

    except FileNotFoundError:
        print("Error: File not found.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # 1. Get Active Users
    users = get_active_users()
    print(f"Found {len(users)} active users.")

    # 2. Select CSV
    print("Please select the CSV file...")
    csv_file_path = select_csv_file()

    if csv_file_path:
        # 3. Process Updates
        update_managers_from_csv(csv_file_path, users)
        print("Done.")
    else:
        print("No file selected. Exiting.")