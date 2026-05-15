import os
from googleapiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'Keys', '.env')
load_dotenv(dotenv_path=env_path)

def create_directory_service():
	service_account_json_file_path = 'Email Signatures\service-account.json'
	credentials = ServiceAccountCredentials.from_json_keyfile_name(
		service_account_json_file_path,
		scopes=['https://www.googleapis.com/auth/admin.directory.user', 'https://www.googleapis.com/auth/admin.directory.group'])
	credz = credentials.create_delegated("admin@yourdomain.com")
	return build('admin', 'directory_v1', credentials=credz)

user = {         
         "primaryEmail":"test.user@yourdomain.com",
         "name":{
            "givenName":"Test",
            "familyName":"3",
            "fullName":"Test "},
         "orgUnitPath":"/Headquarters",
		 "password": os.environ["DEFAULT_EMP_PASSWORD"],
		 "changePasswordAtNextLogin":"true"
      }

service = create_directory_service()
response = results = service.users().insert(body=user).execute()

print(response)