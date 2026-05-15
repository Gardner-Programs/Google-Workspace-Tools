import os
from google.oauth2 import service_account
from oauth2client.service_account import ServiceAccountCredentials, oauth2client
from googleapiclient.discovery import build
import re, base64, gspread, pandas, imgkit, email,time
from datetime import datetime

_KEYS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'Keys')
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)
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

def get_unread(email):
	emails = []
	service = setup_credentials_gmail_code(email)
	result = service.users().messages().list(userId="me",maxResults=500, q="from:security@vendor.com Suspicious").execute()
	print(result)
	for id in result["messages"]:
		message = service.users().messages().get(userId="me", id=id["id"]).execute()
		if "Your Transport Pro verification code is: " in message["snippet"]:
			search = re.findall(r'code is: \d+', message["snippet"])
			code = str(search[0]).replace("code is: ", "")
	# nextPageToken = result.get('nextPageToken', {})
	# loop = True
	# while loop:
	# 	if nextPageToken:
	# 		loop_result = service.users().messages().list(userId="me",maxResults=500, q="in:inbox is:unread", pageToken=nextPageToken).execute()
	# 		if "messages" in loop_result:
	# 			unread+=len(loop_result["messages"])
	# 			nextPageToken = loop_result.get('nextPageToken', {})
	# 		if not nextPageToken:
	# 			loop = False
	# 			break

			

def get_blocklist(email):
	emails = []
	service = setup_credentials_gmail_code(email)
	result = service.users().messages().list(userId="me",maxResults=100, q="from:security@vendor.com Suspicious").execute()
	for x in result["messages"]:
		message = service.users().messages().get(userId="me", id=x["id"], format="raw").execute()
		data = base64.urlsafe_b64decode(message["raw"]).decode("utf-8")
		replace = str(data).replace("<", " ").replace("=","").replace(";","")
		mod_string = "".join(replace.splitlines())
		search = re.search(r'Email Address: \S+', mod_string)
		if str(search) != "None":
			id = str(search.group(0)).replace("Email Address: ", "")
			print(search[0])
		
		
		emails.append(id)		
	print(emails)	


def get_email(user_email, q):
	emails = []
	num = 1
	service = setup_credentials_gmail_code(user_email)
	result = service.users().messages().list(userId="me",maxResults=20, q=q).execute()
	print(len(result["messages"]))
	for x in reversed(result["messages"]):
		message = service.users().messages().get(userId="me", id=x["id"], format="raw").execute()
		data = base64.urlsafe_b64decode(message["raw"]).decode("utf-8")
		search_sub = re.search("^Subject.*",data,flags=re.MULTILINE)
		subject = search_sub.group(0).replace("Subject: ","")
		valid_chars = "-_.() {}[]abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
		sanitized = ''.join(c for c in subject if c in valid_chars)
		emailMessage = email.message_from_string(str(data))
		htmlContent = None
		for part in emailMessage.walk():
			if part.get_content_type() == "text/html":
				htmlContent = part.get_payload(decode=True).decode("utf-8")
				break
		if htmlContent:
			options = {'width': 1000, 'disable-smart-width': ''}
			imgkit.from_string(htmlContent, os.path.join(OUTPUT_DIR, "email"+str(num)+".jpg"),options=options)
			
		# with open("G:\My Drive\circle-workspace-tools\Email Search\email"+str(num)+".txt", "w") as f:
		# 	f.write(data)
		# print(data)
		num+=1



def sent_emails(user_email,q):
	service = setup_credentials_gmail_code(user_email)
	query = q
	count = 0
	nextPageToken = None
	result = service.users().messages().list(userId="me",maxResults=500, q=query).execute()
	count += len(result["messages"])
	loop = True
	if "nextPageToken" in result.keys():
		while loop:
			nextPageToken = result["nextPageToken"]
			result = service.users().messages().list(userId="me",maxResults=500, q=query, pageToken=nextPageToken).execute()
			count += len(result["messages"])
			if "nextPageToken" in result.keys():
				loop = True
			else:
				loop = False
				break		
	print(count)
	return count

get_email("user@yourdomain.com", "in:sent")

# sent_emails("user@yourdomain.com", "in:sent before:03/11/2024 after:03/09/2024")