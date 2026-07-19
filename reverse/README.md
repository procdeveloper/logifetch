# Logitech HID reverse-engineering notes

This is a running capture log for a minimal local MX Master 4 mapper. Values are recorded from direct HID reads while Logi Options+ input processes are stopped.

## Device endpoint

| Field | Value |
| --- | --- |
| Mouse | Logitech MX Master 4 |
| Connection observed | Bluetooth LE HID |
| Vendor ID | `046D` |
| Product ID | `B042` |
| Top-level HID usage | `FF43:0202` (vendor-defined) |
| Input report length | 20 bytes |
| Interface | `\\?\hid#{00001812-0000-1000-8000-00805f9b34fb}_dev_vid&02046d_pid&b042_rev&0015_d7aa41103bda&col02#b&1ad30b4a&0&0001#{4d1e55b2-f16f-11cf-88cb-001111000030}` |

## Controls

### Left click

Captured as one press report followed by one release report.

| Action | Raw 20-byte report |
| --- | --- |
| Press | `11 ff 0d 20 00 50 01 00 00 00 00 00 00 00 00 00 00 00 00 00` |
| Release | `11 ff 0d 20 00 50 00 00 00 00 00 00 00 00 00 00 00 00 00 00` |

Tentative interpretation: bytes 4–5 form a big-endian control ID (`0x0050`); byte 6 is its state (`0x01` pressed, `0x00` released). The preceding bytes are not yet interpreted.

### Main-wheel click (middle click)

| Action | Raw 20-byte report |
| --- | --- |
| Press | `11 ff 0d 20 00 52 01 00 00 00 00 00 00 00 00 00 00 00 00 00` |
| Release | `11 ff 0d 20 00 52 00 00 00 00 00 00 00 00 00 00 00 00 00 00` |

Control ID is `0x0052`; byte 6 is its press state. Do not inject a replacement middle click unless separate testing shows Windows fails to receive the native one.

### Right click

| Action | Raw 20-byte report |
| --- | --- |
| Press | `11 ff 0d 20 00 51 01 00 00 00 00 00 00 00 00 00 00 00 00 00` |
| Release | `11 ff 0d 20 00 51 00 00 00 00 00 00 00 00 00 00 00 00 00 00` |

Confirmed: bytes 4–5 are `0x0051` for the right button and byte 6 is the press state.

### Large thumb / gesture button

Each transition emits two reports. The second is the actionable button-state report.

| Action | Actionable report |
| --- | --- |
| Press | `11 ff 0d 20 01 a0 01 00 00 00 00 00 00 00 00 00 00 00 00 00` |
| Release | `11 ff 0d 20 01 a0 00 00 00 00 00 00 00 00 00 00 00 00 00 00` |

Control ID is `0x01A0`; the state remains byte 6 (`0x01` pressed, `0x00` released). Companion packets were observed on press (`11 ff 0d 00 01 a0 00 ...`) and release (`11 ff 0d 00 00 00 ...`); they are not required to detect the button state.

### Back button

| Action | Actionable report | Planned Windows output |
| --- | --- | --- |
| Press | `11 ff 0d 20 00 53 01 00 00 00 00 00 00 00 00 00 00 00 00 00` | XButton1 down |
| Release | `11 ff 0d 20 00 53 00 00 00 00 00 00 00 00 00 00 00 00 00 00` | XButton1 up |

Control ID is `0x0053`; byte 6 is its press state. As with the large thumb button, the device sends companion notifications before each actionable report; the mapper should ignore those.

### Forward button

| Action | Actionable report | Planned Windows output |
| --- | --- | --- |
| Press | `11 ff 0d 20 00 56 01 00 00 00 00 00 00 00 00 00 00 00 00 00` | XButton2 down |
| Release | `11 ff 0d 20 00 56 00 00 00 00 00 00 00 00 00 00 00 00 00 00` | XButton2 up |

Control ID is `0x0056`; byte 6 is its press state. Companion notifications use the same pattern as Back and should be ignored.

### Gesture button (third thumb-side button)

| Action | Actionable report |
| --- | --- |
| Press | `11 ff 0d 20 00 c3 01 00 00 00 00 00 00 00 00 00 00 00 00 00` |
| Release | `11 ff 0d 20 00 c3 00 00 00 00 00 00 00 00 00 00 00 00 00 00` |

Control ID is `0x00C3`; byte 6 is its press state. Default behavior for this control will be decided when building the mapper.

### MagSpeed wheel mode-shift button

| Action | Actionable report |
| --- | --- |
| Press | `11 ff 0d 20 00 c4 01 00 00 00 00 00 00 00 00 00 00 00 00 00` |
| Release | `11 ff 0d 20 00 c4 00 00 00 00 00 00 00 00 00 00 00 00 00 00` |

Control ID is `0x00C4`; byte 6 is its press state. The device's wheel-mode behavior should remain hardware-native unless explicitly remapped.

## Controls not observed on this endpoint

Pointer motion, main vertical-wheel scrolling, and the other ordinary mouse controls did not produce reports on the `FF43:0202` vendor endpoint. This probe alone cannot establish whether they are delivered through another HID collection, require Logitech initialization, or are unavailable without Logitech software. Do not assume they work natively until separately tested.

## Bluetooth re-pairing observation

After cycling the mouse pairing button and reconnecting Bluetooth, the reporting behavior changed:

| Control | Observed path after re-pairing |
| --- | --- |
| Thumb wheel / horizontal scroll | Standard Windows HID input |
| Back / Forward | Standard Windows XButton input |
| Main-wheel click | Standard middle-click behavior; Brave uses it for built-in autoscroll |
| Wheel mode-shift button | Still produces a Logitech HID report and changes wheel mode in hardware |
| Large thumb / Haptic Sense control | No event observed yet |
| Gesture button | No event observed yet |

The custom mapper should not inject horizontal scroll, Back, Forward, or middle click in this re-paired state: doing so would duplicate native events. Only the controls that remain unreported need further investigation.

## Device configuration boundary

The local Logitech device cache identifies the internal HID++ control table:

| Physical control | Internal ID |
| --- | --- |
| Gesture button | `0x00C3` |
| Wheel mode-shift button | `0x00C4` |
| Haptic Sense / large thumb control | `0x01A0` |
| Thumb wheel | `0x00D7` |

`logitech_hid_query.py` attempted a query-only HID++ control-table request on the Bluetooth vendor collection. Windows rejected both ordinary HID output methods (`HidD_SetOutputReport` and `WriteFile`) with WinError 87. No configuration was changed.

Conclusion: this interface permits raw event reads but does not expose the device's configuration channel as standard HID output. Reassigning controls or enabling the missing Haptic/Gesture reports requires Logitech's proprietary Bluetooth transport or a deeper reverse-engineering effort; it cannot be done by a simple standard-HID Python mapper alone.

## Bluetooth GATT configuration transport (confirmed)

The mouse exposes two Logitech BLE services in addition to the standard HID service:

| Service | Useful characteristic | Capability |
| --- | --- | --- |
| `0000FD72-0000-1000-8000-00805F9B34FB` | several vendor characteristics | Logitech service metadata |
| `00010000-0000-1000-8000-011F2000046D` | `00010001-0000-1000-8000-011F2000046D` | read, write, write-without-response, notify |

`logitech_gatt_probe.py` inventories these services without writing. `--values` additionally performs reads.

`logitech_gatt_query.py` sends HID++ request bodies through the second service. The BLE characteristic carries the 18-byte HID++ body **without** the raw-HID report ID (`0x10`) and device ID (`0xFF`). Responses arrive on the normal vendor HID input collection as 20-byte packets.

The known safe queries confirmed the whole control table and current reporting states. Before changes, controls `0x0052` (middle), `0x00C3` (gesture), `0x00C4` (mode shift), and `0x01A0` (Haptic Sense) had neither diversion nor remapping configured.

### Requested wheel/middle swap (active test)

The device supports HID++ `SpecialKeysMseButtons` / feature page `0x1B04`; all relevant controls are in compatible remapping groups. The following two **temporary** device remaps were accepted and echoed by the mouse:

```text
0x00C4 (mode-shift button) -> 0x0052 (middle click)
0x0052 (wheel click)       -> 0x00C4 (mode shift)
```

These commands do not require a running agent. They are volatile HID++ configuration and can be reset by a HID++ configuration reset. The remap command is retained in `logitech_gatt_query.py` as:

```powershell
python .\logitech_gatt_query.py --temporary-remap 00c4 0052
python .\logitech_gatt_query.py --temporary-remap 0052 00c4
```

The large thumb/Haptic (`0x01A0`) and gesture (`0x00C3`) buttons can likewise be either remapped to another available native control or diverted to a minimal custom agent for arbitrary shortcuts. Their intended actions still need to be chosen.

### Runtime agent

`../src/logifetch_agent.py` replaces the original one-button proof of concept. It reapplies configured temporary remaps and button diversions after Bluetooth reconnects, then injects the configured Windows shortcuts. `../Install-Logifetch.ps1` installs it as a per-user logon task.

### Haptics

The Bluetooth transport path is known, but the HID++ request that triggers a haptic pulse has not yet been captured. See [`HAPTICS-CAPTURE-PLAN.md`](HAPTICS-CAPTURE-PLAN.md) for the evidence-gathering sequence. The runtime configuration intentionally keeps its haptic body empty until that request is confirmed.

### Drag behaviour

A captured click-drag-release sequence used control ID `0x50`, so it was a **left-button** drag (not a right-button drag). It emitted only the normal press and release reports; no extra report was emitted while moving the pointer. Pointer movement therefore travels through a separate standard mouse HID collection and does not need to be implemented by the custom mapper.

### Thumb wheel / horizontal scroll

The wheel reports on the same vendor endpoint as the buttons, using a different report family:

```text
11 ff 13 ...
```

The capture contains several movement bursts. Two use a non-negative-looking prefix, for example:

```text
11 ff 13 00 00 01 00 2d 02 02 00 00 00 00 00 00 00 00 00 00
11 ff 13 00 00 01 00 5c 02 02 00 00 00 00 00 00 00 00 00 00
```

The opposite-direction burst contains sign-extended fields, for example:

```text
11 ff 13 00 ff fe 00 00 01 02 00 00 00 00 00 00 00 00 00 00
11 ff 13 00 ff ff 00 1d 02 02 00 00 00 00 00 00 00 00 00 00
```

This proves the thumb wheel is readable directly without Logi Options+. The report layout and exact delta field are **not yet decoded**. Capture one slow notch right, pause, then one slow notch left to isolate the directional delta.

## Next captures needed

Capture one action at a time, with the raw HID probe running:

- Right click press and release
- Middle click press and release
- Back and Forward press/release
- Thumb wheel: one notch left, then one notch right
- Main wheel: one notch up, then one notch down
- Gesture button press/release
