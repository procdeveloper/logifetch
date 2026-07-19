"""Print raw Windows input from Logitech mouse controls.

Run from a terminal with the Logitech agent stopped:
    py raw_mouse_watch.py

Then rotate the thumb wheel and press Back/Forward.  Press Ctrl+C to quit.
No administrator rights or third-party packages are required.
"""

import ctypes as ct
from ctypes import wintypes as wt
import struct


user32 = ct.WinDLL("user32", use_last_error=True)

WM_INPUT = 0x00FF
WM_DESTROY = 0x0002
WM_QUIT = 0x0012
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RIM_TYPEHID = 2
RIDEV_INPUTSINK = 0x00000100
RIDEV_PAGEONLY = 0x00000020
RI_MOUSE_LEFT_BUTTON_DOWN = 0x0001
RI_MOUSE_LEFT_BUTTON_UP = 0x0002
RI_MOUSE_RIGHT_BUTTON_DOWN = 0x0004
RI_MOUSE_RIGHT_BUTTON_UP = 0x0008
RI_MOUSE_MIDDLE_BUTTON_DOWN = 0x0010
RI_MOUSE_MIDDLE_BUTTON_UP = 0x0020
RI_MOUSE_BUTTON_4_DOWN = 0x0040  # normally Browser Back
RI_MOUSE_BUTTON_4_UP = 0x0080
RI_MOUSE_BUTTON_5_DOWN = 0x0100  # normally Browser Forward
RI_MOUSE_BUTTON_5_UP = 0x0200
RI_MOUSE_WHEEL = 0x0400
RI_MOUSE_HWHEEL = 0x0800


class RAWINPUTDEVICE(ct.Structure):
    _fields_ = [
        ("usUsagePage", wt.USHORT),
        ("usUsage", wt.USHORT),
        ("dwFlags", wt.DWORD),
        ("hwndTarget", wt.HWND),
    ]


class WNDCLASSW(ct.Structure):
    _fields_ = [
        ("style", wt.UINT),
        ("lpfnWndProc", ct.c_void_p),
        ("cbClsExtra", ct.c_int),
        ("cbWndExtra", ct.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HCURSOR),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


def device_name(handle):
    """Return the Raw Input device path, e.g. one containing VID_046D."""
    size = wt.UINT(0)
    user32.GetRawInputDeviceInfoW(handle, 0x20000007, None, ct.byref(size))
    if not size.value:
        return "<unknown device>"
    buf = ct.create_unicode_buffer(size.value)
    user32.GetRawInputDeviceInfoW(handle, 0x20000007, buf, ct.byref(size))
    return buf.value


BUTTON_NAMES = {
    RI_MOUSE_LEFT_BUTTON_DOWN: "Left down",
    RI_MOUSE_LEFT_BUTTON_UP: "Left up",
    RI_MOUSE_RIGHT_BUTTON_DOWN: "Right down",
    RI_MOUSE_RIGHT_BUTTON_UP: "Right up",
    RI_MOUSE_MIDDLE_BUTTON_DOWN: "Middle down",
    RI_MOUSE_MIDDLE_BUTTON_UP: "Middle up",
    RI_MOUSE_BUTTON_4_DOWN: "Back/XButton1 down",
    RI_MOUSE_BUTTON_4_UP: "Back/XButton1 up",
    RI_MOUSE_BUTTON_5_DOWN: "Forward/XButton2 down",
    RI_MOUSE_BUTTON_5_UP: "Forward/XButton2 up",
}


def print_raw_input(lparam):
    size = wt.UINT(0)
    user32.GetRawInputData(lparam, RID_INPUT, None, ct.byref(size), 24 if ct.sizeof(ct.c_void_p) == 8 else 16)
    buf = (ct.c_ubyte * size.value)()
    got = user32.GetRawInputData(lparam, RID_INPUT, buf, ct.byref(size), 24 if ct.sizeof(ct.c_void_p) == 8 else 16)
    if got == 0xFFFFFFFF:
        raise ct.WinError(ct.get_last_error())

    raw = bytes(buf)
    header_size = 24 if ct.sizeof(ct.c_void_p) == 8 else 16
    kind = struct.unpack_from("I", raw)[0]
    # hDevice is the third RAWINPUTHEADER member on both x86 and x64.
    hdevice_offset = 8 if ct.sizeof(ct.c_void_p) == 8 else 8
    hdevice = int.from_bytes(raw[hdevice_offset:hdevice_offset + ct.sizeof(ct.c_void_p)], "little")
    source = device_name(hdevice)

    if kind == RIM_TYPEMOUSE:
        # RAWMOUSE starts immediately after RAWINPUTHEADER.
        # RAWMOUSE has two padding bytes after usFlags before its button union.
        flags, buttons, raw_buttons, dx, dy = struct.unpack_from("<H2xIIii", raw, header_size)
        button_flags = buttons & 0xFFFF
        button_data = ct.c_short((buttons >> 16) & 0xFFFF).value
        events = [name for bit, name in BUTTON_NAMES.items() if button_flags & bit]
        if button_flags & RI_MOUSE_WHEEL:
            events.append(f"vertical wheel {button_data:+d}")
        if button_flags & RI_MOUSE_HWHEEL:
            events.append(f"HORIZONTAL wheel {button_data:+d}")
        if events or dx or dy:
            print(f"MOUSE  {', '.join(events) or f'move dx={dx} dy={dy}'}\n       {source}", flush=True)
    elif kind == RIM_TYPEHID:
        # Report-size and report-count follow the header; preserve every byte.
        report_size, report_count = struct.unpack_from("II", raw, header_size)
        report = raw[header_size + 8:]
        print(
            f"HID    {report_count} report(s) × {report_size} bytes: {report.hex(' ')}\n"
            f"       {source}",
            flush=True,
        )


WNDPROC = ct.WINFUNCTYPE(ct.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


@WNDPROC
def wndproc(hwnd, msg, wparam, lparam):
    if msg == WM_INPUT:
        print_raw_input(lparam)
        return 0
    if msg == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def main():
    instance = ct.WinDLL("kernel32", use_last_error=True).GetModuleHandleW(None)
    wc = WNDCLASSW(0, ct.cast(wndproc, ct.c_void_p), 0, 0, instance, None, None, None, None, "RawMouseWatch")
    if not user32.RegisterClassW(ct.byref(wc)):
        raise ct.WinError(ct.get_last_error())
    hwnd = user32.CreateWindowExW(0, "RawMouseWatch", "", 0, 0, 0, 0, 0, None, None, instance, None)

    # INPUTSINK keeps delivery even if another app has focus.  The vendor page
    # catches Logitech controls that are not published as a normal mouse wheel.
    devices = (RAWINPUTDEVICE * 3)(
        RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, hwnd),       # Generic Desktop / Mouse
        RAWINPUTDEVICE(0x0C, 0x01, RIDEV_INPUTSINK, hwnd),       # Consumer Control
        RAWINPUTDEVICE(0xFF00, 0, RIDEV_INPUTSINK | RIDEV_PAGEONLY, hwnd),
    )
    if not user32.RegisterRawInputDevices(devices, len(devices), ct.sizeof(RAWINPUTDEVICE)):
        raise ct.WinError(ct.get_last_error())

    print("Watching raw mouse input. Rotate the thumb wheel and press Back/Forward; Ctrl+C quits.")
    msg = wt.MSG()
    while user32.GetMessageW(ct.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ct.byref(msg))
        user32.DispatchMessageW(ct.byref(msg))


if __name__ == "__main__":
    main()
