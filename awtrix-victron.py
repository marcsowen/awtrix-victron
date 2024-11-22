#!/usr/bin/python3
import time
import requests
from pymodbus.client import ModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder


def send_to_awtrix(ip, data):
    headers = {"Content-Type": "application/json"}
    bat_soc = data["bat_soc"]
    bat_soc_icon = 6345
    if bat_soc >= 30: bat_soc_icon = 6355
    if bat_soc >= 50: bat_soc_icon = 6356
    if bat_soc >= 70: bat_soc_icon = 6357
    if bat_soc == 100: bat_soc_icon = 6358

    json_data = [
        {
            "icon": 18363,
            "text": format_watt(data["pv_power"]),
            "lifetime": 300
        },
        {
            "icon": bat_soc_icon,
            "text": "%d %%" % data["bat_soc"],
            "lifetime": 300
        },
        {
            "icon": 403,
            "text": format_watt(data["ac_power"]),
            "lifetime": 300
        }
    ]

    url = "http://" + ip + "/api/custom?name=solar"
    requests.post(url, json=json_data, headers=headers)


def format_watt(watt: float) -> str:
    if watt >= 10000:
        return "%.0f kW" % (watt / 1000)
    elif watt >= 1000:
        return "%.1f kW" % (watt / 1000)
    else:
        return "%d W" % watt


def main():
    print("awtrix-victron v1.0")
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

        data = {
            "ac_power": l1 + l2 + l3,
            "pv_power": pv_p,
            "pv_yield": yield_1 + yield_2,
            "bat_soc": soc,
        }

        send_to_awtrix(awtrix_ip, data)
        time.sleep(3)


if __name__ == "__main__":
    main()
