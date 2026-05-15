"""List all org units in the domain with their IDs."""
from customScripts.authenticator import admin_directory_v1_api


def main():
    service = admin_directory_v1_api()
    result = service.orgunits().list(customerId="my_customer", type="all").execute()
    for ou in result.get("organizationUnits", []):
        print(f"{ou['orgUnitId']}  {ou['orgUnitPath']}")


if __name__ == "__main__":
    main()
