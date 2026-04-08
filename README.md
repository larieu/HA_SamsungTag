# Samsung SmartTag2 Battery Integration (Home Assistant)

Since the SmartTag2 battery status is hidden in `bleD2D` metadata and requires OAuth token rotation, this setup uses a Python "Proxy" script to fetch data.

## 1. Prerequisites
- Access to a machine with [SmartThings CLI](https://github.com/SmartThingsCommunity/smartthings-cli) installed.
- Capture the `credentials.json` from the CLI to get the initial `refreshToken` and `client_id`.

## 2. File Structure
Place files in `/config/scripts/smarttag/`:
- `config.json`: Stores `client_id`, `device_id`, and the current `refresh_token`.
- `tag_battery.py`: Handles OAuth2 rotation and metadata extraction.

## 3. The Logic
The script performs the following:
1. Loads the `refresh_token` from `config.json`.
2. Requests a new `access_token` from SmartThings.
3. **Crucial:** Saves the *new* `refresh_token` back to `config.json` (Samsung burns tokens after one use).
4. Calls the `/v1/devices/{id}` endpoint with Header `Accept: application/vnd.smartthings+json;v=1`.
5. Parses the path: `['bleD2D']['metadata']['battery']['level']`.

## 4. Home Assistant Sensor
```yaml
command_line:
  - sensor:
      name: "SmartTag2 Ana Battery"
      command: "python3 /config/scripts/smarttag/tag_battery.py"
      scan_interval: 3600
      value_template: "{{ value }}"
