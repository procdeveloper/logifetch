"""Read-only inventory of the Bluetooth LE GATT services exposed by MX Master 4.

Usage:
    python .\\logitech_gatt_probe.py

This opens the Bluetooth LE device for read access, lists its services and
characteristics, and never calls a GATT write or configuration function.
"""

import ctypes as ct
from ctypes import wintypes as wt
import sys


kernel32 = ct.WinDLL("kernel32", use_last_error=True)
setupapi = ct.WinDLL("setupapi", use_last_error=True)
bluetooth = ct.WinDLL("BluetoothAPIs", use_last_error=True)

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
ERROR_NO_MORE_ITEMS = 259
ERROR_MORE_DATA_HR = 0x800700EA
INVALID_HANDLE_VALUE = ct.c_void_p(-1).value


class GUID(ct.Structure):
    _fields_ = [
        ("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
        ("Data4", ct.c_ubyte * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ct.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("InterfaceClass", GUID), ("Flags", wt.DWORD), ("Reserved", ct.c_void_p)]


class BTH_LE_UUID_VALUE(ct.Union):
    _fields_ = [("ShortUuid", wt.WORD), ("LongUuid", GUID)]


class BTH_LE_UUID(ct.Structure):
    _fields_ = [("IsShortUuid", ct.c_ubyte), ("Value", BTH_LE_UUID_VALUE)]


class BTH_LE_GATT_SERVICE(ct.Structure):
    _fields_ = [("ServiceUuid", BTH_LE_UUID), ("AttributeHandle", wt.WORD)]


class BTH_LE_GATT_CHARACTERISTIC(ct.Structure):
    _fields_ = [
        ("ServiceHandle", wt.WORD), ("CharacteristicUuid", BTH_LE_UUID),
        ("AttributeHandle", wt.WORD), ("CharacteristicValueHandle", wt.WORD),
        ("IsBroadcastable", ct.c_ubyte), ("IsReadable", ct.c_ubyte),
        ("IsWritable", ct.c_ubyte), ("IsWritableWithoutResponse", ct.c_ubyte),
        ("IsSignedWritable", ct.c_ubyte), ("IsNotifiable", ct.c_ubyte),
        ("IsIndicatable", ct.c_ubyte), ("HasExtendedProperties", ct.c_ubyte),
    ]


class BTH_LE_GATT_CHARACTERISTIC_VALUE(ct.Structure):
    _fields_ = [("DataSize", wt.ULONG), ("Data", ct.c_ubyte * 1)]


kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ct.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
kernel32.CreateFileW.restype = wt.HANDLE
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL
setupapi.SetupDiGetClassDevsW.argtypes = [ct.POINTER(GUID), wt.LPCWSTR, wt.HWND, wt.DWORD]
setupapi.SetupDiGetClassDevsW.restype = wt.HANDLE
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [wt.HANDLE, ct.c_void_p, ct.POINTER(GUID), wt.DWORD, ct.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiEnumDeviceInterfaces.restype = wt.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [wt.HANDLE, ct.POINTER(SP_DEVICE_INTERFACE_DATA), ct.c_void_p, wt.DWORD, ct.POINTER(wt.DWORD), ct.c_void_p]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wt.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wt.HANDLE]
setupapi.SetupDiDestroyDeviceInfoList.restype = wt.BOOL
bluetooth.BluetoothGATTGetServices.argtypes = [wt.HANDLE, wt.USHORT, ct.POINTER(BTH_LE_GATT_SERVICE), ct.POINTER(wt.USHORT), wt.ULONG]
bluetooth.BluetoothGATTGetServices.restype = ct.c_long
bluetooth.BluetoothGATTGetCharacteristics.argtypes = [wt.HANDLE, ct.POINTER(BTH_LE_GATT_SERVICE), wt.USHORT, ct.POINTER(BTH_LE_GATT_CHARACTERISTIC), ct.POINTER(wt.USHORT), wt.ULONG]
bluetooth.BluetoothGATTGetCharacteristics.restype = ct.c_long
bluetooth.BluetoothGATTGetCharacteristicValue.argtypes = [
    wt.HANDLE, ct.POINTER(BTH_LE_GATT_CHARACTERISTIC), wt.ULONG,
    ct.POINTER(BTH_LE_GATT_CHARACTERISTIC_VALUE), ct.POINTER(wt.USHORT), wt.ULONG,
]
bluetooth.BluetoothGATTGetCharacteristicValue.restype = ct.c_long


def guid(data1, data2, data3, data4):
    return GUID(data1, data2, data3, (ct.c_ubyte * 8)(*data4))


# GUID_BLUETOOTHLE_DEVICE_INTERFACE from bthledef.h.
GUID_BLUETOOTHLE_DEVICE_INTERFACE = guid(0x781AEE18, 0x7733, 0x4CE4, [0xAD, 0xD0, 0x91, 0xF4, 0x1C, 0x67, 0xB5, 0x92])


def uuid_text(value):
    if value.IsShortUuid:
        return f"0000{value.Value.ShortUuid:04X}-0000-1000-8000-00805F9B34FB"
    g = value.Value.LongUuid
    tail = bytes(g.Data4)
    return f"{g.Data1:08X}-{g.Data2:04X}-{g.Data3:04X}-{tail[:2].hex().upper()}-{tail[2:].hex().upper()}"


def interface_paths(interface_guid=GUID_BLUETOOTHLE_DEVICE_INTERFACE):
    info_set = setupapi.SetupDiGetClassDevsW(ct.byref(interface_guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if info_set == INVALID_HANDLE_VALUE:
        raise ct.WinError(ct.get_last_error())
    try:
        index = 0
        while True:
            interface = SP_DEVICE_INTERFACE_DATA()
            interface.cbSize = ct.sizeof(interface)
            if not setupapi.SetupDiEnumDeviceInterfaces(info_set, None, ct.byref(interface_guid), index, ct.byref(interface)):
                if ct.get_last_error() == ERROR_NO_MORE_ITEMS:
                    return
                raise ct.WinError(ct.get_last_error())
            required = wt.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(info_set, ct.byref(interface), None, 0, ct.byref(required), None)
            detail = ct.create_string_buffer(required.value)
            ct.cast(detail, ct.POINTER(wt.DWORD))[0] = 8 if ct.sizeof(ct.c_void_p) == 8 else 6
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(info_set, ct.byref(interface), detail, required.value, None, None):
                raise ct.WinError(ct.get_last_error())
            yield ct.wstring_at(ct.addressof(detail) + ct.sizeof(wt.DWORD))
            index += 1
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(info_set)


def hresult(value):
    return value & 0xFFFFFFFF


def get_services(handle):
    count = wt.USHORT()
    hr = hresult(bluetooth.BluetoothGATTGetServices(handle, 0, None, ct.byref(count), 0))
    if hr not in (0, ERROR_MORE_DATA_HR):
        raise OSError(f"BluetoothGATTGetServices sizing failed: 0x{hr:08X}")
    services = (BTH_LE_GATT_SERVICE * count.value)()
    actual = wt.USHORT()
    hr = hresult(bluetooth.BluetoothGATTGetServices(handle, count.value, services, ct.byref(actual), 0))
    if hr != 0:
        raise OSError(f"BluetoothGATTGetServices failed: 0x{hr:08X}")
    return services[:actual.value]


def get_characteristics(handle, service=None):
    count = wt.USHORT()
    parent = ct.byref(service) if service is not None else None
    hr = hresult(bluetooth.BluetoothGATTGetCharacteristics(handle, parent, 0, None, ct.byref(count), 0))
    if hr not in (0, ERROR_MORE_DATA_HR):
        raise OSError(f"sizing failed: 0x{hr:08X}")
    chars = (BTH_LE_GATT_CHARACTERISTIC * count.value)()
    actual = wt.USHORT()
    hr = hresult(bluetooth.BluetoothGATTGetCharacteristics(handle, parent, count.value, chars, ct.byref(actual), 0))
    if hr != 0:
        raise OSError(f"enumeration failed: 0x{hr:08X}")
    return chars[:actual.value]


def get_value(handle, characteristic):
    """Return a characteristic value.  This performs a GATT read only."""
    needed = wt.USHORT()
    hr = hresult(bluetooth.BluetoothGATTGetCharacteristicValue(
        handle, ct.byref(characteristic), 0, None, ct.byref(needed), 0))
    if hr not in (0, ERROR_MORE_DATA_HR):
        raise OSError(f"value sizing failed: 0x{hr:08X}")
    raw = ct.create_string_buffer(needed.value)
    value = ct.cast(raw, ct.POINTER(BTH_LE_GATT_CHARACTERISTIC_VALUE))
    actual = wt.USHORT()
    hr = hresult(bluetooth.BluetoothGATTGetCharacteristicValue(
        handle, ct.byref(characteristic), needed.value, value, ct.byref(actual), 0))
    if hr != 0:
        raise OSError(f"value read failed: 0x{hr:08X}")
    data_size = value.contents.DataSize
    return bytes(raw[ct.sizeof(wt.ULONG):ct.sizeof(wt.ULONG) + data_size])


def properties(characteristic):
    names = [
        ("read", characteristic.IsReadable), ("write", characteristic.IsWritable),
        ("write-no-response", characteristic.IsWritableWithoutResponse),
        ("notify", characteristic.IsNotifiable), ("indicate", characteristic.IsIndicatable),
    ]
    return ", ".join(name for name, present in names if present) or "none"


def uuid_guid(data1, data2, data3, tail):
    return guid(data1, data2, data3, tail)


LOGITECH_SERVICE_GUIDS = [
    ("FD72", uuid_guid(0x0000FD72, 0x0000, 0x1000, [0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB])),
    ("vendor", uuid_guid(0x00010000, 0x0000, 0x1000, [0x80, 0x00, 0x01, 0x1F, 0x20, 0x00, 0x04, 0x6D])),
]


def probe_service_interface(label, interface_guid, show_values):
    paths = [path for path in interface_paths(interface_guid) if "d7aa41103bda" in path.lower()]
    if not paths:
        print(f"\nNo Windows GATT service interface exposed for Logitech {label}.")
        return
    for path in paths:
        print(f"\nLogitech {label} service interface:\n  {path}")
        handle = kernel32.CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
        if handle == INVALID_HANDLE_VALUE:
            print(f"  Open failed: {ct.WinError(ct.get_last_error())}")
            continue
        try:
            for char in get_characteristics(handle):
                print(f"  Char {uuid_text(char.CharacteristicUuid)}  value {char.CharacteristicValueHandle:04X}  [{properties(char)}]")
                if show_values and char.IsReadable:
                    try:
                        print(f"    read: {get_value(handle, char).hex(' ')}")
                    except OSError as exc:
                        print(f"    read failed: {exc}")
        except OSError as exc:
            print(f"  {exc}")
        finally:
            kernel32.CloseHandle(handle)


def main():
    show_values = "--values" in sys.argv
    candidates = [path for path in interface_paths() if "d7aa41103bda" in path.lower()]
    if not candidates:
        raise RuntimeError("MX Master 4 Bluetooth LE interface not found. Keep the mouse paired and connected.")
    for path in candidates:
        print(f"Bluetooth LE interface:\n  {path}")
        handle = kernel32.CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
        if handle == INVALID_HANDLE_VALUE:
            print(f"  Open failed: {ct.WinError(ct.get_last_error())}")
            continue
        try:
            for service in get_services(handle):
                print(f"  Service {uuid_text(service.ServiceUuid)}  handle {service.AttributeHandle:04X}")
                for char in get_characteristics(handle, service):
                    print(f"    Char {uuid_text(char.CharacteristicUuid)}  value {char.CharacteristicValueHandle:04X}  [{properties(char)}]")
                    if show_values and char.IsReadable:
                        try:
                            print(f"      read: {get_value(handle, char).hex(' ')}")
                        except OSError as exc:
                            print(f"      read failed: {exc}")
        except OSError as exc:
            print(f"  {exc}")
        finally:
            kernel32.CloseHandle(handle)
    for label, service_guid in LOGITECH_SERVICE_GUIDS:
        probe_service_interface(label, service_guid, show_values)


if __name__ == "__main__":
    main()
