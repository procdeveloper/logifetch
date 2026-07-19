"""Read raw reports directly from every Logitech HID collection.

Usage:
    python logitech_hid_probe.py --list    # enumerate only
    python logitech_hid_probe.py           # print reports until Ctrl+C

Keep Logi Options+ stopped while testing.  This program is read-only: it opens
HID collections with GENERIC_READ only and never sends an output/feature report.
"""

import ctypes as ct
from ctypes import wintypes as wt
import sys
import threading
import traceback


kernel32 = ct.WinDLL("kernel32", use_last_error=True)
setupapi = ct.WinDLL("setupapi", use_last_error=True)
hid = ct.WinDLL("hid", use_last_error=True)

kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ct.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
kernel32.CreateFileW.restype = wt.HANDLE

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
ERROR_NO_MORE_ITEMS = 259
INVALID_HANDLE_VALUE = ct.c_void_p(-1).value
HIDP_STATUS_SUCCESS = 0x00110000


class GUID(ct.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ct.c_ubyte * 8)]


setupapi.SetupDiGetClassDevsW.argtypes = [ct.POINTER(GUID), wt.LPCWSTR, wt.HWND, wt.DWORD]
setupapi.SetupDiGetClassDevsW.restype = wt.HANDLE


class SP_DEVICE_INTERFACE_DATA(ct.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("InterfaceClass", GUID), ("Flags", wt.DWORD), ("Reserved", ct.c_void_p)]


class HIDD_ATTRIBUTES(ct.Structure):
    _fields_ = [("Size", wt.DWORD), ("VendorID", wt.WORD), ("ProductID", wt.WORD), ("VersionNumber", wt.WORD)]


class HIDP_CAPS(ct.Structure):
    _fields_ = [
        ("Usage", wt.WORD), ("UsagePage", wt.WORD),
        ("InputReportByteLength", wt.WORD), ("OutputReportByteLength", wt.WORD),
        ("FeatureReportByteLength", wt.WORD), ("Reserved", wt.WORD * 17),
        ("NumberLinkCollectionNodes", wt.WORD),
        ("NumberInputButtonCaps", wt.WORD), ("NumberInputValueCaps", wt.WORD), ("NumberInputDataIndices", wt.WORD),
        ("NumberOutputButtonCaps", wt.WORD), ("NumberOutputValueCaps", wt.WORD), ("NumberOutputDataIndices", wt.WORD),
        ("NumberFeatureButtonCaps", wt.WORD), ("NumberFeatureValueCaps", wt.WORD), ("NumberFeatureDataIndices", wt.WORD),
    ]


# Explicit signatures are required for 64-bit handles.  Without them ctypes
# assumes an int for SetupAPI arguments, which can truncate the device-set
# handle in a Python process launched through the Explorer file association.
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wt.HANDLE, ct.c_void_p, ct.POINTER(GUID), wt.DWORD, ct.POINTER(SP_DEVICE_INTERFACE_DATA)
]
setupapi.SetupDiEnumDeviceInterfaces.restype = wt.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wt.HANDLE, ct.POINTER(SP_DEVICE_INTERFACE_DATA), ct.c_void_p, wt.DWORD,
    ct.POINTER(wt.DWORD), ct.c_void_p,
]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wt.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wt.HANDLE]
setupapi.SetupDiDestroyDeviceInfoList.restype = wt.BOOL
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL
kernel32.ReadFile.argtypes = [wt.HANDLE, ct.c_void_p, wt.DWORD, ct.POINTER(wt.DWORD), ct.c_void_p]
kernel32.ReadFile.restype = wt.BOOL
kernel32.WriteFile.argtypes = [wt.HANDLE, ct.c_void_p, wt.DWORD, ct.POINTER(wt.DWORD), ct.c_void_p]
kernel32.WriteFile.restype = wt.BOOL
hid.HidD_GetHidGuid.argtypes = [ct.POINTER(GUID)]
hid.HidD_GetHidGuid.restype = None
hid.HidD_GetAttributes.argtypes = [wt.HANDLE, ct.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetAttributes.restype = wt.BOOL
hid.HidD_GetPreparsedData.argtypes = [wt.HANDLE, ct.POINTER(ct.c_void_p)]
hid.HidD_GetPreparsedData.restype = wt.BOOL
hid.HidD_FreePreparsedData.argtypes = [ct.c_void_p]
hid.HidD_FreePreparsedData.restype = wt.BOOL
hid.HidP_GetCaps.argtypes = [ct.c_void_p, ct.POINTER(HIDP_CAPS)]
hid.HidP_GetCaps.restype = ct.c_ulong


def check(ok, what):
    if not ok:
        raise ct.WinError(ct.get_last_error(), what)


def hid_paths():
    """Yield every present HID interface path."""
    guid = GUID()
    hid.HidD_GetHidGuid(ct.byref(guid))
    info_set = setupapi.SetupDiGetClassDevsW(ct.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if info_set == INVALID_HANDLE_VALUE:
        raise ct.WinError(ct.get_last_error())
    try:
        index = 0
        while True:
            interface = SP_DEVICE_INTERFACE_DATA()
            interface.cbSize = ct.sizeof(interface)
            if not setupapi.SetupDiEnumDeviceInterfaces(info_set, None, ct.byref(guid), index, ct.byref(interface)):
                if ct.get_last_error() == ERROR_NO_MORE_ITEMS:
                    return
                raise ct.WinError(ct.get_last_error())
            required = wt.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(info_set, ct.byref(interface), None, 0, ct.byref(required), None)
            detail = ct.create_string_buffer(required.value)
            ct.cast(detail, ct.POINTER(wt.DWORD))[0] = 8 if ct.sizeof(ct.c_void_p) == 8 else 6
            check(setupapi.SetupDiGetDeviceInterfaceDetailW(
                info_set, ct.byref(interface), detail, required.value, None, None), "SetupDiGetDeviceInterfaceDetailW")
            # DevicePath begins immediately after the cbSize DWORD; cbSize itself is
            # 8 on x64 because of trailing structure alignment.
            yield ct.wstring_at(ct.addressof(detail) + ct.sizeof(wt.DWORD))
            index += 1
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(info_set)


def open_logitech_collections(access=GENERIC_READ):
    collections = []
    for path in hid_paths():
        handle = kernel32.CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
        if handle == INVALID_HANDLE_VALUE:
            continue
        attrs = HIDD_ATTRIBUTES(ct.sizeof(HIDD_ATTRIBUTES), 0, 0, 0)
        if not hid.HidD_GetAttributes(handle, ct.byref(attrs)) or attrs.VendorID != 0x046D:
            kernel32.CloseHandle(handle)
            continue
        preparsed = ct.c_void_p()
        caps = HIDP_CAPS()
        if not hid.HidD_GetPreparsedData(handle, ct.byref(preparsed)):
            kernel32.CloseHandle(handle)
            continue
        try:
            if hid.HidP_GetCaps(preparsed, ct.byref(caps)) != HIDP_STATUS_SUCCESS:
                kernel32.CloseHandle(handle)
                continue
        finally:
            hid.HidD_FreePreparsedData(preparsed)
        collections.append((handle, path, attrs, caps))
    return collections


def read_reports(handle, path, attrs, caps):
    buf = ct.create_string_buffer(caps.InputReportByteLength)
    count = wt.DWORD()
    label = f"VID_{attrs.VendorID:04X} PID_{attrs.ProductID:04X} usage {caps.UsagePage:04X}:{caps.Usage:04X}"
    while True:
        if not kernel32.ReadFile(handle, buf, len(buf), ct.byref(count), None):
            print(f"[{label}] read ended: {ct.WinError(ct.get_last_error())}", flush=True)
            return
        print(f"[{label}] {bytes(buf[:count.value]).hex(' ')}\n  {path}", flush=True)


def main():
    collections = open_logitech_collections()
    if not collections:
        raise RuntimeError("No readable Logitech HID collections found.")
    for _, path, attrs, caps in collections:
        print(f"VID_{attrs.VendorID:04X} PID_{attrs.ProductID:04X}  usage {caps.UsagePage:04X}:{caps.Usage:04X}  input={caps.InputReportByteLength} bytes\n  {path}")
    if "--list" in sys.argv:
        return
    print("\nListening for HID reports. Test only one control at a time; Ctrl+C quits.\n")
    for collection in collections:
        threading.Thread(target=read_reports, args=collection, daemon=True).start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        # Explorer closes the temporary Python console as soon as the process
        # ends.  Leave the error visible when the script was double-clicked.
        try:
            input("\nProbe stopped. Press Enter to close this window...")
        except EOFError:
            pass
