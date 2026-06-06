import os
import time
import platform
import socket
import psutil
from datetime import datetime


class SysInfo:
    """Collects and surfaces system information across all categories.

    Usage::

        from toolbook.tSys import SysInfo

        info = SysInfo()          # collects everything on init
        info.all()                # -> dict with all sections
        info.system()             # -> dict with OS / machine info
        info.cpu()                # -> dict with CPU info
        info.memory()             # -> dict with RAM info
        info.disk()               # -> list of dicts, one per partition
        info.battery()            # -> dict with battery info
        info.network()            # -> dict with hostname / IP
        info.boot()               # -> dict with last boot time
    """

    def __init__(self) -> None:
        self._data = {
            "system": self._collect_system(),
            "cpu": self._collect_cpu(),
            "memory": self._collect_memory(),
            "disk": self._collect_disk(),
            "battery": self._collect_battery(),
            "network": self._collect_network(),
            "uptime": self._collect_uptime(),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def all(self) -> dict:
        """Return all system information as a single dict."""
        return self._data

    def system(self) -> dict:
        """Return OS / machine information."""
        return self._data["system"]

    def cpu(self) -> dict:
        """Return CPU information."""
        return self._data["cpu"]

    def memory(self) -> dict:
        """Return RAM / virtual memory information."""
        return self._data["memory"]

    def disk(self) -> list:
        """Return a list of dicts, one per disk partition."""
        return self._data["disk"]

    def battery(self) -> dict:
        """Return battery status, or a note when no battery is present."""
        return self._data["battery"]

    def network(self) -> dict:
        """Return hostname and primary IP address."""
        return self._data["network"]

    def uptime(self) -> dict:
        """Return boot timestamp, uptime in seconds, and human-readable uptime."""
        return self._data["uptime"]

    # ------------------------------------------------------------------
    # Private collectors
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_system() -> dict:
        return {
            "system": platform.system(),
            "node_name": platform.node(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        }

    @staticmethod
    def _collect_cpu() -> dict:
        freq = psutil.cpu_freq()

        # os.getloadavg() is only available on Linux/macOS
        try:
            load_avg = list(os.getloadavg())
        except AttributeError:
            load_avg = None

        return {
            "physical_cores": psutil.cpu_count(logical=False),
            "total_cores": psutil.cpu_count(logical=True),
            "cpu_usage_percent": psutil.cpu_percent(interval=1),
            "cpu_per_core_usage": psutil.cpu_percent(percpu=True),
            "cpu_frequency_mhz": round(freq.current, 2) if freq else None,
            "cpu_max_frequency_mhz": round(freq.max, 2) if freq else None,
            "cpu_min_frequency_mhz": round(freq.min, 2) if freq else None,
            "cpu_load_average": load_avg,
        }

    @staticmethod
    def _collect_memory() -> dict:
        mem = psutil.virtual_memory()
        return {
            "total_ram_gb": round(mem.total / (1024**3), 2),
            "available_ram_gb": round(mem.available / (1024**3), 2),
            "used_ram_gb": round(mem.used / (1024**3), 2),
            "ram_usage_percent": mem.percent,
        }

    @staticmethod
    def _collect_disk() -> list:
        disks = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append(
                    {
                        "drive": partition.device,
                        "file_system": partition.fstype,
                        "total_space_gb": round(usage.total / (1024**3), 2),
                        "used_space_gb": round(usage.used / (1024**3), 2),
                        "free_space_gb": round(usage.free / (1024**3), 2),
                        "usage_percent": usage.percent,
                    }
                )
            except PermissionError:
                continue
        return disks

    @staticmethod
    def _collect_battery() -> dict:
        battery = psutil.sensors_battery()
        if battery:
            return {
                "battery_percent": battery.percent,
                "charging": battery.power_plugged,
                "seconds_left": battery.secsleft,
            }
        return {"battery": "No battery detected"}

    @staticmethod
    def _collect_network() -> dict:
        return {
            "hostname": socket.gethostname(),
            "ip_address": socket.gethostbyname(socket.gethostname()),
        }

    @staticmethod
    def _collect_uptime() -> dict:
        boot_ts = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_ts)

        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60

        return {
            "boot_time": datetime.fromtimestamp(boot_ts).strftime("%Y-%m-%d %H:%M:%S"),
            "uptime_seconds": uptime_seconds,
            "uptime_minutes": round(uptime_seconds / 60, 2),
            "uptime_hours": round(uptime_seconds / 3600, 2),
            "uptime": f"{days}d {hours:02}h {minutes:02}m {seconds:02}s",
        }
