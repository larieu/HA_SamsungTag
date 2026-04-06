# 🏷️ HA Samsung Tag
Trace the battery status of a Samsung SmartTag 2 from Home Assistant (HA).

## 🚀 Setup Instructions

### 1. Generate your Personal Access Token
Go to the **SmartThings Developers Page** to create a token:
🔗 [SmartThings Developers Page](https://account.smartthings.com/tokens)

* **Important:** Save the token in a safe place immediately. 
* In the code below, this will be referred to as `%TOKEN%`.

### 2. Locate your Unique Device ID
Find your unique SmartTag ID in the **SmartThings Advanced User Console**:
🔗 [SmartThings Advanced Console](https://my.smartthings.com/advanced)

* Find your tag in the list and copy the `Device ID`.
* In the code below, this will be referred to as `%UNIQUE_ID%`.

### 3. Choose your Home Assistant Names
Decide on two names for your integration:
* **%DEVICE_NAME%**: The friendly name shown in your dashboard (e.g., `First SmartTag Battery`).
* **%UNIQUE_HA-ID%**: A unique internal ID for Home Assistant (e.g., `first_tag_battery_rest`).

---

## 🛠️ Configuration

Add the following block to your `configuration.yaml` file. Replace the placeholders (`%...%`) with the information gathered in the steps above.

```yaml
sensor:
  - platform: rest
    name: "%DEVICE_NAME%"
    unique_id: "%UNIQUE_HA-ID%"
    resource: "[https://api.smartthings.com/v1/devices/%UNIQUE_ID](https://api.smartthings.com/v1/devices/%UNIQUE_ID)%"
    method: GET
    headers:
      Authorization: "Bearer %TOKEN%"
      Accept: "application/json"
    # Mapping the Samsung status words to numbers for alerts and graphs
    value_template: >
      {% set status = value_json.bleD2D.metadata.battery.level | default('NORMAL') %}
      {% if status == 'FULL' %} 100
      {% elif status == 'NORMAL' %} 50
      {% elif status == 'LOW' %} 10
      {% else %} 5
      {% endif %}
    unit_of_measurement: "%"
    device_class: battery
    scan_interval: 3600
