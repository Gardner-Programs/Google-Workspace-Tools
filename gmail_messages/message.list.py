from customScripts.authenticator import gmail_v1_api, admin_directory_v1_api
import time

def list_email(email):
	service = gmail_v1_api(email)
	result = service.users().messages().list(userId="me",q="before:2018/1/1 in:trash").execute()
	print(result)

	


if __name__ == "__main__":
	list_email("gbarr@yourdomain.com")

