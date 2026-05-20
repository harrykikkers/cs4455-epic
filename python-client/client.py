import sys
import requests
import urllib3

# Suppress SSL warning for self-signed localhost cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "https://localhost:3000"

# verify=False accepts self-signed dev certs (same as the C++ client with libcurl)
# In production this would be verify=True
VERIFY_SSL = "localhost" not in BASE_URL and "127.0.0.1" not in BASE_URL


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def register(username, email, password):
    resp = requests.post(f"{BASE_URL}/api/auth/register", json={
        "username": username,
        "email": email,
        "password": password,
    }, verify=VERIFY_SSL)
    resp.raise_for_status()
    return resp.json()


def login(username, password):
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": username,
        "password": password,
    }, verify=VERIFY_SSL)
    resp.raise_for_status()
    return resp.json()


def get_inbox(token):
    resp = requests.get(f"{BASE_URL}/api/messages/inbox",
                        headers=auth_headers(token), verify=VERIFY_SSL)
    resp.raise_for_status()
    return resp.json().get("data", [])


def get_sent(token):
    resp = requests.get(f"{BASE_URL}/api/messages/sent",
                        headers=auth_headers(token), verify=VERIFY_SSL)
    resp.raise_for_status()
    return resp.json().get("data", [])


def get_message(token, message_id):
    resp = requests.get(f"{BASE_URL}/api/messages/{message_id}",
                        headers=auth_headers(token), verify=VERIFY_SSL)
    resp.raise_for_status()
    return resp.json().get("data", {})


def delete_message(token, message_id):
    resp = requests.delete(f"{BASE_URL}/api/messages/{message_id}",
                           headers=auth_headers(token), verify=VERIFY_SSL)
    resp.raise_for_status()


def main():
    print(f"=== Epic Secure Messenger ===")
    print(f"Server: {BASE_URL}\n")

    mode = input("1) Register  2) Login\n> ").strip()
    username = input("Username: ").strip()
    password = input("Password: ").strip()

    if mode == "1":
        email = input("Email: ").strip()
        register(username, email, password)
        print("Registered successfully.")

    login_resp = login(username, password)
    token = login_resp["data"]["token"]
    user_id = login_resp["data"]["user"]["id"]
    print(f"Logged in. User ID: {user_id}")

    while True:
        print("\n1) View inbox\n2) View sent\n3) Get message by ID\n4) Delete message\n5) Quit")
        choice = input("> ").strip()

        if choice == "1":
            messages = get_inbox(token)
            if not messages:
                print("No messages.")
            for m in messages:
                print(f"  [{m['created_at']}]  from={m['sender_id']}  id={m['id']}")
                print(f"  (end-to-end encrypted)")

        elif choice == "2":
            messages = get_sent(token)
            if not messages:
                print("No sent messages.")
            for m in messages:
                print(f"  [{m['created_at']}]  to={m['recipient_id']}  id={m['id']}")

        elif choice == "3":
            msg_id = input("Message ID: ").strip()
            m = get_message(token, msg_id)
            print(f"  from={m.get('sender_id')}  at={m.get('created_at')}")
            print(f"  (end-to-end encrypted)")

        elif choice == "4":
            msg_id = input("Message ID: ").strip()
            delete_message(token, msg_id)
            print("Deleted.")

        elif choice == "5":
            break

        else:
            print("Unknown option.")


if __name__ == "__main__":
    main()
