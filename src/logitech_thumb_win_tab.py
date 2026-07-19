"""Make the MX Master 4 large thumb/Haptic button open Windows Task View.

Run manually:
    python .\\logitech_thumb_win_tab.py

This is intentionally not a service and does not install a startup task.  While
it is running it diverts only control 0x01A0 from the mouse and converts each
new press into Win+Tab.  Ctrl+C removes that temporary diversion.
"""

import ctypes as ct
from ctypes import wintypes as wt
from pathlib import Path
import sys


# The reusable device-discovery and HID++ helpers remain with the
# reverse-engineering tools, while this file is the small user-facing mapper.
REVERSE_DIR = Path(__file__).resolve().parents[1] / "reverse"
if str(REVERSE_DIR) not in sys.path:
    sys.path.insert(0, str(REVERSE_DIR))

import logitech_gatt_probe as gatt
import logitech_gatt_query as query
from logitech_hid_probe import kernel32, open_logitech_collections


THUMB_CONTROL = 0x01A0
VK_TAB = 0x09
VK_LWIN = 0x5B
KEYEVENTF_KEYUP = 0x0002
user32 = ct.WinDLL("user32", use_last_error=True)
user32.keybd_event.argtypes = [ct.c_ubyte, ct.c_ubyte, wt.DWORD, ct.c_void_p]
user32.keybd_event.restype = None


def set_thumb_diversion(enabled):
    """Temporarily send the physical thumb button as HID++ event 0."""
    path = query.find_vendor_service()
    handle = gatt.kernel32.CreateFileW(
        path, gatt.GENERIC_READ | query.GENERIC_WRITE,
        gatt.FILE_SHARE_READ | gatt.FILE_SHARE_WRITE, None, gatt.OPEN_EXISTING, 0, None,
    )
    if handle == gatt.INVALID_HANDLE_VALUE:
        raise ct.WinError(ct.get_last_error(), "opening Logitech vendor GATT service")
    try:
        characteristic = next(
            item for item in gatt.get_characteristics(handle)
            if gatt.uuid_text(item.CharacteristicUuid) == query.VENDOR_CHARACTERISTIC
        )
        # setCidReporting: dvalid=1, and set/clear the temporary divert bit.
        settings = 0x03 if enabled else 0x02
        query.send_request(handle, characteristic, bytes((
            0x0D, 0x3A, THUMB_CONTROL >> 8, THUMB_CONTROL & 0xFF, settings, 0x00, 0x00,
        )))
    finally:
        gatt.kernel32.CloseHandle(handle)


def send_win_tab():
    user32.keybd_event(VK_LWIN, 0, 0, None)
    user32.keybd_event(VK_TAB, 0, 0, None)
    user32.keybd_event(VK_TAB, 0, KEYEVENTF_KEYUP, None)
    user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, None)


def pressed_controls(report):
    # SpecialKeysMseButtons divertedButtonsEvent: report ID, device, feature,
    # event 0, then up to four big-endian control IDs that are currently held.
    if len(report) < 12 or report[:4] != b"\x11\xff\x0d\x00":
        return set()
    return {
        int.from_bytes(report[offset:offset + 2], "big")
        for offset in range(4, min(len(report), 12), 2)
        if report[offset:offset + 2] != b"\x00\x00"
    }


def main():
    target = next(
        (item for item in open_logitech_collections()
         if item[2].ProductID == 0xB042 and item[3].UsagePage == 0xFF43 and item[3].Usage == 0x0202),
        None,
    )
    if target is None:
        raise RuntimeError("MX Master 4 vendor HID endpoint was not found. Keep the mouse connected by Bluetooth.")
    handle, _, _, caps = target
    set_thumb_diversion(True)
    print("Thumb button -> Win+Tab is active. Ctrl+C stops and restores the normal button route.")
    held = set()
    buffer = ct.create_string_buffer(caps.InputReportByteLength)
    received = wt.DWORD()
    try:
        while True:
            if not kernel32.ReadFile(handle, buffer, len(buffer), ct.byref(received), None):
                raise ct.WinError(ct.get_last_error(), "reading Logitech HID input")
            now = pressed_controls(bytes(buffer[:received.value]))
            if THUMB_CONTROL in now and THUMB_CONTROL not in held:
                send_win_tab()
            if now or held:
                held = now
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        kernel32.CloseHandle(handle)
        try:
            set_thumb_diversion(False)
            print("Thumb button restored to its normal route.")
        except Exception as exc:
            print(f"Could not restore thumb-button routing: {exc}")


if __name__ == "__main__":
    main()
