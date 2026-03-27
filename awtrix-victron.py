#!/usr/bin/python3

import json
import time
from datetime import datetime

import requests
import yaml
from pymodbus.client import ModbusTcpClient

g_price_last_timestamp = 0
g_price_last_price_result = {}
g_temp_last_timestamp = 0
g_temp_last_temperature = 0

def send_to_awtrix(ip, data):
    bat_soc = data["bat_soc"]
    bat_soc_icon = 6354 + int(bat_soc / 25)

    price_icon = data["evu_price"]["icon"]
    evu_price = data["evu_price"]["price"]

    temperature = data["temperature"]
    if temperature is not None:
        temperature_icon = 21750 - max(min(int((temperature + 15) / 10), 5), 0)

    pool_temperature = data["pool_temperature"]

    json_data = [
        {
            "icon": 18363,
            "text": format_watt(data["pv_power"]),
            "lifetime": 300
        },
        {
            "icon": 403,
            "text": format_watt(data["ac_power"]),
            "lifetime": 300
        },
        {
            "icon": bat_soc_icon,
            "text": "%d %%" % bat_soc,
            "lifetime": 300
        }
    ]

    if isinstance(evu_price, (int, float)):
        json_data.append({
            "icon": price_icon,
            "text": "%.2f" % evu_price,
            "lifetime": 300
        })
        json_data.append({
            "icon": price_icon,
            "draw": data["evu_price"]["bars"],
            "lifetime": 300
        })

    if temperature is not None:
        json_data.append({
            "icon": temperature_icon,
            "text": "%.1f" % temperature,
            "lifetime": 300
        })

    if pool_temperature is not None:
        json_data.append({
            "icon": 48963,
            "text": "%.1f" % pool_temperature,
            "lifetime": 300
        })

    headers = {"Content-Type": "application/json"}
    url = "http://" + ip + "/api/custom?name=solar"
    requests.post(url, json=json_data, headers=headers)


def format_watt(watt: float) -> str:
    if watt >= 10000:
        return "%.0f kW" % (watt / 1000)
    elif watt >= 1000:
        return "%.1f kW" % (watt / 1000)
    else:
        return "%d W" % watt

def fetch_tibber(config: dict) -> list:
    query = """
    query FetchPriceInfo($homeId: ID!) {
      viewer {
        home(id: $homeId) {
          currentSubscription {
            priceInfo(resolution: QUARTER_HOURLY) {
              today {
                total
                startsAt
              }
              tomorrow {
                total
                startsAt
              }
            }
          }
        }
      }
    }
    """

    response = json.loads(
        requests.post(
            "https://api.tibber.com/v1-beta/gql",
            json={"query": query, "variables": {"homeId": config["home_id"]}},
            headers={"Authorization": f"Bearer {config['token']}"},
        ).content.decode("UTF-8")
    )

    price_info = (
        response.get("data", {})
        .get("viewer", {})
        .get("home", {})
        .get("currentSubscription", {})
        .get("priceInfo", {})
    )

    return sorted(
        [
            {"price": entry["total"], "time": int(datetime.fromisoformat(entry["startsAt"]).timestamp())}
            for day in ("today", "tomorrow")
            for entry in (price_info.get(day) or [])
        ],
        key=lambda entry: entry["time"],
    )


def get_energy_price(tibber_config: dict):
    current_timestamp = int(time.time())
    current_hour_timestamp = current_timestamp - (current_timestamp % 3600)
    current_quarter_hour_timestamp = current_timestamp - (current_timestamp % 900)

    global g_price_last_timestamp
    global g_price_last_price_result

    if current_hour_timestamp == g_price_last_timestamp:
        return g_price_last_price_result

    try:
        tibber_prices = fetch_tibber(tibber_config)
        current_price_index = next(i for i, entry in enumerate(tibber_prices) if entry["time"] == current_quarter_hour_timestamp)
        end_index = min(len(tibber_prices) - current_price_index, 22) + current_price_index
        current_price = tibber_prices[current_price_index]["price"]
        bar_chart_price = [entry["price"] for entry in tibber_prices[current_price_index:end_index]]
        bar_chart_min_value = min(bar_chart_price)
        bar_chart_max_value = max(bar_chart_price)
        bar_chart_int = [int(round((((value - bar_chart_min_value) / (bar_chart_max_value - bar_chart_min_value)) * 7) + 1, 0)) for value in bar_chart_price]
        bar_chart_color = [get_color_from_price(price) for price in bar_chart_price]

        result = {
            "price": current_price,
            "icon": get_color_from_price(current_price)["icon"],
            "bars": get_bar_graph_drawing(bar_chart_int, bar_chart_color),
        }
    except:
        result = {
            "price": None,
            "icon": 6256,
            "bars": [],
        }

    g_price_last_timestamp = current_hour_timestamp
    g_price_last_price_result = result

    return result

def get_bar_graph_drawing(heights, colors) -> list:
    data_size = len(heights)
    start_x = 9
    result = []

    for i in range(0, data_size):
        x = start_x + i
        y = 8 - heights[i]
        result.append({"df": [x, y, 1, heights[i], colors[i]["color"]]})

    return result

def get_color_from_price(price: float) -> dict:
    if price < 0.30:
        return { "color": "#00ff00", "icon": 3961} # green
    elif 0.30 <= price < 0.40:
        return { "color": "#ffff00", "icon": 6256} # yellow
    else:
        return { "color": "#ff0000", "icon": 3813} # red

def get_outside_weather(ip: str, ble_mac: str):
    try:
        response = json.loads(requests.get("http://" + ip).content.decode('UTF-8'))
        return next(sensor for sensor in response["sensors"] if sensor["ble_mac"] == ble_mac)
    except:
        return None

def get_pool_temp() -> float | None:
    try:
        response = json.loads(requests.get("http://localhost:8009").content.decode('UTF-8'))
        temp_current = response["temp_current"]
        return temp_current if isinstance(temp_current, (int, float)) else None
    except:
        return None

def main():
    print("awtrix-victron v1.6")
    victron_ip = "192.168.178.104"
    awtrix_ip = "192.168.178.143"
    weather_sensor_ip = "192.168.178.157"
    weather_sensor_ble_mac = "F4:5C:E1:F9:32:21"

    with open("/etc/tibber.yaml", encoding="utf-8") as config_file:
        tibber_config = yaml.safe_load(config_file)

    client = ModbusTcpClient(victron_ip)
    while True:

        result = client.read_input_registers(817, count=3, device_id=100)
        l1, l2, l3 = client.convert_from_registers(result.registers, data_type=client.DATATYPE.UINT16)
        result = client.read_input_registers(850, count=1, device_id=100)
        pv_p = client.convert_from_registers(result.registers, data_type=client.DATATYPE.UINT16)
        result = client.read_input_registers(266, count=1, device_id=225)
        soc = client.convert_from_registers(result.registers, data_type=client.DATATYPE.UINT16) / 10
        energy_price = get_energy_price(tibber_config)
        weather = get_outside_weather(weather_sensor_ip, weather_sensor_ble_mac)
        pool_temp = get_pool_temp()

        data = {
            "ac_power": l1 + l2 + l3,
            "pv_power": pv_p,
            "bat_soc": soc,
            "evu_price": energy_price,
            "temperature": weather["temperature"] if weather is not None else None,
            "pool_temperature": pool_temp
        }

        send_to_awtrix(awtrix_ip, data)
        time.sleep(3)


if __name__ == "__main__":
    main()
