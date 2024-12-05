#!/usr/bin/python3
import json
import time

import requests
from pymodbus.client import ModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder

g_last_timestamp = 0
g_last_price = 0

def send_to_awtrix(ip, data):
    bat_soc = data["bat_soc"]
    if bat_soc < 40:
        bat_soc_icon = 6354 # 20%
    elif 40 <= bat_soc < 60:
        bat_soc_icon = 6355 # 40%
    elif 60 <= bat_soc < 80:
        bat_soc_icon = 6356 # 60%
    elif 80 <= bat_soc < 100:
        bat_soc_icon = 6357 # 80%
    else:
        bat_soc_icon = 6358 # 100%

    price = data["price"]
    if price < 0.30:
        price_icon = 3961 # green
    elif 0.30 <= price < 0.40:
        price_icon = 6256 # yellow
    else:
        price_icon = 3813 # red

    json_data = [
        {
            "icon": 18363,
            "text": format_watt(data["pv_power"]),
            "lifetime": 300
        },
        {
            "icon": bat_soc_icon,
            "text": "%d %%" % bat_soc,
            "lifetime": 300
        },
        {
            "icon": 403,
            "text": format_watt(data["ac_power"]),
            "lifetime": 300
        },
        {
            "icon": price_icon,
            "text": "%.2f" % price,
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

def get_energy_price() -> float:
    current_timestamp = int(time.time())
    current_hour_timestamp = current_timestamp - (current_timestamp % 3600)

    global g_last_timestamp
    global g_last_price

    if current_hour_timestamp == g_last_timestamp:
        return g_last_price

    response = json.loads(requests.get("https://api.energy-charts.info/price?bzn=DE-LU").content.decode('UTF-8'))
    index = response["unix_seconds"].index(current_hour_timestamp)
    stock_price = response["price"][index] / 1000

    price = (stock_price * 1.19) + 0.1984 # Green Planet Energy Ökostrom flex

    g_last_timestamp = current_hour_timestamp
    g_last_price = price

    return price

def main():
    print("awtrix-victron v1.1")
    victron_ip = "192.168.178.104"
    awtrix_ip = "192.168.178.143"

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
        result = client.read_input_registers(784, 1, slave=1)
        decoder = BinaryPayloadDecoder.fromRegisters(result.registers, byteorder=Endian.BIG)
        yield_1 = decoder.decode_16bit_uint() / 10
        result = client.read_input_registers(784, 1, slave=100)
        decoder = BinaryPayloadDecoder.fromRegisters(result.registers, byteorder=Endian.BIG)
        yield_2 = decoder.decode_16bit_uint() / 10
        energy_price = get_energy_price()

        data = {
            "ac_power": l1 + l2 + l3,
            "pv_power": pv_p,
            "pv_yield": yield_1 + yield_2,
            "bat_soc": soc,
            "price": price
        }

        send_to_awtrix(awtrix_ip, data)
        time.sleep(3)


if __name__ == "__main__":
    main()
