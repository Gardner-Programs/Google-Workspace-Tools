import time
from customScripts.authenticator import drive_v3_api
from googleapiclient.errors import HttpError
from colorama import init, Fore

# Initialize colorama
init(autoreset=True)

# --- Configuration ---
SOURCE_OWNER_EMAIL = "offboarded@yourdomain.com"
TARGET_PARENT_ID = "0AHg0nc56KN0AUk9PVA"
SEARCH_QUERY_NAME = "yourdomain.com"

# Initialize Service
service = drive_v3_api(SOURCE_OWNER_EMAIL)

def remove_myself_from_item(item_id, item_name, is_folder=False):
    """
    Removes the current user's permission from a file OR folder.
    Returns: True if success, False if failed.
    """
    item_type = "folder" if is_folder else "file"
    try:
        # 1. Get permissions
        file_info = service.files().get(
            fileId=item_id, 
            fields="owners, permissions(id, emailAddress, role)",
            supportsAllDrives=True
        ).execute()

        # 2. Check Owner
        is_owner = False
        for owner in file_info.get('owners', []):
            if owner.get('emailAddress', '').lower() == SOURCE_OWNER_EMAIL.lower():
                is_owner = True
                break
        
        if is_owner:
            print(f"{Fore.RED}CRITICAL: Cannot remove access from {item_type} '{item_name}' - You are the OWNER.")
            return False

        # 3. Find permission ID
        my_permission_id = None
        for perm in file_info.get('permissions', []):
            if perm.get('emailAddress', '').lower() == SOURCE_OWNER_EMAIL.lower():
                my_permission_id = perm.get('id')
                break
        
        # 4. Delete permission
        if my_permission_id:
            service.permissions().delete(
                fileId=item_id, 
                permissionId=my_permission_id,
                supportsAllDrives=True
            ).execute()
            print(f"{Fore.MAGENTA}Success (Fallback): Removed access to shared {item_type} '{item_name}'")
            return True
        else:
            print(f"{Fore.RED}CRITICAL: Could not find permission for {SOURCE_OWNER_EMAIL} on '{item_name}'")
            return False

    except HttpError as error:
        print(f"{Fore.RED}CRITICAL: Error removing self from '{item_name}': {error.reason}")
        return False

def delete_folder_or_remove_access(folder_id, folder_name):
    """
    Attempts to delete the folder. 
    If deletion fails (e.g. not owner), attempts to remove access.
    """
    # Attempt 1: Delete
    try:
        service.files().delete(fileId=folder_id, supportsAllDrives=True).execute()
        print(f"{Fore.BLUE}Deleted source folder: {folder_name}")
        return True
    except HttpError as error:
        # Attempt 1 Failed -> Print ORANGE (Yellow) Warning
        print(f"{Fore.YELLOW}Warning: Could not delete folder '{folder_name}' ({error.reason}). Attempting to remove access...")
        
        # Attempt 2: Remove Access
        return remove_myself_from_item(folder_id, folder_name, is_folder=True)

def move_file(file_id, target_parent_id, file_name):
    """
    Attempts to move the file.
    Returns: True if successful, String (Error Message) if failed.
    """
    try:
        service.files().update(
            fileId=file_id,
            supportsAllDrives=True,
            addParents=target_parent_id,
            fields="id, parents"
        ).execute()
        print(f"{Fore.GREEN}Moved file: {file_name}")
        return True
    except HttpError as error:
        return str(error.reason)

def check_existing_destination(folder_name):
    """Checks if destination exists."""
    query = (
        f"name='{folder_name}' and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"'{TARGET_PARENT_ID}' in parents and trashed = false"
    )
    try:
        results = service.files().list(
            q=query, spaces='drive', 
            supportsAllDrives=True, 
            includeItemsFromAllDrives=True, 
            fields='files(id, name)'
        ).execute()
        files = results.get('files', [])
        return files[0]["id"] if files else None
    except HttpError as error:
        print(f"{Fore.RED}Error checking existence: {error.reason}")
        return None

def create_drive_folder(folder_name):
    """Creates destination folder or returns existing ID."""
    existing_id = check_existing_destination(folder_name)
    if existing_id:
        return existing_id
    
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [TARGET_PARENT_ID]
    }
    try:
        file = service.files().create(
            body=file_metadata, 
            supportsAllDrives=True, 
            fields='id'
        ).execute()
        print(f"{Fore.GREEN}Created folder {folder_name} (ID: {file.get('id')})")
        return file.get('id')
    except HttpError as error:
        print(f"{Fore.RED}Error creating folder {folder_name}: {error.reason}")
        return None

def process_recursive_contents(current_folder_id, target_folder_id):
    """
    Recursively moves files. Returns True only if all items were handled successfully.
    """
    all_ops_successful = True
    page_token = None

    while True:
        try:
            results = service.files().list(
                q=f"'{current_folder_id}' in parents and trashed = false",
                spaces='drive',
                fields='nextPageToken, files(id, name, mimeType)',
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
        except HttpError as error:
            print(f"{Fore.RED}Error listing folder {current_folder_id}: {error.reason}")
            return False

        items = results.get('files', [])
        if items:
            for item in items:
                # --- Sub-Folders ---
                if item["mimeType"] == "application/vnd.google-apps.folder":
                    sub_success = process_recursive_contents(item["id"], target_folder_id)
                    
                    if not sub_success:
                        all_ops_successful = False
                        print(f"{Fore.YELLOW}Skipping cleanup of folder '{item['name']}' due to errors inside.")
                    else:
                        # Contents moved safely. Now try to delete OR remove access to this sub-folder.
                        folder_cleaned = delete_folder_or_remove_access(item["id"], item["name"])
                        if not folder_cleaned:
                            all_ops_successful = False
                
                # --- Files ---
                else:
                    # Attempt 1: Move
                    move_result = move_file(item["id"], target_folder_id, item["name"])
                    
                    if move_result is True:
                        pass # Success
                    else:
                        # Attempt 1 Failed -> Print Warning
                        print(f"{Fore.YELLOW}Warning: Move failed for '{item['name']}' ({move_result}). Attempting fallback...")
                        
                        # Attempt 2: Remove Access
                        removed_access = remove_myself_from_item(item["id"], item["name"], is_folder=False)
                        
                        if not removed_access:
                            all_ops_successful = False

        page_token = results.get('nextPageToken', None)
        if not page_token:
            break

    return all_ops_successful

def run_cleanup_scan():
    """Main scanning loop."""
    changes_detected_in_scan = False
    page_token = None

    print(f"{Fore.CYAN}Starting scan for folders containing '{SEARCH_QUERY_NAME}'...")

    while True:
        try:
            # Note: We filter for 'me' in owners to target folders we control
            query = (
                f"mimeType = 'application/vnd.google-apps.folder' and "
                f"name contains '{SEARCH_QUERY_NAME}' and "
                f"'me' in owners and trashed = false"
            )
            results = service.files().list(
                q=query,
                orderBy="name",
                pageToken=page_token,
                fields="nextPageToken, files(id, name)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
        except HttpError as error:
            print(f"{Fore.RED}Fatal error listing root folders: {error.reason}")
            break

        files = results.get("files", [])
        
        for folder in files:
            print(f"{Fore.YELLOW}Processing Root Folder: {folder['name']}")
            target_id = create_drive_folder(folder['name'])
            
            if target_id:
                success = process_recursive_contents(folder['id'], target_id)
                
                if success:
                    # Try to delete the root folder, or remove access if delete fails
                    cleaned = delete_folder_or_remove_access(folder['id'], folder['name'])
                    if cleaned:
                        changes_detected_in_scan = True
                else:
                    print(f"{Fore.RED}Skipping cleanup of root {folder['name']} - some items inside failed processing.")

        page_token = results.get("nextPageToken")
        if not page_token:
            break
            
    return changes_detected_in_scan

# --- Main Loop ---
if __name__ == "__main__":
    while True:
        changes = run_cleanup_scan()
        if changes:
            print(f"\n{Fore.CYAN}Changes detected. Waiting 2 seconds then re-scanning...\n")
            time.sleep(2) 
            continue
        else:
            print(f"\n{Fore.CYAN}No changes detected. Exiting script.\n")
            break