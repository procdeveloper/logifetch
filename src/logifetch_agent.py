"""Configurable background agent for Logitech MX Master 4 Bluetooth controls.

The agent waits for the vendor HID collection, reapplies volatile HID++ mappings
after every Bluetooth reconnect, and sends configured Windows shortcuts for
diverted controls. It uses only the standard library and the checked-in reverse
engineering helpers.
"""

import argparse
import ctypes as ct
from ctypes import wintypes as wt
import json
import logging
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET


REVERSE_DIR = Path(__file__).resolve().parents[1] / "reverse"
if str(REVERSE_DIR) not in sys.path:
    sys.path.insert(0, str(REVERSE_DIR))

import logitech_gatt_query as query
from logitech_hid_probe import kernel32, open_logitech_collections


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config.json"
USER32 = ct.WinDLL("user32", use_last_error=True)
KEYEVENTF_KEYUP = 0x0002
USER32.keybd_event.argtypes = [ct.c_ubyte, ct.c_ubyte, wt.DWORD, ct.c_void_p]
USER32.keybd_event.restype = None

KEYS = {
    "alt": 0x12,
    "backspace": 0x08,
    "caps_lock": 0x14,
    "ctrl": 0x11,
    "delete": 0x2E,
    "down": 0x28,
    "end": 0x23,
    "enter": 0x0D,
    "esc": 0x1B,
    "home": 0x24,
    "left": 0x25,
    "page_down": 0x22,
    "page_up": 0x21,
    "right": 0x27,
    "shift": 0x10,
    "space": 0x20,
    "tab": 0x09,
    "up": 0x26,
    "win": 0x5B,
}
KEYS.update({f"f{number}": 0x6F + number for number in range(1, 25)})


def control_id(value):
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        parsed = int(value.removeprefix("0x"), 16)
    else:
        raise ValueError("control IDs must be hexadecimal strings")
    if not 0 <= parsed <= 0xFFFF:
        raise ValueError("control IDs must fit in 16 bits")
    return parsed


def virtual_key(name):
    normalized = name.casefold()
    if normalized in KEYS:
        return KEYS[normalized]
    if len(normalized) == 1 and normalized.isalnum():
        return ord(normalized.upper())
    raise ValueError(f"unsupported shortcut key: {name!r}")


def load_config(path):
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    for section in ("remapping", "custom_shortcuts", "settings", "haptics"):
        if section not in data:
            raise ValueError(f"configuration is missing the {section!r} section")
    if not isinstance(data["custom_shortcuts"], dict):
        raise ValueError("custom_shortcuts must map control IDs to arrays of key names")
    for raw_control, keys in data["custom_shortcuts"].items():
        control_id(raw_control)
        if not isinstance(keys, list):
            raise ValueError(f"shortcut for {raw_control!r} must be an array of key names")
        for key in keys:
            virtual_key(key)
    for item in data["remapping"].get("temporary", []):
        control_id(item["source"])
        control_id(item["target"])
    return data


def pressed_controls(report):
    """Decode the observed SpecialKeysMseButtons diverted-controls report."""
    if len(report) < 12 or report[:4] != b"\x11\xff\x0d\x00":
        return set()
    return {
        int.from_bytes(report[offset:offset + 2], "big")
        for offset in range(4, min(len(report), 12), 2)
        if report[offset:offset + 2] != b"\x00\x00"
    }


def send_shortcut(keys):
    virtual_keys = [virtual_key(key) for key in keys]
    for key in virtual_keys:
        USER32.keybd_event(key, 0, 0, None)
    for key in reversed(virtual_keys):
        USER32.keybd_event(key, 0, KEYEVENTF_KEYUP, None)


class EventLogWatcher(threading.Thread):
    """Poll selected Windows Event Log rules without external Python packages."""

    def __init__(self, config, emit, log):
        super().__init__(daemon=True, name="logifetch-event-log")
        self.config = config
        self.emit = emit
        self.log = log
        self.seen = set()

    def matching_records(self, rule):
        command = ["wevtutil", "qe", rule["channel"], "/rd:true", "/c:20", "/f:xml"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.log.warning("Could not inspect Windows Event Log: %s", exc)
            return []
        if result.returncode:
            self.log.warning("Event-log rule for %s failed: %s", rule["channel"], result.stderr.strip())
            return []
        try:
            root = ET.fromstring(result.stdout)
        except ET.ParseError as exc:
            self.log.warning("Could not parse Windows Event Log XML: %s", exc)
            return []
        namespace = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
        wanted_ids = {int(value) for value in rule.get("event_ids", [])}
        wanted_providers = {value.casefold() for value in rule.get("providers", [])}
        records = []
        for event in root.findall("e:Event", namespace):
            system = event.find("e:System", namespace)
            if system is None:
                continue
            provider = system.find("e:Provider", namespace)
            event_id = system.findtext("e:EventID", default="", namespaces=namespace)
            record_id = system.findtext("e:EventRecordID", default="", namespaces=namespace)
            provider_name = provider.get("Name", "") if provider is not None else ""
            if wanted_ids and int(event_id or -1) not in wanted_ids:
                continue
            if wanted_providers and provider_name.casefold() not in wanted_providers:
                continue
            records.append((rule["channel"], record_id, provider_name, event_id))
        return records

    def run(self):
        alert = self.config.get("notification_alert", {})
        rules = alert.get("rules", [])
        for rule in rules:
            self.seen.update(self.matching_records(rule))
        while True:
            for rule in rules:
                for record in self.matching_records(rule):
                    if record in self.seen:
                        continue
                    self.seen.add(record)
                    self.log.info("Windows notification alert: %s / %s (%s)", record[0], record[2], record[3])
                    self.emit("notification_alert")
            time.sleep(max(2, int(alert.get("poll_seconds", 10))))


class Agent:
    def __init__(self, config):
        self.config = config
        self.events = queue.SimpleQueue()
        # Empty arrays are deliberate placeholders: only non-empty entries are
        # diverted from their normal mouse behaviour.
        self.shortcuts = {
            control_id(raw): keys
            for raw, keys in config["custom_shortcuts"].items()
            if keys
        }
        log_file = Path(os.path.expandvars(config["settings"].get(
            "log_file", r"%LOCALAPPDATA%\Logifetch\logifetch.log"
        )))
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=log_file,
            level=getattr(logging, config["settings"].get("log_level", "INFO").upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(message)s",
        )
        self.log = logging.getLogger("logifetch")

    def emit(self, event):
        self.events.put(event)

    def trigger_haptic(self, event):
        haptics = self.config["haptics"]
        if not haptics.get("enabled") or not haptics.get("events", {}).get(event):
            return
        body_hex = haptics.get("pulse_hidpp_body_hex", "").replace(" ", "")
        if not body_hex:
            self.log.warning("Haptic event %s requested, but pulse_hidpp_body_hex is intentionally blank.", event)
            return
        try:
            query.send_vendor_request(bytes.fromhex(body_hex))
            self.log.info("Sent configured haptic alert for %s.", event)
        except (ValueError, OSError, RuntimeError) as exc:
            self.log.warning("Could not send haptic alert for %s: %s", event, exc)

    def apply_on_connect(self):
        for item in self.config["remapping"].get("temporary", []):
            source, target = control_id(item["source"]), control_id(item["target"])
            query.set_temporary_remap(source, target)
            self.log.info("Applied temporary remap %04X -> %04X", source, target)
        for control in self.shortcuts:
            query.set_control_diversion(control, True)
            self.log.info("Enabled custom-shortcut reporting for %04X", control)

    def find_mouse(self):
        settings = self.config["settings"]
        vendor_id = int(str(settings.get("vendor_id", "046D")).removeprefix("0x"), 16)
        product_id = int(str(settings.get("product_id", "B042")).removeprefix("0x"), 16)
        target = None
        for item in open_logitech_collections():
            handle, _, attributes, caps = item
            is_target = (
                attributes.VendorID == vendor_id and attributes.ProductID == product_id
                and caps.UsagePage == 0xFF43 and caps.Usage == 0x0202
            )
            if is_target and target is None:
                target = item
            else:
                kernel32.CloseHandle(handle)
        return target

    def handle_events(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            self.trigger_haptic(event)

    def read_connected_mouse(self, target):
        handle, _, _, caps = target
        held = set()
        buffer = ct.create_string_buffer(caps.InputReportByteLength)
        received = wt.DWORD()
        while True:
            self.handle_events()
            if not kernel32.ReadFile(handle, buffer, len(buffer), ct.byref(received), None):
                raise ct.WinError(ct.get_last_error(), "reading Logitech HID input")
            now = pressed_controls(bytes(buffer[:received.value]))
            for control in now - held:
                shortcut = self.shortcuts.get(control)
                if shortcut:
                    send_shortcut(shortcut)
                    self.log.info("Sent shortcut for control %04X", control)
            held = now

    def run(self):
        haptics = self.config["haptics"]
        alert = haptics.get("notification_alert", {})
        if alert.get("enabled"):
            # This watcher invokes haptics directly, rather than waiting for a
            # HID report; otherwise an idle mouse could delay an alert forever.
            EventLogWatcher(haptics, self.trigger_haptic, self.log).start()
        self.emit("agent_started")
        reconnect_delay = max(1, int(self.config["settings"].get("reconnect_delay_seconds", 3)))
        self.log.info("Logifetch agent started.")
        while True:
            self.handle_events()
            target = self.find_mouse()
            if target is None:
                time.sleep(reconnect_delay)
                continue
            try:
                self.log.info("MX Master 4 connected; applying configuration.")
                self.apply_on_connect()
                self.emit("mouse_connected")
                self.handle_events()
                self.read_connected_mouse(target)
            except Exception as exc:
                self.log.warning("Mouse session ended: %s", exc)
            finally:
                kernel32.CloseHandle(target[0])
            time.sleep(reconnect_delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--check-config", action="store_true", help="validate the configuration and exit")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.check_config:
        print(f"Configuration is valid: {args.config}")
        return
    Agent(config).run()


if __name__ == "__main__":
    main()
