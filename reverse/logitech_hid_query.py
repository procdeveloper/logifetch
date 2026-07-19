"""Query (but never change) the MX Master 4 HID++ control table.

This sends only the documented-looking HID++ `get control info` requests found
in the local Logitech device cache. It does not write assignments or firmware.
"""

import ctypes as ct

from logitech_hid_probe import GENERIC_READ, GENERIC_WRITE, kernel32, open_logitech_collections


def read_one(handle, size):
    buffer = ct.create_string_buffer(size)
    received = ct.c_ulong()
    if not kernel32.ReadFile(handle, buffer, size, ct.byref(received), None):
        raise ct.WinError(ct.get_last_error(), "ReadFile")
    return bytes(buffer[:received.value])


def main():
    collections = open_logitech_collections(access=GENERIC_READ | GENERIC_WRITE)
    target = next(
        (item for item in collections
         if item[2].ProductID == 0xB042 and item[3].UsagePage == 0xFF43 and item[3].Usage == 0x0202),
        None,
    )
    if target is None:
        raise RuntimeError("MX Master 4 vendor endpoint (046D:B042, FF43:0202) was not found.")

    handle, _, _, caps = target
    print("Querying MX Master 4 control table (read-only):")
    # HID++ feature 0x1A, function 0x0D: query entries 0 through 8.
    for index in range(9):
        request = bytearray(caps.OutputReportByteLength)
        request[:5] = (0x10, 0xFF, 0x0D, 0x1A, index)
        wire = ct.create_string_buffer(bytes(request))
        written = ct.c_ulong()
        if not kernel32.WriteFile(handle, wire, len(request), ct.byref(written), None):
            raise ct.WinError(ct.get_last_error(), f"query control {index}")
        if written.value != len(request):
            raise RuntimeError(f"query control {index}: wrote {written.value} of {len(request)} bytes")
        print(f"{index}: {read_one(handle, caps.InputReportByteLength).hex(' ')}")


if __name__ == "__main__":
    main()
