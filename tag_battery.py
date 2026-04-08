import requests
import json
import os

CONFIG_PATH = "/config/scripts/smarttag/config.json"

def rotate_and_get():
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)

    # 1. Exchange Refresh Token for a fresh Access Token
    token_url = "https://api.smartthings.com/oauth/token"
    token_data = {
        "grant_type": "refresh_token",
        "client_id": config['client_id'],
        "refresh_token": config['refresh_token']
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    token_res = requests.post(token_url, data=token_data, headers=headers)
    
    if token_res.status_code != 200:
        # If refresh fails, the token might still be valid (like today)
        # Or it might be totally expired. We'll try one last 'hail mary' 
        # using the current refresh_token as a bearer just in case.
        print("Refresh skipped or failed, attempting direct fetch...")
        access_token = config.get('access_token', '7a6c5969-35a1-4cf6-a0cf-d4dbf21317fc')
    else:
        data = token_res.json()
        access_token = data['access_token']
        # 2. SAVE the new refresh token for next time!
        config['refresh_token'] = data['refresh_token']
        config['access_token'] = access_token
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=4)

    # 3. Get the Battery Data
    device_url = f"https://api.smartthings.com/v1/devices/{config['device_id']}"
    auth_headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.smartthings+json;v=1"
    }
    
    res = requests.get(device_url, headers=auth_headers).json()

    try:
        level = res['bleD2D']['metadata']['battery']['level']
        # Convert SmartThings text to something HA likes (Optional)
        # FULL -> 100, NORMAL -> 50, LOW -> 10
        print(level)
    except KeyError:
        print("Unknown")

if __name__ == "__main__":
    rotate_and_get()
