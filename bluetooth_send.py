# bluetooth_sender.py
import asyncio
from bleak import BleakClient

ELEVATOR_BT_ADDRESS = "AA:BB:CC:DD:EE:FF"  # Replace with your elevator's Bluetooth MAC address
CHARACTERISTIC_UUID = "0000xxxx-0000-1000-8000-00805f9b34fb"  # Replace with writable characteristic UUID

async def send_floor_number_via_bluetooth(floor_number: int):
    async with BleakClient(ELEVATOR_BT_ADDRESS) as client:
        connected = await client.connect()
        if connected:
            data = str(floor_number).encode('utf-8')
            await client.write_gatt_char(CHARACTERISTIC_UUID, data)
            print(f"Sent floor number {floor_number} via Bluetooth")
        else:
            print("Failed to connect to elevator Bluetooth device")

