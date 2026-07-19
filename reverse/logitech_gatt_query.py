"""Send a query-only HID++ control-table request through the Logitech BLE GATT service.

Usage:
    python .\\logitech_gatt_query.py <control-table index 0..8>
    python .\\logitech_gatt_query.py --reporting <control ID, for example 00c4>
    python .\\logitech_gatt_query.py --temporary-remap <source control ID> <target control ID>

The first two modes issue read-style requests only.  `--temporary-remap` changes
only the requested mapping in volatile device configuration; it is reset by a
HID++ configuration reset and does not update firmware.
"""

import ctypes as ct
from ctypes import wintypes as wt
import sys

import logitech_gatt_probe as gatt


GENERIC_WRITE = 0x40000000
VENDOR_CHARACTERISTIC = "00010001-0000-1000-8000-011F2000046D"

gatt.bluetooth.BluetoothGATTSetCharacteristicValue.argtypes = [
    wt.HANDLE, ct.POINTER(gatt.BTH_LE_GATT_CHARACTERISTIC),
    ct.POINTER(gatt.BTH_LE_GATT_CHARACTERISTIC_VALUE), ct.c_void_p, wt.ULONG,
]
gatt.bluetooth.BluetoothGATTSetCharacteristicValue.restype = ct.c_long


def find_vendor_service():
    _, service_guid = gatt.LOGITECH_SERVICE_GUIDS[1]
    paths = [path for path in gatt.interface_paths(service_guid) if "d7aa41103bda" in path.lower()]
    if not paths:
        raise RuntimeError("MX Master 4 Logitech vendor GATT service was not found.")
    return paths[0]


def send_request(handle, characteristic, body):
    # The GATT characteristic is 18 bytes.  It carries the HID++ body after
    # report ID 0x10 and device ID 0xFF; those two bytes belong to the HID
    # bridge and must not be put in the GATT payload.
    if len(body) > 18:
        raise ValueError("HID++ request body is too long for this GATT characteristic")
    payload = bytearray(18)
    payload[:len(body)] = body
    raw = ct.create_string_buffer(ct.sizeof(wt.ULONG) + len(payload))
    value = ct.cast(raw, ct.POINTER(gatt.BTH_LE_GATT_CHARACTERISTIC_VALUE))
    value.contents.DataSize = len(payload)
    ct.memmove(ct.addressof(raw) + ct.sizeof(wt.ULONG), bytes(payload), len(payload))
    hr = gatt.hresult(gatt.bluetooth.BluetoothGATTSetCharacteristicValue(
        handle, ct.byref(characteristic), value, None, 0))
    if hr != 0:
        raise OSError(f"BluetoothGATTSetCharacteristicValue failed: 0x{hr:08X}")


def main():
    if len(sys.argv) == 2 and sys.argv[1].isdigit() and 0 <= int(sys.argv[1]) <= 8:
        index = int(sys.argv[1])
        body = bytes((0x0D, 0x1A, index))  # getCidInfo(index), software ID A
        description = f"control-table entry {index}"
    elif len(sys.argv) == 3 and sys.argv[1] == "--reporting":
        try:
            cid = int(sys.argv[2], 16)
        except ValueError:
            raise SystemExit("Control ID must be hexadecimal, for example 00c4.")
        if not 0 <= cid <= 0xFFFF:
            raise SystemExit("Control ID must fit in 16 bits.")
        body = bytes((0x0D, 0x2A, cid >> 8, cid & 0xFF))  # getCidReporting(cid)
        description = f"reporting state for control 0x{cid:04X}"
    elif len(sys.argv) == 4 and sys.argv[1] == "--temporary-remap":
        try:
            source = int(sys.argv[2], 16)
            target = int(sys.argv[3], 16)
        except ValueError:
            raise SystemExit("Control IDs must be hexadecimal, for example 00c4 0052.")
        if not 0 <= source <= 0xFFFF or not 0 <= target <= 0xFFFF:
            raise SystemExit("Control IDs must fit in 16 bits.")
        # setCidReporting(source, rvalid=1, remap=target), function 3 / software ID A.
        body = bytes((0x0D, 0x3A, source >> 8, source & 0xFF, 0x20, target >> 8, target & 0xFF))
        description = f"temporary remap 0x{source:04X} -> 0x{target:04X}"
    else:
        raise SystemExit("Usage: python .\\logitech_gatt_query.py <index 0..8> | --reporting <hex control ID> | --temporary-remap <source> <target>")
    path = find_vendor_service()
    handle = gatt.kernel32.CreateFileW(
        path, gatt.GENERIC_READ | GENERIC_WRITE, gatt.FILE_SHARE_READ | gatt.FILE_SHARE_WRITE,
        None, gatt.OPEN_EXISTING, 0, None,
    )
    if handle == gatt.INVALID_HANDLE_VALUE:
        raise ct.WinError(ct.get_last_error(), "opening Logitech vendor GATT service")
    try:
        characteristic = next(
            item for item in gatt.get_characteristics(handle)
            if gatt.uuid_text(item.CharacteristicUuid) == VENDOR_CHARACTERISTIC
        )
        send_request(handle, characteristic, body)
        print(f"Sent HID++ request for {description}.")
        print("Run logitech_hid_probe.py now to capture the response if it is delivered as vendor HID input.")
    finally:
        gatt.kernel32.CloseHandle(handle)


if __name__ == "__main__":
    main()
