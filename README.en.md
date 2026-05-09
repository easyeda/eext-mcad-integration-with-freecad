[简体中文](./README.md) | [English](#)

# Export to FreeCAD

Send PCB 3D models (STEP format) to FreeCAD via WebSocket for viewing and editing.

## Features

- Export PCB 3D models to FreeCAD via WebSocket
- Supports STEP format export
- Auto-install Python dependencies
- Progress bar display
- Easy menu operation

## Quick Start

### 1. Install FreeCAD WebSocket Server Script

#### Run script using Macro

1. **Open FreeCAD**
2. Click **Macro** → **Macro Editor** in the top menu bar
3. In the Macro Editor:
   - Click **New** to create a new macro
   - Paste the content of `script/pcb_importer_freecad.py`
   - Click **Save** and name it `pcb_importer`
   - Click **Execute** to run the script

The script will automatically detect and install the `websockets` dependency.

After successful startup, you will see output similar to:

```
Checking websockets library...
websockets library is installed
Initializing WebSocket server 0.0.0.0:8766
WebSocket server started successfully!
Address: ws://localhost:8766
FreeCAD environment detected, server started
Main thread timer registered (100ms polling)
Waiting for client connection...
```

### 2. Install Extension

1. **Install in JLCEDA Pro:**
   - Open JLCEDA Pro
   - Click **Extensions** → **Extension Manager**
   - Click **Install Extension** → **Install from Local File**
   - Select `build/dist/pcb-export-to-freecad_v1.0.0.eext`
   - Enable the extension and grant external interaction permissions

### 3. Use Extension

1. In the PCB editor, click **Export to FreeCAD** in the top menu
2. Select **Connect to FreeCAD** (ensure FreeCAD server is running)
3. After successful connection, select **Export to FreeCAD**
4. The PCB model will be automatically sent to FreeCAD and imported

## Menu Functions

| Menu Option | Description |
| ---------- | ----------- |
| Connect to FreeCAD | Connect to FreeCAD WebSocket server |
| Export to FreeCAD | Send PCB STEP file to FreeCAD |
| Check Connection Status | View current connection status with FreeCAD |
| Disconnect | Disconnect from FreeCAD |

## Technical Notes

- **Communication Method**: WebSocket
- **WebSocket Port**: 8766
- **File Format**: STEP (.step)
- **FreeCAD Version Requirement**: 1.0 or higher

## FAQ

**Q: Failed to connect to FreeCAD?**

A: Please ensure:

1. FreeCAD is running and the WebSocket server script is active
2. Port 8766 is not occupied
3. JLCEDA extension has external interaction permissions enabled

**Q: Need to install additional dependencies?**

A: The script will automatically install the `websockets` library on first run. If automatic installation fails, run manually:

```shell
"<FreeCAD installation directory>/bin/python.exe" -m pip install websockets==13.1
```

**Q: FreeCAD has no response after import?**

A: Please ensure **View → Panels → Report View** is open in FreeCAD to check for error logs.

## Open Source License

This extension is licensed under the [Apache License 2.0](https://choosealicense.com/licenses/apache-2.0/).