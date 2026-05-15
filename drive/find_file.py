from customScripts.authenticator import drive_v2_api,drive_v3_api
service = drive_v3_api("user@yourdomain.com")
files = service.files().list(q="name contains 'track' and 'me' in owners and trashed = false",orderBy="name").execute()
# result = service.files().list(q="Recruiting",spaces='drive',supportsAllDrives=True,includeItemsFromAllDrives=True,fields='files(id, name)').execute()
for file in files["files"]:
    print(file["name"])
