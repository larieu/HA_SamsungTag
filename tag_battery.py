import requests
import json
import os

CONFIG_PATH = "/config/scripts/smarttag/config.json"

def rotate_and_get():
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)

    token_url = "https://api.smartthings.com/oauth/token"
    token_data = {
        "grant_type": "refresh_token",
        "client_id": config['client_id'],
        "refresh_token": config['refresh_token']
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    token_res = requests.post(token_url, data=token_data, headers=headers)
    
    # Use existing token if refresh isn't needed/fails
    access_token = config.get('access_token', '7a6c5969-35a1-4cf6-a0cf-d4dbf21317fc')

    if token_res.status_code == 200:
        data = token_res.json()
        access_token = data['access_token']
        config['refresh_token'] = data['refresh_token']
        config['access_token'] = access_token
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=4)

    device_url = f"https://api.smartthings.com/v1/devices/{config['device_id']}"
    auth_headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.smartthings+json;v=1"
    }
    
    try:
        res = requests.get(device_url, headers=auth_headers).json()
        level = res['bleD2D']['metadata']['battery']['level']
        print(level) # THIS MUST BE THE ONLY PRINT IN THE SCRIPT
    except:
        print("UNKNOWN")

if __name__ == "__main__":
    rotate_and_get()
