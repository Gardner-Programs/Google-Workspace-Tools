import subprocess,csv,os
from tkinter import filedialog
file_path = filedialog.askopenfilename(title = "Select CSV", filetypes=[("CSV", "*.csv")])
with open(file_path, "r") as csvfile:
		reader = csv.reader(csvfile)
		csv_list = list(reader)
print(csv_list)          
os.system("pause")          
for user in csv_list:
    if user["City"] == "Headquarters" and user["Physical Location"] == "Headquarters":
        powershell_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'Active_Directory', 'powershell', 'UserCreation.ps1')
        firstname=user["First Name"]
        lastname=user["Last Name"]
        orgU=input("\n1. Sales \n2. Track & Trace \n3. AccountManagement \n4. Recruiting \n5. Safety \n6. Billing \n7. HR \n8. Admin \n\nSelect Department for "+firstname+" "+lastname+" with title "+user["Title"]+"\n")

        powershell_script_vars = [firstname,lastname,orgU]

        p = subprocess.run(["powershell.exe", "-ExecutionPolicy", "Bypass", powershell_script] + powershell_script_vars)
        print(p)