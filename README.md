# Samsung SmartTag2 Battery Monitor for Home Assistant

Monitor your Samsung SmartTag2 battery level in Home Assistant using the SmartThings API.

## How it works

A Python script authenticates with the SmartThings API using your own OAuth app credentials. On every run it refreshes the access token automatically and saves the new tokens back to disk — so it never expires and never needs manual intervention.

The sensor is polled every hour via HA's `command_line` integration.

---

## Why this approach

- The official SmartThings HA integration does not expose Tag2 battery data
- SmartThings Personal Access Tokens (PATs) expire after 24 hours by design
- The SmartThings CLI hangs in headless environments (no TTY) and its shared OAuth client ID is not reliable for long-running integrations
- A registered OAuth app gives you your own `client_id` and `client_secret`, with refresh tokens that rotate on every use and never expire as long as they are used regularly

---

## Prerequisites

- Home Assistant OS (hassio) running as a VM (e.g. Proxmox)
- SSH access to the HA host (e.g. via the **Advanced SSH & Web Terminal** add-on)
- A computer with a browser and the SmartThings CLI installed (for the one-time app setup)
- Your SmartTag2 already paired in the SmartThings app

### Install the SmartThings CLI on your computer (if not already done)

```bash
sudo npm install -g @smartthings/cli
```

---

## Part 1 — Create your OAuth app (one-time, on your computer)

### 1.1 Create the app

```bash
smartthings apps:create
```

Answer the prompts as follows:

- **App type**: OAuth-In App
- **Display Name**: HA SmartTag Bridge (or any name you prefer)
- **Description**: anything
- **Icon URL**: leave blank
- **Target URL**: leave blank
- **Scopes**: select `r:devices:*`, `w:devices:*`, `x:devices:*`, `r:locations:*`, `w:locations:*`, `x:locations:*`
- **Redirect URI**: `https://httpbin.org/get`

At the end you will see:

```
OAuth Client Id      xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
OAuth Client Secret  xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**Save these immediately** — the secret is shown only once.

### 1.2 Authorize the app and get your first tokens

Open this URL in your browser (replace `YOUR_CLIENT_ID`):

```
https://api.smartthings.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=https://httpbin.org/get&scope=r:devices:*%20x:devices:*%20r:locations:*%20x:locations:*
```

Log in with your Samsung account and authorize the app. You will be redirected to a page that shows the request parameters as JSON. Find the `code` value — it looks like `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`.

### 1.3 Exchange the code for tokens

Run this on your computer (replace the placeholders):

```bash
curl -s -u "YOUR_CLIENT_ID:YOUR_CLIENT_SECRET" \
  -X POST https://api.smartthings.com/oauth/token \
  -d "grant_type=authorization_code&code=YOUR_CODE&redirect_uri=https://httpbin.org/get"
```

You will receive a JSON response containing `access_token` and `refresh_token`. Save both.

### 1.4 Find your SmartTag2 Device ID

```bash
smartthings devices
```

Note the **Device Id** of your SmartTag2 — format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`.

---

## Part 2 — Set up files on HA

SSH into your HA instance.

### 2.1 Create the folder

```bash
mkdir -p /config/scripts/smarttag
```

### 2.2 Create the tokens file

```bash
cat << 'EOF' > /config/scripts/smarttag/tokens.json
{
  "access_token": "PASTE_YOUR_ACCESS_TOKEN_HERE",
  "refresh_token": "PASTE_YOUR_REFRESH_TOKEN_HERE"
}
EOF
```

### 2.3 Create the Python script

Create `/config/scripts/smarttag/refresh_tag.py`:

```python
import json
import subprocess
import os

CLIENT_ID     = "your-client-id-here"
CLIENT_SECRET = "your-client-secret-here"
DEVICE_ID     = "your-device-id-here"
TOKEN_FILE    = "/config/scripts/smarttag/tokens.json"

def run_curl(cmd):
    return subprocess.check_output(cmd, shell=True).decode("utf-8")

with open(TOKEN_FILE, "r") as f:
    tokens = json.load(f)

# Step 1 — Refresh the access token
refresh_cmd = (
    f"curl -s -u '{CLIENT_ID}:{CLIENT_SECRET}' "
    f"-X POST https://api.smartthings.com/oauth/token "
    f"-d 'grant_type=refresh_token&refresh_token={tokens['refresh_token']}'"
)
try:
    resp = json.loads(run_curl(refresh_cmd))
    if "access_token" in resp:
        tokens["access_token"]  = resp["access_token"]
        tokens["refresh_token"] = resp["refresh_token"]
        with open(TOKEN_FILE, "w") as f:
            json.dump(tokens, f)
except Exception:
    pass

# Step 2 — Get device data
detail_cmd = (
    f"curl -s -H 'Authorization: Bearer {tokens['access_token']}' "
    f"https://api.smartthings.com/v1/devices/{DEVICE_ID}"
)
data = json.loads(run_curl(detail_cmd))

# Step 3 — Extract battery level
val = None
try:
    val = data["bleD2D"]["metadata"]["battery"]["level"]
except KeyError:
    try:
        status_cmd = (
            f"curl -s -H 'Authorization: Bearer {tokens['access_token']}' "
            f"https://api.smartthings.com/v1/devices/{DEVICE_ID}/status"
        )
        status_data = json.loads(run_curl(status_cmd))
        val = status_data["components"]["main"]["battery"]["battery"]["value"]
    except Exception:
        val = "UNKNOWN"

print(val if val is not None else "UNKNOWN")
```

### 2.4 Test the script

```bash
python3 /config/scripts/smarttag/refresh_tag.py
# Expected output: FULL, NORMAL, or LOW
```

Also confirm the tokens are being rotated — run the script twice and check that `access_token` changes:

```bash
cat /config/scripts/smarttag/tokens.json
python3 /config/scripts/smarttag/refresh_tag.py
cat /config/scripts/smarttag/tokens.json
# The access_token and refresh_token values should be different after the second cat
```

---

## Part 3 — Home Assistant configuration

Add to `/config/configuration.yaml`:

```yaml
command_line:
  - sensor:
      name: "SmartTag2 Tag01 Battery"
      unique_id: "smarttag2_tag01_battery"
      command: "python3 /config/scripts/smarttag/refresh_tag.py"
      scan_interval: 3600
      command_timeout: 30
      value_template: "{{ value }}"
      icon: >
        {% if value == 'FULL' %} mdi:battery
        {% elif value == 'NORMAL' %} mdi:battery-60
        {% elif value == 'LOW' %} mdi:battery-20
        {% else %} mdi:battery-alert
        {% endif %}
```

Restart HA or reload the configuration. The sensor will appear as `sensor.smarttag2_tag01_battery`.

To force an immediate update:
**Developer Tools → Actions → `homeassistant.update_entity`** → enter `sensor.smarttag2_tag01_battery`.

---

## Final folder structure

```
/config/scripts/smarttag/
├── refresh_tag.py    # The sensor script
└── tokens.json       # OAuth tokens (auto-updated on every run)
```

---

## Troubleshooting

### Sensor shows UNKNOWN or an error message
Run the script manually and check the output:
```bash
python3 /config/scripts/smarttag/refresh_tag.py
```

### tokens.json stops updating
The refresh token may have been invalidated — this can happen if you revoke the app in Samsung account settings or if the token goes unused for an extended period. Repeat the authorization step from Part 1.2 to get a new code, then run the curl command from Part 1.3 to get fresh tokens and update `tokens.json` manually.

### Multiple tags
For each additional tag, create a separate script file (e.g. `refresh_tag2.py`) with a different `DEVICE_ID` and a separate `tokens.json` (e.g. `tokens2.json`). Add a corresponding sensor entry in `configuration.yaml`.

---

## Token refresh notes

- The access token is refreshed on **every script run** (every hour by default)
- Each refresh returns a new `access_token` and a new `refresh_token`, both saved back to `tokens.json`
- The refresh token never expires as long as it is used regularly
- Tokens are stored in `/config` which persists across HA reboots
- No CLI, no Node.js, no browser needed after the initial setup
