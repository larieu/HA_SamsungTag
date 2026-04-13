# Samsung SmartTag2 Battery Monitor for Home Assistant

Monitor your Samsung SmartTag2 battery level in Home Assistant using the SmartThings API.

## How it works

A Python script reads the battery level directly from the SmartThings REST API using OAuth credentials obtained from the SmartThings CLI. The script handles token refresh automatically — no browser, no CLI at runtime.

The sensor is polled every 6 hours via HA's `command_line` integration.

---

## Prerequisites

- Home Assistant OS (hassio) running as a VM (e.g. Proxmox)
- SSH access to the HA host (e.g. via the **Advanced SSH & Web Terminal** add-on)
- A Linux computer with a browser (for the one-time SmartThings login)
- `npm` installed on your computer
- Your SmartTag2 already paired in the SmartThings app

---

## Part 1 — Authenticate on your computer (one-time)

The SmartThings CLI requires a browser for its OAuth flow. Do this once on your computer.

### 1.1 Install the SmartThings CLI

```bash
sudo npm install -g @smartthings/cli
```

### 1.2 Authenticate

```bash
smartthings devices
```

A browser window will open asking you to log in to Samsung. After login, the CLI saves credentials automatically. Confirm it works — you should see your devices listed including your SmartTag2.

### 1.3 Find the credentials file and your Device ID

```bash
cat /home/$USER/.local/share/@smartthings/cli/credentials.json
```

Also note the **Device ID** of your SmartTag2 from the device list — it looks like `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`. You will need it in Part 6.

---

## Part 2 — Set up the folder structure on HA

SSH into your HA instance and create the required directories:

```bash
mkdir -p /config/scripts/smarttag/.smartthings
mkdir -p /config/scripts/smarttag/bin
```

---

## Part 3 — Install Node.js on HA

HA OS uses musl libc (Alpine-based), so you need the musl build of Node.js. The standard glibc builds will not work.

```bash
cd /config/scripts/smarttag/bin

# Download musl build of Node.js v20
curl -L -o node.tar.xz \
  https://unofficial-builds.nodejs.org/download/release/v20.11.0/node-v20.11.0-linux-x64-musl.tar.xz

# Extract
tar -xJf node.tar.xz

# Verify
./node-v20.11.0-linux-x64-musl/bin/node --version
```

---

## Part 4 — Install the SmartThings CLI on HA

Still in `/config/scripts/smarttag/bin`, add node to PATH for this session and install the CLI locally:

```bash
export PATH="/config/scripts/smarttag/bin/node-v20.11.0-linux-x64-musl/bin:$PATH"
npm install @smartthings/cli
```

> Note: the `export PATH=...` above is session-only. The wrapper script below makes the correct Node binary available for every CLI invocation permanently.

### 4.1 Create the wrapper script

```bash
cat << 'EOF' > /config/scripts/smarttag/bin/smartthings
#!/bin/bash
export PATH="/config/scripts/smarttag/bin/node-v20.11.0-linux-x64-musl/bin:$PATH"
unset SMARTTHINGS_TOKEN
/config/scripts/smarttag/bin/node_modules/.bin/smartthings "$@"
EOF

chmod +x /config/scripts/smarttag/bin/smartthings
```

### 4.2 Verify the CLI works

```bash
/config/scripts/smarttag/bin/smartthings --version
```

---

## Part 5 — Copy credentials from your computer to HA

On your **computer**, copy the credentials file to HA via scp:

```bash
scp /home/$USER/.local/share/@smartthings/cli/credentials.json \
    root@<HA_IP>:/config/scripts/smarttag/.smartthings/credentials.json
```

Also copy to the system location the CLI uses as fallback:

```bash
ssh root@<HA_IP> "mkdir -p /root/.local/share/@smartthings/cli"

scp /home/$USER/.local/share/@smartthings/cli/credentials.json \
    root@<HA_IP>:/root/.local/share/@smartthings/cli/credentials.json
```

### 5.1 Verify on HA

```bash
/config/scripts/smarttag/bin/smartthings devices
```

You should see your SmartTag2 listed.

---

## Part 6 — The Python script

This script calls the SmartThings API directly using Python's standard library — no CLI, no Node.js at runtime. It handles token refresh automatically when the access token expires, writing the new tokens back to `credentials.json`.

> **Why not call the CLI from Python?**  
> The SmartThings CLI requires an interactive TTY and will hang indefinitely when spawned as a subprocess from HA's `command_line` integration, which runs in a headless environment. The direct API approach avoids this entirely.

Create `/config/scripts/smarttag/tag_battery.py`:

```python
import json
import urllib.request
import urllib.parse
import urllib.error

CREDENTIALS_FILE = "/config/scripts/smarttag/.smartthings/credentials.json"
DEVICE_ID = "your-device-id-here"  # Replace with your SmartTag2 device ID

def load_credentials():
    with open(CREDENTIALS_FILE) as f:
        data = json.load(f)
    return data["default:api.smartthings.com"]

def save_credentials(creds):
    data = {"default:api.smartthings.com": creds}
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def refresh_token(creds):
    url = "https://auth-global.api.smartthings.com/oauth/token"
    # client_id is the SmartThings CLI's public OAuth client ID.
    # If refresh ever stops working, verify it at:
    # https://github.com/SmartThingsCommunity/smartthings-cli
    payload = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": creds["refreshToken"],
        "client_id": "727cbe60-5a9b-4b8b-b977-8b2f50e97f6e"
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def get_battery(access_token):
    url = f"https://api.smartthings.com/v1/devices/{DEVICE_ID}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["bleD2D"]["metadata"]["battery"]["level"].upper()

def get_tag_battery():
    try:
        creds = load_credentials()
        try:
            return get_battery(creds["accessToken"])
        except urllib.error.HTTPError as e:
            if e.code == 401:
                new_tokens = refresh_token(creds)
                creds["accessToken"] = new_tokens["access_token"]
                creds["refreshToken"] = new_tokens["refresh_token"]
                save_credentials(creds)
                return get_battery(creds["accessToken"])
            raise
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    print(get_tag_battery())
```

Make it executable:

```bash
chmod +x /config/scripts/smarttag/tag_battery.py
```

### 6.1 Test the script

```bash
python3 /config/scripts/smarttag/tag_battery.py
# Expected output: FULL, NORMAL, or LOW
```

Also verify it works in a minimal environment that simulates how HA runs it:

```bash
env -i HOME=/hassio \
  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  python3 /config/scripts/smarttag/tag_battery.py
# Should return FULL, NORMAL, or LOW — not an error or timeout
```

Both should return the same result instantly.

---

## Part 7 — Home Assistant configuration

Add the following to `/config/configuration.yaml`:

```yaml
command_line:
  - sensor:
      name: "SmartTag2 TAG1 Battery"
      unique_id: smarttag2_tag1_bat
      command: "python3 /config/scripts/smarttag/tag_battery.py"
      scan_interval: 21600
      command_timeout: 60
      value_template: "{{ value }}"
      icon: >
        {% if value == 'FULL' %} mdi:battery
        {% elif value == 'NORMAL' %} mdi:battery-60
        {% elif value == 'LOW' %} mdi:battery-20
        {% else %} mdi:battery-alert
        {% endif %}
```

Restart HA or reload the configuration. The sensor will appear as `sensor.smarttag2_tag1_battery`.

To force an immediate update without waiting 6 hours:  
**Developer Tools → Actions → `homeassistant.update_entity`** → enter `sensor.smarttag2_tag1_battery`.

---

## Final folder structure

```
/config/scripts/smarttag/
├── .smartthings/
│   └── credentials.json                  # OAuth credentials (copied from computer)
├── bin/
│   ├── node-v20.11.0-linux-x64-musl/    # Node.js musl build
│   ├── node_modules/                     # SmartThings CLI npm package
│   ├── node.tar.xz                       # (can be deleted after extraction)
│   ├── package.json
│   ├── package-lock.json
│   └── smartthings                       # Wrapper shell script
└── tag_battery.py                        # The HA sensor script
```

---

## Troubleshooting

### 401 Unauthorized
The access token has expired and automatic refresh failed. Re-run the CLI on your computer to get a fresh token, then copy the credentials file to HA again:

```bash
# On your computer
smartthings devices

scp /home/$USER/.local/share/@smartthings/cli/credentials.json \
    root@<HA_IP>:/config/scripts/smarttag/.smartthings/credentials.json
```

### Sensor shows UNKNOWN
The script returned an empty or unexpected value. Run it manually from the HA SSH terminal to see the actual output:

```bash
python3 /config/scripts/smarttag/tag_battery.py
```

### Sensor shows an error message instead of FULL / NORMAL / LOW
The script returns `str(e)` so you can read the error directly in the HA UI during initial setup. Once everything is working you can change the last `except` line to `return "ERROR"` if you prefer a clean fallback.

---

## Token refresh notes

- The OAuth **access token** expires roughly every 24 hours
- The **refresh token** stays valid as long as it is used regularly
- The Python script refreshes automatically on 401 — no manual intervention needed
- With HA polling every 6 hours, the refresh token will never go stale
- If you revoke app access in Samsung account settings, you will need to re-authenticate from scratch on your computer (Part 1) and repeat Part 5
