from customScripts.authenticator import gmail_v1_api, admin_directory_v1_api
import time
from colorama import init, Fore
init()

def start_group(group,message_id):
	service = admin_directory_v1_api()
	result = service.members().list(groupKey=group).execute()
	emails = [{"Email":member["email"]} for member in result["members"]]
	for email in emails:
		mass_delete_email(email["Email"],message_id)

def start(message_id):
	service = admin_directory_v1_api()
	result = service.users().list(domain="yourdomain.com", maxResults = 500, orderBy="email").execute()
	for user in result["users"]:
		if user["suspended"] == False and user["orgUnitPath"] != "/Non-User Accounts":
			mass_delete_email(user["primaryEmail"],message_id)
	nextPageToken = result.get("nextPageToken", {})
	loop = True
	while loop:
		if nextPageToken:
			loop_result = service.users().list(domain="yourdomain.com", pageToken = nextPageToken, maxResults = 500, orderBy="email").execute()
			for user in loop_result["users"]:
				if user["suspended"] == False and user["orgUnitPath"] != "/Non-User Accounts":
					mass_delete_email(user["primaryEmail"],message_id)
			nextPageToken = loop_result.get("nextPageToken", {})
			if not nextPageToken:
				loop = False
				break    

def mass_delete_email(email,message_id):
	time.sleep(.1)
	try:
		service = gmail_v1_api(email)
		result = service.users().messages().list(userId="me",q="rfc822msgid:"+message_id).execute()
	except:
		time.sleep(3)
		service = gmail_v1_api(email)
		result = service.users().messages().list(userId="me",q="rfc822msgid:"+message_id).execute()
	try:
		id = result["messages"][0]["id"]
		deleted = service.users().messages().delete(userId="me",id=id).execute()
		print(Fore.GREEN+email,deleted)
	except:
		print(Fore.RED+email+" has none")
		pass


def empyty_trash(email):
	service = gmail_v1_api(email)
	result = service.users().messages().list(userId="me",q="in:trash").execute()
	while True:
		time.sleep(.17)
		next_page = result.get("nextPageToken",None)
		print(result)
		for message in result["messages"]:
			id = message.get("id",None)
			failed = ""
			time.sleep(0.17)
			if id:
				try:
					deleted = service.users().messages().delete(userId="me",id=id).execute()
				except:
					time.sleep(1.5)
					try:
						deleted = service.users().messages().delete(userId="me",id=id).execute()
					except:
						failed = " failed."
			else:
				pass
			print(id+failed)
		if next_page:
			result = service.users().messages().list(userId="me",q="in:trash",pageToken=next_page).execute()
		else:
			break
	
	


if __name__ == "__main__":
	start("<YOUR_MESSAGE_ID>")
	# message_id = input("Type Message ID> ")
	# start(message_id)

