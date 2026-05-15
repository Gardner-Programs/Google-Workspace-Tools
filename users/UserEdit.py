from customScripts.authenticator import admin_directory_v1_api

key="admin@yourdomain.com"
service = admin_directory_v1_api()
results = service.users().update(userKey=key, body={'organizations': [{'title': 'Representative','department': 'Fort Blaine', 'primary': True, 'customType': ''}],'addresses': [{'type': 'home', 'formatted': 'New Home Address'}], 'phones': [{'value': '1010', 'type': 'work'}]}).execute()

