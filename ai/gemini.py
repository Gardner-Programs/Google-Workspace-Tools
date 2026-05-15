# pip install google-generativeai
import google.generativeai as genai
from google.generativeai import GenerativeModel
from customScripts.authenticator import gmail_v1_api

API_KEY=os.environ["API_KEY"]
client = genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')
convo = True
user_parts = []
model_parts = []
chat = model.start_chat()
while convo:
    print("\033[1m")
    text = input("> ")
    print("\033[0m")
    user_parts.append({"text":text})
    if text == "end":
        convo = False
        break
    response = chat.send_message(text)
    model_parts.append({"text":response.text})

    context = [{"role" : "user","parts" : user_parts,},{"role" : "model","parts" : model_parts}]
    chat = model.start_chat(history=context)

    print(response.text)