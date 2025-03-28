#!/usr/bin/python3
import json
import time

import requests
from datetime import timedelta, datetime
from pymodbus.client import ModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder

g_price_last_timestamp = 0
g_price_last_price_result = {}
g_temp_last_timestamp = 0
g_temp_last_temperature = 0

def send_to_awtrix(ip, data):
    bat_soc = data["bat_soc"]
    bat_soc_icon = 6354 + int(bat_soc / 25)

    price_icon = data["evu_price"]["icon"]

    temperature = data["temperature"]
    temperature_icon = 21750 - max(min(int((temperature + 15) / 10), 5), 0)

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
        },
        {
            "icon": price_icon,
            "text": "%.2f" % data["evu_price"]["price"],
            "lifetime": 300
        },
        {
            "icon": price_icon,
            "draw": data["evu_price"]["bars"],
            "lifetime": 300
        },
        {
            "icon": temperature_icon,
            "text": "%.1f" % temperature,
            "lifetime": 300
        }
    ]

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

def get_energy_price():
    current_timestamp = int(time.time())
    current_hour_timestamp = current_timestamp - (current_timestamp % 3600)

    global g_price_last_timestamp
    global g_price_last_price_result

    if current_hour_timestamp == g_price_last_timestamp:
        return g_price_last_price_result

    next_day = datetime.today() + timedelta(days=1)
    response = json.loads(requests.get("https://api.energy-charts.info/price?bzn=DE-LU&end=" + next_day.strftime("%Y-%m-%d")).content.decode('UTF-8'))
    index = response["unix_seconds"].index(current_hour_timestamp)
    end_index = min(len(response["unix_seconds"]) - index, 11) + index
    current_price = get_evu_price_in_euro(response["price"][index])
    bar_chart_stock = response["price"][index:end_index]
    bar_chart_min_value = min(bar_chart_stock)
    bar_chart_max_value = max(bar_chart_stock)
    bar_chart_int = [int(round((((value - bar_chart_min_value) / (bar_chart_max_value - bar_chart_min_value)) * 7) + 1, 0)) for value in bar_chart_stock]
    bar_chart_euro = [get_evu_price_in_euro(price) for price in bar_chart_stock]
    bar_chart_color = [get_color_from_price(price) for price in bar_chart_euro]

    result = {
        "price": current_price,
        "icon": get_color_from_price(current_price)["icon"],
        "bars": get_bar_graph_drawing(bar_chart_int, bar_chart_color),
    }

    g_price_last_timestamp = current_hour_timestamp
    g_price_last_price_result = result

    return result

def get_bar_graph_drawing(heights, colors) -> list:
    data_size = len(heights)
    start_x = 9
    result = []

    for i in range(0, data_size):
        x = start_x + i * 2
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

def get_evu_price_in_euro(stock_price: float) -> float:
    return round((stock_price / 1000 * 1.19) + 0.1978, 2) # Green Planet Energy Ökostrom flex (since 01/2025)

def get_outside_weather(ip: str, ble_mac: str):
    response = json.loads(requests.get("http://" + ip).content.decode('UTF-8'))
    return next(sensor for sensor in response["sensors"] if sensor["ble_mac"] == ble_mac)

def main():
    print("awtrix-victron v1.2")
    victron_ip = "192.168.178.104"
    awtrix_ip = "192.168.178.143"
    weather_sensor_ip = "192.168.178.157"
    weather_sensor_ble_mac = "F4:5C:E1:F9:32:21"

    client = ModbusTcpClient(victron_ip)
    while True:
        result = client.read_input_registers(817, 3, slave=100)
        decoder = BinaryPayloadDecoder.fromRegisters(result.registers, byteorder=Endian.BIG)
        l1 = decoder.decode_16bit_uint()
        l2 = decoder.decode_16bit_uint()
        l3 = decoder.decode_16bit_uint()
        result = client.read_input_registers(850, 1, slave=100)
        decoder = BinaryPayloadDecoder.fromRegisters(result.registers, byteorder=Endian.BIG)
        pv_p = decoder.decode_16bit_uint()
        result = client.read_input_registers(266, 1, slave=225)
        decoder = BinaryPayloadDecoder.fromRegisters(result.registers, byteorder=Endian.BIG)
        soc = decoder.decode_16bit_uint() / 10
        energy_price = get_energy_price()
        weather = get_outside_weather(weather_sensor_ip, weather_sensor_ble_mac)

        data = {
            "ac_power": l1 + l2 + l3,
            "pv_power": pv_p,
            "bat_soc": soc,
            "evu_price": energy_price,
            "temperature": weather["temperature"]
        }

        send_to_awtrix(awtrix_ip, data)
        time.sleep(3)


if __name__ == "__main__":
    main()
