import os
from google.oauth2 import service_account
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
import re, base64, gspread, pandas
from datetime import datetime

_KEYS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'Keys')
env_path = os.path.join(_KEYS_DIR, '.env')

def sheets_credentials():
	service_account_json_file_path = os.path.join(_KEYS_DIR, 'service-account.json') #"YOUR_KEY_PATH/service-account.json"
	credentials = ServiceAccountCredentials.from_json_keyfile_name(service_account_json_file_path,scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive", "https://spreadsheets.google.com/feeds"])
	return credentials

def setup_credentials_gmail_code(email):
		key_path = os.path.join(_KEYS_DIR, 'service-account.json')
		API_scopes =["https://www.googleapis.com/auth/gmail.readonly", "https://mail.google.com/", "https://www.googleapis.com/auth/gmail.modify"]
		credentials = service_account.Credentials.from_service_account_file(key_path,scopes=API_scopes)
		credentials_delegated = credentials.with_subject(email)
		return build("gmail","v1",credentials=credentials_delegated)


def get_tp_code(email):
	service = setup_credentials_gmail_code(email)
	result = service.users().messages().list(userId="me",maxResults=5).execute()
	for x in result["messages"]:
		message = service.users().messages().get(userId="me", id=x["id"]).execute()
		if "Your verification code is: " in message["snippet"]:
			search = re.findall(r'code is: \d+', message["snippet"])
			code = str(search[0]).replace("code is: ", "")
			epoch = int(message["internalDate"])/1000
			time = datetime.fromtimestamp(epoch)
			return (code, time)
	return "No code found."

def delete_email(email, id):
	service = setup_credentials_gmail_code(email)
	result = service.users().messages().list(userId="me",maxResults=20).execute()
	for x in result["messages"]:
		message = service.users().messages().get(userId="me", id=x["id"]).execute()
		for y in message["payload"]["headers"]:
			if y["value"] == id:
				service.users().messages().delete(userId="me", id=x["id"]).execute()

def get_email(email):
	service = setup_credentials_gmail_code(email)
	result = service.users().messages().list(userId="me",maxResults=100).execute()
	for x in result["messages"]:
		message = service.users().messages().get(userId="me", id=x["id"]).execute()
		for x in message["payload"]["headers"]:
			if "From" in x["name"] or "Subject" in x["name"]:
				print(x["name"], x["value"])
		print("\n")


