# System Info

All `sys info-*` commands accept a `--json` flag to output raw JSON instead of the formatted view.

---

### `sys info`
Show complete system information — OS, CPU, memory, disk, battery, network, and uptime — in one view.

```bash
toolbook sys info [--json]
```

**Example:**
```bash
toolbook sys info
toolbook sys info --json
```

**Python:**
```python
from toolbook.tSys import SysInfo

info = SysInfo()

# All sections at once
data = info.all()
print(data)
```

---

### `sys info-system`
Show OS and machine details (platform, node name, release, version, architecture, processor).

```bash
toolbook sys info-system [--json]
```

**Example:**
```bash
toolbook sys info-system
```

**Python:**
```python
from toolbook.tSys import SysInfo

info = SysInfo()
system = info.system()
# {
#   "system": "Windows",
#   "node_name": "MY-PC",
#   "release": "10",
#   "version": "10.0.22621",
#   "machine": "AMD64",
#   "processor": "Intel64 Family 6 ..."
# }
print(system["system"])
print(system["node_name"])
```

---

### `sys info-cpu`
Show CPU core count, usage percentage, per-core usage bars, clock frequencies, and load average.

```bash
toolbook sys info-cpu [--json]
```

**Example:**
```bash
toolbook sys info-cpu
```

**Python:**
```python
from toolbook.tSys import SysInfo

info = SysInfo()
cpu = info.cpu()
# {
#   "physical_cores": 8,
#   "total_cores": 16,
#   "cpu_usage_percent": 12.5,
#   "cpu_per_core_usage": [10.0, 14.0, ...],
#   "cpu_frequency_mhz": 2400.0,
#   "cpu_max_frequency_mhz": 4800.0,
#   "cpu_min_frequency_mhz": 400.0,
#   "cpu_load_average": null   # None on Windows
# }
print(f"Cores  : {cpu['total_cores']}")
print(f"Usage  : {cpu['cpu_usage_percent']}%")
```

---

### `sys info-memory`
Show total, available, and used RAM with usage percentage.

```bash
toolbook sys info-memory [--json]
```

**Example:**
```bash
toolbook sys info-memory
```

**Python:**
```python
from toolbook.tSys import SysInfo

info = SysInfo()
mem = info.memory()
# {
#   "total_ram_gb": 16.0,
#   "available_ram_gb": 9.4,
#   "used_ram_gb": 6.6,
#   "ram_usage_percent": 41.2
# }
print(f"RAM: {mem['used_ram_gb']} GB / {mem['total_ram_gb']} GB ({mem['ram_usage_percent']}%)")
```

---

### `sys info-disk`
Show all disk partitions with file system type, total/used/free space, and usage percentage.

```bash
toolbook sys info-disk [--json]
```

**Example:**
```bash
toolbook sys info-disk
```

**Python:**
```python
from toolbook.tSys import SysInfo

info = SysInfo()
disks = info.disk()   # returns a list, one dict per partition
# [
#   {
#     "drive": "C:\\",
#     "file_system": "NTFS",
#     "total_space_gb": 476.84,
#     "used_space_gb": 120.5,
#     "free_space_gb": 356.34,
#     "usage_percent": 25.3
#   },
#   ...
# ]
for disk in disks:
    print(f"{disk['drive']}  {disk['usage_percent']}% used")
```

---

### `sys info-battery`
Show battery charge percentage, charging state, and estimated time remaining.

```bash
toolbook sys info-battery [--json]
```

**Example:**
```bash
toolbook sys info-battery
```

**Python:**
```python
from toolbook.tSys import SysInfo

info = SysInfo()
battery = info.battery()
# {
#   "battery_percent": 87.0,
#   "charging": True,
#   "seconds_left": -1
# }
# — or on a desktop —
# { "battery": "No battery detected" }
print(battery)
```

---

### `sys info-network`
Show hostname and primary IP address.

```bash
toolbook sys info-network [--json]
```

**Example:**
```bash
toolbook sys info-network
```

**Python:**
```python
from toolbook.tSys import SysInfo

info = SysInfo()
net = info.network()
# {
#   "hostname": "MY-PC",
#   "ip_address": "192.168.1.42"
# }
print(f"{net['hostname']}  {net['ip_address']}")
```

---

### `sys info-uptime`
Show the boot timestamp and time elapsed since last power-on.

```bash
toolbook sys info-uptime [--json]
```

**Example:**
```bash
toolbook sys info-uptime
# Booted At    2026-05-30 06:23:55
# Seconds      440,684 s
# Minutes      7,344.73 min
# Hours        122.41 hr
# Total Uptime 5d 02h 24m 44s
```

**Python:**
```python
from toolbook.tSys import SysInfo

info = SysInfo()
uptime = info.uptime()
# {
#   "boot_time": "2026-05-30 06:23:55",
#   "uptime_seconds": 440684,
#   "uptime_minutes": 7344.73,
#   "uptime_hours": 122.41,
#   "uptime": "5d 02h 24m 44s"
# }
print(uptime["uptime"])
```

---

### `sys organize-files`
Organise files in a folder into typed sub-folders: Images, Videos, Documents, PDFs, Music, Archives, Others.

```bash
toolbook sys organize-files <FOLDER_PATH>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `FOLDER_PATH` | Yes | Path to the folder to organise |

**Example:**
```bash
toolbook sys organize-files C:\Users\me\Downloads
```

**Python:**
```python
from toolbook.tSys import FileOrganizer

# Organises the folder immediately on instantiation
FileOrganizer("C:/Users/me/Downloads")

# Or with a variable path
folder = "C:/Users/me/Desktop/Messy Folder"
FileOrganizer(folder)
```
