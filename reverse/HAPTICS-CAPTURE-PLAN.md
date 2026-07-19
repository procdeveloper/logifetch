# Haptics capture plan

`logifetch` deliberately does not guess a vibration command. We have confirmed a writable Logitech BLE GATT characteristic and can send a known HID++ body through it, but have not yet captured the HID++ body that triggers a haptic pulse.

## Goal

Capture an outbound request associated with one deliberately triggered Haptic Sense effect, then verify it is safe and repeatable before putting it in `config.json` as `haptics.pulse_hidpp_body_hex`.

## First pass: establish a timestamped baseline

1. Keep the mouse connected over Bluetooth LE.
2. Start the read-only vendor-HID probe in one PowerShell window:

   ```powershell
   python .\reverse\logitech_hid_probe.py
   ```

3. In a second window, inventory the vendor GATT characteristics and readable values:

   ```powershell
   python .\reverse\logitech_gatt_probe.py --values
   ```

4. Trigger exactly one haptic effect in Logi Options+ (for example, one button-feedback action), write down its time, then wait five seconds.
5. Save all packets around that time. Repeat the same one-action test at least three times, with a quiet baseline between runs.

The HID probe may expose an acknowledgement or a state-change event. It cannot, by itself, see an outbound GATT write made by another process.

## If the HID probe has no useful difference

The next evidence needed is a Bluetooth LE / HID++ transport trace of Logi Options+ while it performs one haptic action. Do not replay arbitrary captured traffic. First identify the request bytes that differ between a no-op baseline and a single haptic action, then test only a single candidate against a connected mouse.

Record these facts with every candidate:

- the full 18-byte-or-shorter HID++ body, excluding raw-HID report ID `0x10` and device ID `0xFF`;
- the specific UI action that caused it;
- whether the mouse visibly/vibrationally responded;
- any vendor-HID response; and
- whether repeating the request is harmless.

Only a confirmed body belongs in `haptics.pulse_hidpp_body_hex`. Until then, keep the field empty: an enabled haptics event will only be logged, not sent to the mouse.
