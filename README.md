# Samsung SmartTag2 Battery Monitor for Home Assistant

Monitor your Samsung SmartTag2 battery level in Home Assistant using the SmartThings API.

## How it works

A Python script reads the battery level directly from the SmartThings REST API using OAuth credentials obtained from the SmartThings CLI. The script handles token refresh automatically — no browser, no CLI at runtime.

The sensor is polled every 6 hours via HA's `command_line` integration.

---

## Prerequisites

- Home Assistant OS (hassio) running as a VM (e.g. Proxmox)
- SSH access to the HA host (e.g. via the **Advanced SSH & Web Terminal** add-on)
- A Linux laptop/desktop with a browser (for the one-time SmartThings login)
- `npm` installed on your laptop
- Your SmartTag2 already paired in the SmartThings app

---

## Part 1 — Authenticate on your laptop (one-time)

The SmartThings CLI requires a browser for its OAuth flow. Do this once on your laptop.

### 1.1 Install the SmartThings CLI

```bash
sudo npm install -g @smartthings/cli
```

### 1.2 Authenticate

```bash
smartthings devices
```

A browser window will open asking you to log in to Samsung. After login, the CLI saves credentials automatically. Confirm it works — you should see your devices listed including your SmartTag2.

### 1.3 Find the credentials file

```bash
cat /home/$USER/.local/share/@smartthings/cli/credentials.json
```

Note your **Device ID** for the SmartTag2 from the device list (format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`).

---

## Part 2 — Set up the folder structure on HA

SSH into your HA instance and create the required directories:

```bash
mkdir -p /config/scripts/smarttag/.smartthings
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

Still in `/config/scripts/smarttag/bin`:

```bash
# Add node to PATH for this session
export PATH="/config/scripts/smarttag/bin/node-v20.11.0-linux-x64-musl/bin:$PATH"

# Install the SmartThings CLI locally
npm install @smartthings/cli
```

### 4.1 Create the wrapper script

This wrapper ensures the correct Node binary is always used and prevents stale tokens from leaking in via environment variables:

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

## Part 5 — Copy credentials from your laptop to HA

On your **laptop**, copy the credentials file to HA via scp:

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

You should see your SmartTag2 listed. If you get a 401 error, check that no `SMARTTHINGS_TOKEN` environment variable is set (`echo $SMARTTHINGS_TOKEN`) and that the wrapper script does not contain a hardcoded token.

---

## Part 6 — The Python script

This script calls the SmartThings API directly — no CLI at runtime. It handles token refresh automatically when the access token expires.

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

Test it:

```bash
python3 /config/scripts/smarttag/tag_battery.py
# Expected output: FULL, NORMAL, or LOW
```

Also test simulating HA's minimal environment:

```bash
env -i HOME=/hassio \
  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  python3 /config/scripts/smarttag/tag_battery.py
# Should also return FULL, NORMAL, or LOW — not an error
```

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
│   └── credentials.json          # OAuth credentials (copied from computer)
├── bin/
│   ├── node-v20.11.0-linux-x64-musl/   # Node.js musl build
│   ├── node_modules/             # SmartThings CLI npm package
│   ├── node.tar.xz               # (can be deleted after extraction)
│   ├── package.json
│   ├── package-lock.json
│   └── smartthings               # Wrapper shell script
└── tag_battery.py                # The HA sensor script
```

---

## Troubleshooting

### 401 Unauthorized
The access token has expired and automatic refresh failed. Re-authenticate on your computer and copy the credentials file again:
```bash
smartthings devices   # triggers refresh on computer
scp /home/$USER/.local/share/@smartthings/cli/credentials.json \
    root@<HA_IP>:/config/scripts/smarttag/.smartthings/credentials.json
```

### Sensor shows UNKNOWN
The script returned an empty or unexpected value. Run the script manually from the HA SSH terminal and check the output:
```bash
python3 /config/scripts/smarttag/tag_battery.py
```

### Sensor shows the error message instead of battery level
During development the script returns `str(e)` for debugging. Once working, change the last `except` line to `return "ERROR"`.

### CLI hangs / timeout
Do not call the CLI from the Python script — use the direct API approach in Part 6. The CLI requires an interactive TTY and will hang when called from HA's `command_line` integration.

### SMARTTHINGS_TOKEN conflict
If you previously set `SMARTTHINGS_TOKEN` in your shell or in the wrapper script, it will override the credentials file. The wrapper script must contain `unset SMARTTHINGS_TOKEN`. Check with:
```bash
cat /config/scripts/smarttag/bin/smartthings
grep -r "SMARTTHINGS_TOKEN" /root/.zshrc /root/.bashrc /root/.profile 2>/dev/null
```

---

## Token refresh notes

- The OAuth **access token** expires roughly every 24 hours
- The **refresh token** stays valid as long as it is used regularly
- The Python script refreshes automatically on 401 — no manual intervention needed
- If HA polls every 6 hours, the refresh token will never go stale
- If you revoke app access in Samsung account settings, you will need to re-authenticate from scratch on your computer
