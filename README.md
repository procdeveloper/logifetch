# logifetch

Configurable, local Windows tools for Logitech mouse controls. The main agent re-applies volatile HID++ remaps after an MX Master 4 reconnects over Bluetooth LE, then turns diverted buttons into Windows shortcuts.

## Install the background agent

Python 3 is the only dependency. From an ordinary, non-administrator PowerShell window:

```powershell
powershell -ExecutionPolicy Bypass -File .\Install-Logifetch.ps1
```

The installer copies the agent and protocol helpers to `%LOCALAPPDATA%\Logifetch`, preserves an existing `config.json`, creates a per-user **Logifetch** Task Scheduler task that starts at logon, and starts it once immediately. It works on Windows 10 and Windows 11.

To remove the agent, its current-user task, and its local configuration:

```powershell
powershell -ExecutionPolicy Bypass -File .\Install-Logifetch.ps1 -Remove
```

## Configure it

Edit `%LOCALAPPDATA%\Logifetch\config.json` after installing (or edit the repository's [`config.json`](config.json) before the first install). The file has four top-level sections:

- `remapping.temporary` re-applies a temporary native HID++ mapping after each Bluetooth connection. Keep this empty unless you have tested the two control IDs.
- `custom_shortcuts` maps a diverted control ID to a Windows key combination. Every currently identified control is included as a placeholder; `[]` means the control stays untouched. The default maps `01a0` (the large thumb / Haptic Sense button) to `Win+Tab`.
- `settings` selects the mouse and reconnect/log behaviour.
- `haptics` is opt-in. It can react to agent startup, mouse connection, or matching Windows Event Log records rather than using haptic feedback for every button press.

For example, the tested wheel/middle swap can be added to `remapping.temporary`:

```json
[
  { "source": "00c4", "target": "0052" },
  { "source": "0052", "target": "00c4" }
]
```

The currently listed control IDs are: `0050` left click, `0051` right click, `0052` middle click, `0053` Back, `0056` Forward, `00c3` gesture button, `00c4` MagSpeed mode-shift button, `00d7` thumb wheel, and `01a0` large thumb / Haptic Sense button. Leave an entry as `[]` until you want Logifetch to divert it.

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

The HID and Bluetooth LE GATT exploration tools, raw input watcher, and capture notes are in [`reverse/`](reverse/). They are useful for investigating controls and reports, rather than required for ordinary mapper use.

## Status and safety

This is currently tailored to the Logitech MX Master 4 on Windows over Bluetooth LE. The agent reapplies volatile device configuration every time it reconnects. Review the notes and tool docstrings before sending configuration commands to a device.
