import json
import os
from customScripts.authenticator import cloud_identity_v1_api

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def export_google_devices():
    print("--- STARTING GOOGLE DEVICE EXPORT ---")
    ci_service = cloud_identity_v1_api()
    all_devices = []
    page_num = 1
    
    try:
        # We use NO filter here so we can see the "junk" and the "good" data side-by-side
        request = ci_service.devices().list(
            customer="customers/my_customer", 
            pageSize=100
        )
        
        while request:
            print(f"Fetching Page {page_num}...")
            result = request.execute()
            devices = result.get("devices", [])
            all_devices.extend(devices)
            
            request = ci_service.devices().list_next(previous_request=request, previous_response=result)
            page_num += 1

        # Save to a local JSON file
        with open(os.path.join(OUTPUT_DIR, "google_devices.json"), "w") as f:
            json.dump(all_devices, f, indent=4)
            
        print(f"\nSUCCESS: Exported {len(all_devices)} devices to 'google_devices.json'")
        print("Open this file to see which fields (like 'deviceType' or 'osVersion') we can use for a filter.")

    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    export_google_devices()