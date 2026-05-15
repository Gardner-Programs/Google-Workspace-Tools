from customScripts.authenticator import calendar_v3_api
from datetime import datetime,timedelta
start_input = (datetime.now()-timedelta(days=1))
end_inpuit = datetime.now()
e_start = start_input.strftime("%Y-%m-%dT%H:%M:%SZ")
e_end = end_inpuit.strftime("%Y-%m-%dT%H:%M:%SZ")

def list_events(user):
	calendar_service = calendar_v3_api(user)
	events_list = calendar_service.events().list(calendarId="primary",pageToken=None,timeMax=e_end,timeMin=e_start).execute()
	for item in events_list["items"]:
		try:
			start = datetime.fromisoformat(item["start"]["dateTime"]).strftime("%m/%d/%Y, %H:%M")
		except:
			start = "No Start"
		e_id = item.get("id")
		summary = item.get("summary", "No summary")
		description = item.get("description","No description")
		print("\nID: "+e_id+"\nStart: "+start+"\nSummary: "+summary+"\nDescription: "+description)

def move_event(user,event_id,target_user):
	calendar_service = calendar_v3_api(user)
	move = calendar_service.events().move(calendarId="primary",eventId=event_id,destination=target_user).execute()
	print(move)

list_events("user@yourdomain.com")