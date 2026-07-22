# logifetch

Configurable, local Windows tools for Logitech mouse controls. The main agent re-applies volatile HID++ remaps after an MX Master 4 reconnects over Bluetooth LE, then turns diverted buttons into Windows shortcuts.

## What is it and why it exists

Logifetch is a small, open local alternative for the specific controls that Logitech's software does not expose the way we want. It reads the MX Master 4's vendor HID++ reports, reapplies chosen temporary button mappings after a Bluetooth reconnect, and can map selected buttons to ordinary Windows keyboard shortcuts.

The goal is not to replace every part of Logi Options+. It is to keep a few useful device customizations running independently, visibly, and with a plain JSON configuration.

### Supported product and platform

Current support is deliberately narrow:

- **Mouse:** Logitech MX Master 4 (`046D:B042`)
- **Connection:** Bluetooth Low Energy / Logitech vendor HID++ collection
- **Operating system:** Windows 10 and Windows 11

Other Logitech models, receiver connections, and macOS/Linux are not supported yet. The hardware identifiers are configurable, but changing them is experimental until their reports and configuration transport have been captured.

## Install the background agent

Python 3 is the only dependency. From an ordinary, non-administrator PowerShell window:

```powershell
powershell -ExecutionPolicy Bypass -File .\Install-Logifetch.ps1
```

The installer copies the agent and protocol helpers to `%LOCALAPPDATA%\Logifetch`, preserves an existing `config.json`, adds a per-user **Logifetch** entry to the Windows Run key so it starts at logon, and starts it once immediately. It works on Windows 10 and Windows 11 without administrator rights.

To remove the agent, its current-user Run entry, and its local configuration:

```powershell
powershell -ExecutionPolicy Bypass -File .\Install-Logifetch.ps1 -Remove
```

## Configure it

Edit `%LOCALAPPDATA%\Logifetch\config.json` after installing (or edit the repository's [`config.json`](config.json) before the first install). The file has four top-level sections:

- `remapping.temporary` re-applies a temporary native HID++ mapping after each Bluetooth connection. Keep this empty unless you have tested the two control IDs.
- `custom_shortcuts` maps a human-readable button name to a Windows key combination. Every currently identified button is included as a placeholder; `[]` means the button stays untouched. The default maps `large_thumb_haptic` to `Win+Tab`.
- `settings` selects the mouse and reconnect/log behaviour.
- `haptics` is opt-in. It can react to agent startup, mouse connection, or matching Windows Event Log records rather than using haptic feedback for every button press.

For example, the tested wheel/middle swap can be added to `remapping.temporary`:

```json
[
  { "source": "magspeed_mode_shift", "target": "middle_click" },
  { "source": "middle_click", "target": "magspeed_mode_shift" }
]
```

The available button names are: `left_click`, `right_click`, `middle_click`, `back`, `forward`, `gesture`, `magspeed_mode_shift`, `thumb_wheel`, and `large_thumb_haptic`. Leave an entry as `[]` until you want Logifetch to divert it. Raw hexadecimal IDs remain supported for compatibility with existing configurations.

### Shortcut keywords

Each non-empty `custom_shortcuts` entry is an ordered JSON array of key names. Modifiers should come first, and Logifetch releases them in reverse order. For example, `"large_thumb_haptic": ["win", "tab"]` sends `Win+Tab`; `"gesture": ["ctrl", "shift", "s"]` sends `Ctrl+Shift+S`.

The accepted keywords are:

- Modifiers: `alt`, `ctrl`, `shift`, `win`
- Navigation: `up`, `down`, `left`, `right`, `home`, `end`, `page_up`, `page_down`
- Editing and system keys: `backspace`, `caps_lock`, `delete`, `enter`, `esc`, `space`, `tab`
- Function keys: `f1` through `f24`
- Any single letter or number: `a` through `z`, and `0` through `9`

Names are case-insensitive. An unknown keyword makes the configuration validation fail instead of silently sending the wrong shortcut.

### Haptic notification alerts

The agent can poll selected Windows Event Log rules and use a matching event as a notification alert. The example rule watches for the Windows power-resume event. Enable the relevant event flag and add the verified HID++ pulse body once it has been captured:

```json
"haptics": {
  "enabled": true,
  "pulse_hidpp_body_hex": "",
  "events": { "notification_alert": true }
}
```

`pulse_hidpp_body_hex` intentionally starts empty: the current captures confirm the BLE route for HID++ configuration, but do **not** yet identify the command that makes the mouse vibrate. Leaving it blank is safe; the agent logs the requested alert and sends no unverified device command. When that request is reverse engineered, place only the HID++ body (maximum 18 bytes, without the raw-HID report and device bytes) in this field.

## Reverse-engineering material

The HID and Bluetooth LE GATT exploration tools, raw input watcher, and capture notes are in [`reverse/`](reverse/). They are useful for adding more devices to the scripts, investigating controls and reports, rather than required for ordinary mapper use.

## Status and safety

This is currently tailored to the Logitech MX Master 4 on Windows over Bluetooth LE. The agent reapplies volatile device configuration every time it reconnects. Review the notes and tool docstrings before sending configuration commands to a device.
