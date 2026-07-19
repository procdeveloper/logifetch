# logifetch

Small, local Windows tools for exploring and customizing Logitech mouse controls.

## Run the mapper

`src/logitech_thumb_win_tab.py` temporarily maps the MX Master 4 large thumb / Haptic Sense button to Windows Task View (`Win+Tab`). It is intentionally a manual process: it does not install a service or startup task.

```powershell
python .\src\logitech_thumb_win_tab.py
```

Press `Ctrl+C` to stop it and restore the button's normal route.

## Reverse-engineering material

The HID and Bluetooth LE GATT exploration tools, raw input watcher, and capture notes are in [`reverse/`](reverse/). They are useful for investigating controls and reports, rather than required for ordinary mapper use.

## Status and safety

This is currently tailored to the Logitech MX Master 4 on Windows over Bluetooth LE. The runtime mapper makes a temporary device configuration change while it runs, then clears it when stopped. Review the notes and tool docstrings before sending configuration commands to a device.
