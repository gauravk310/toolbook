import os
import re
import platform
import subprocess
import json
import tempfile
from pathlib import Path
from datetime import datetime
import webbrowser
import psutil
import wmi
from bs4 import BeautifulSoup


def SystemReport(output_path="advanced_system_report.html", open_report=False):
    """
    Create advanced Windows system report HTML
    with modern UI and Chart.js graphs.
    """

    c = wmi.WMI()

    # =====================================================
    # SYSTEM INFO
    # =====================================================

    system_info = {
        "System": platform.system(),
        "Node Name": platform.node(),
        "Release": platform.release(),
        "Version": platform.version(),
        "Machine": platform.machine(),
        "Processor": platform.processor(),
        "Boot Time": datetime.fromtimestamp(psutil.boot_time()).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    }

    # =====================================================
    # CPU INFO — per-core usage for chart
    # =====================================================

    per_core = psutil.cpu_percent(interval=1, percpu=True)
    cpu_info = {
        "Physical Cores": psutil.cpu_count(logical=False),
        "Total Cores": psutil.cpu_count(logical=True),
        "Overall CPU Usage": f"{sum(per_core) / len(per_core):.1f}%",
    }
    cpu_labels_json = json.dumps([f"Core {i}" for i in range(len(per_core))])
    cpu_data_json = json.dumps(per_core)

    # =====================================================
    # MEMORY INFO — for donut chart
    # =====================================================

    memory = psutil.virtual_memory()

    memory_info = {
        "Total RAM": f"{memory.total / (1024**3):.2f} GB",
        "Available RAM": f"{memory.available / (1024**3):.2f} GB",
        "Used RAM": f"{memory.used / (1024**3):.2f} GB",
        "RAM Usage": f"{memory.percent}%",
    }
    ram_used_gb = round(memory.used / (1024**3), 2)
    ram_free_gb = round(memory.available / (1024**3), 2)
    ram_cached_gb = round(
        (memory.total - memory.used - memory.available) / (1024**3), 2
    )

    # =====================================================
    # GPU INFO
    # =====================================================

    gpu_rows = ""
    try:
        for gpu in c.Win32_VideoController():
            gpu_rows += f"""
            <tr>
                <td>{gpu.Name}</td>
                <td>{gpu.DriverVersion}</td>
                <td>{gpu.VideoProcessor}</td>
                <td>{int(gpu.AdapterRAM or 0) // (1024**2)} MB</td>
            </tr>"""
    except Exception:
        gpu_rows = '<tr><td colspan="4" class="empty-row">Unable to fetch GPU information</td></tr>'

    # =====================================================
    # STORAGE INFO — for grouped bar chart
    # =====================================================

    disk_rows = ""
    disk_labels = []
    disk_used = []
    disk_free = []

    for partition in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            pct = usage.percent
            bar_color = "#ef4444" if pct > 85 else "#f59e0b" if pct > 60 else "#22c55e"
            disk_rows += f"""
            <tr>
                <td><span class="badge badge-blue">{partition.device}</span></td>
                <td>{partition.fstype}</td>
                <td>{usage.total / (1024**3):.1f} GB</td>
                <td>{usage.used / (1024**3):.1f} GB</td>
                <td>{usage.free / (1024**3):.1f} GB</td>
                <td>
                    <div class="usage-bar-wrap">
                        <div class="usage-bar" style="width:{pct}%; background:{bar_color};"></div>
                    </div>
                    <span class="usage-pct">{pct}%</span>
                </td>
            </tr>"""
            disk_labels.append(partition.device.rstrip("\\"))
            disk_used.append(round(usage.used / (1024**3), 2))
            disk_free.append(round(usage.free / (1024**3), 2))
        except Exception:
            continue

    disk_labels_json = json.dumps(disk_labels)
    disk_used_json = json.dumps(disk_used)
    disk_free_json = json.dumps(disk_free)

    # =====================================================
    # BATTERY INFO — live stats
    # =====================================================

    battery = psutil.sensors_battery()
    if battery:
        pct = battery.percent
        batt_color = "#ef4444" if pct < 20 else "#f59e0b" if pct < 50 else "#22c55e"
        time_left = (
            "Charging"
            if battery.power_plugged
            else f"{battery.secsleft // 3600}h {(battery.secsleft % 3600) // 60}m"
            if battery.secsleft != psutil.POWER_TIME_UNLIMITED
            else "Calculating..."
        )
        live_battery_html = f"""
        <div class="stat-grid" style="grid-template-columns:repeat(3,1fr);">
            <div class="stat-card">
                <div class="stat-icon" style="background:#1a2e1a; color:#22c55e;">🔋</div>
                <div class="stat-body">
                    <div class="stat-label">Charge Level</div>
                    <div class="stat-value" style="color:{batt_color};">{pct:.0f}%</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon" style="background:#1e2e3a; color:#4f8ef7;">⚡</div>
                <div class="stat-body">
                    <div class="stat-label">Status</div>
                    <div class="stat-value">{"Plugged In" if battery.power_plugged else "On Battery"}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon" style="background:#2a2a1e; color:#fbbf24;">⏱</div>
                <div class="stat-body">
                    <div class="stat-label">Time Remaining</div>
                    <div class="stat-value">{time_left}</div>
                </div>
            </div>
        </div>
        <div class="batt-bar-wrap" style="margin-bottom:20px;">
            <div class="batt-bar" style="width:{pct}%; background:{batt_color};"></div>
        </div>"""
    else:
        live_battery_html = '<div class="empty-message" style="margin-bottom:16px;">No battery detected — desktop system</div>'

    # =====================================================
    # BATTERY HEALTH — powercfg report
    # =====================================================

    design_capacity = 0
    full_charge_capacity = 0
    cycle_count = "Unknown"
    battery_health = 0.0
    battery_condition = "Unknown"
    capacity_loss = 0
    powercfg_ok = False

    try:
        _tmp_report = Path(tempfile.gettempdir()) / "_sr_battery_report.html"
        _cmd = f'powercfg /batteryreport /output "{_tmp_report}"'
        result = subprocess.run(
            _cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if result.returncode == 0 and _tmp_report.exists():
            with open(_tmp_report, "r", encoding="utf-8", errors="ignore") as _f:
                _soup = BeautifulSoup(_f, "html.parser")
            _text = _soup.get_text("\n")

            _dm = re.search(r"DESIGN CAPACITY\s+([\d,]+)\s+mWh", _text)
            _fm = re.search(r"FULL CHARGE CAPACITY\s+([\d,]+)\s+mWh", _text)
            _cm = re.search(r"CYCLE COUNT\s+(\d+)", _text)

            design_capacity = int(_dm.group(1).replace(",", "")) if _dm else 0
            full_charge_capacity = int(_fm.group(1).replace(",", "")) if _fm else 0
            cycle_count = int(_cm.group(1)) if _cm else "Unknown"

            if design_capacity > 0:
                battery_health = (full_charge_capacity / design_capacity) * 100
                capacity_loss = design_capacity - full_charge_capacity

            if battery_health >= 90:
                battery_condition = "Excellent"
            elif battery_health >= 75:
                battery_condition = "Good"
            elif battery_health >= 60:
                battery_condition = "Average"
            else:
                battery_condition = "Poor"

            powercfg_ok = True
    except Exception:
        pass

    _health_color = (
        "#ef4444"
        if battery_health < 60
        else "#f59e0b"
        if battery_health < 75
        else "#22c55e"
    )
    _condition_color = {
        "Excellent": "#22c55e",
        "Good": "#4f8ef7",
        "Average": "#f59e0b",
        "Poor": "#ef4444",
        "Unknown": "#8a95b0",
    }.get(battery_condition, "#8a95b0")

    if powercfg_ok:
        health_stats_html = f"""
        <div class="section-sub-title" style="font-size:12px;font-weight:600;text-transform:uppercase;
             letter-spacing:.08em;color:var(--text3);margin-bottom:12px;">Battery Health Report</div>
        <div class="stat-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:16px;">
            <div class="stat-card">
                <div class="stat-icon" style="background:#1a2e1a; color:#22c55e;">🩺</div>
                <div class="stat-body">
                    <div class="stat-label">Health</div>
                    <div class="stat-value" style="color:{_health_color};">{battery_health:.1f}%</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon" style="background:#2a1e3a; color:#c084fc;">🏷</div>
                <div class="stat-body">
                    <div class="stat-label">Condition</div>
                    <div class="stat-value" style="color:{_condition_color};">{battery_condition}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon" style="background:#1e2e3a; color:#60a5fa;">🔄</div>
                <div class="stat-body">
                    <div class="stat-label">Cycle Count</div>
                    <div class="stat-value">{cycle_count}</div>
                </div>
            </div>
        </div>
        <div class="stat-grid" style="grid-template-columns:repeat(3,1fr);">
            <div class="stat-card">
                <div class="stat-icon" style="background:#2a2a1e; color:#fbbf24;">⚗️</div>
                <div class="stat-body">
                    <div class="stat-label">Design Capacity</div>
                    <div class="stat-value" style="font-size:15px;">{design_capacity:,} mWh</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon" style="background:#1a2e1a; color:#4ade80;">⚡</div>
                <div class="stat-body">
                    <div class="stat-label">Full Charge</div>
                    <div class="stat-value" style="font-size:15px;">{full_charge_capacity:,} mWh</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon" style="background:#2a1e1e; color:#f87171;">📉</div>
                <div class="stat-body">
                    <div class="stat-label">Capacity Loss</div>
                    <div class="stat-value" style="font-size:15px;color:#ef4444;">{capacity_loss:,} mWh</div>
                </div>
            </div>
        </div>
        <div style="margin-top:14px;">
            <div style="font-size:11px;color:var(--text3);margin-bottom:6px;">Health bar</div>
            <div class="batt-bar-wrap">
                <div class="batt-bar" style="width:{battery_health:.1f}%; background:{_health_color};"></div>
            </div>
        </div>"""
    else:
        health_stats_html = '<div class="empty-message">Battery health report unavailable (powercfg failed or no battery)</div>'

    battery_html = live_battery_html + health_stats_html

    # =====================================================
    # RUNNING PROCESSES — top 10 for chart, top 25 for table
    # =====================================================

    all_procs = sorted(
        psutil.process_iter(["pid", "name", "memory_percent"]),
        key=lambda p: p.info["memory_percent"],
        reverse=True,
    )

    proc_top10 = []
    process_rows = ""

    for proc in all_procs[:25]:
        try:
            info = proc.info
            pct = info["memory_percent"]
            bar_w = min(pct * 10, 100)
            process_rows += f"""
            <tr>
                <td class="pid-cell">{info["pid"]}</td>
                <td class="proc-name">{info["name"]}</td>
                <td><div class="proc-bar-wrap"><div class="proc-bar" style="width:{bar_w}%;"></div></div></td>
                <td class="pct-cell">{pct:.2f}%</td>
            </tr>"""
            if len(proc_top10) < 10:
                proc_top10.append({"name": info["name"][:22], "pct": round(pct, 2)})
        except Exception:
            continue

    proc_names_json = json.dumps([p["name"] for p in proc_top10])
    proc_pcts_json = json.dumps([p["pct"] for p in proc_top10])

    # =====================================================
    # INSTALLED APPS
    # =====================================================

    installed_apps = []
    try:
        command = 'powershell "Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* |Select-Object DisplayName"'
        output = subprocess.check_output(command, shell=True).decode(errors="ignore")
        installed_apps = [a.strip() for a in output.splitlines()[1:80] if a.strip()]
    except Exception:
        installed_apps = ["Unable to fetch installed apps"]

    app_cards = ""
    for app in installed_apps:
        if app:
            initial = app[0].upper()
            app_cards += f'<div class="app-card"><div class="app-icon">{initial}</div><span>{app}</span></div>'

    # =====================================================
    # WIFI / DRIVERS
    # =====================================================

    # --- WiFi: parse key:value pairs into table rows ---
    try:
        _wifi_raw = subprocess.check_output(
            "netsh wlan show interfaces", shell=True
        ).decode(errors="ignore")
        wifi_rows = ""
        for line in _wifi_raw.splitlines():
            if ":" in line:
                parts = line.split(":", 1)
                key = parts[0].strip()
                val = parts[1].strip() if len(parts) > 1 else ""
                if key and val:
                    wifi_rows += f'<tr><td class="kv-key">{key}</td><td class="kv-val">{val}</td></tr>'
        if not wifi_rows:
            wifi_rows = '<tr><td colspan="2" class="empty-row">No active WiFi interface found</td></tr>'
    except Exception:
        wifi_rows = '<tr><td colspan="2" class="empty-row">WiFi information unavailable</td></tr>'

    # --- Drivers: parse fixed-width driverquery output into table rows ---
    try:
        _driver_raw = subprocess.check_output(
            "driverquery /fo csv /nh", shell=True
        ).decode(errors="ignore")
        driver_rows = ""
        for line in _driver_raw.splitlines():
            line = line.strip()
            if not line:
                continue
            cols = [c.strip('"') for c in line.split('","')]
            if len(cols) >= 4:
                name, display, kind, started = cols[0], cols[1], cols[2], cols[3]
                status_color = "#22c55e" if started.lower() == "true" else "#ef4444"
                status_text = "Running" if started.lower() == "true" else "Stopped"
                driver_rows += f"""
                <tr>
                    <td class="proc-name">{name}</td>
                    <td style="color:var(--text2);">{display}</td>
                    <td><span class="badge badge-blue">{kind}</span></td>
                    <td><span style="color:{status_color};font-weight:600;">{status_text}</span></td>
                </tr>"""
        if not driver_rows:
            driver_rows = '<tr><td colspan="4" class="empty-row">No driver data available</td></tr>'
    except Exception:
        driver_rows = '<tr><td colspan="4" class="empty-row">Unable to fetch driver information</td></tr>'

    # =====================================================
    # STARTUP APPS
    # =====================================================

    startup_items = []
    startup_folder = os.path.join(
        os.getenv("APPDATA"), r"Microsoft\Windows\Start Menu\Programs\Startup"
    )
    if os.path.exists(startup_folder):
        startup_items = os.listdir(startup_folder)

    startup_cards = "".join(
        f'<div class="startup-chip">{a}</div>' for a in startup_items
    )
    if not startup_cards:
        startup_cards = '<p class="empty-message">No startup applications found</p>'

    # =====================================================
    # JUNK FILE SCAN
    # =====================================================

    temp_dirs = [os.getenv("TEMP"), r"C:\Windows\Temp"]
    junk_size = 0
    junk_files = 0
    for folder in temp_dirs:
        if not folder:
            continue
        for root, dirs, files in os.walk(folder):
            for file in files:
                try:
                    junk_size += os.path.getsize(os.path.join(root, file))
                    junk_files += 1
                except Exception:
                    continue

    junk_size_mb = round(junk_size / (1024**2), 2)

    # =====================================================
    # WINDOWS ACTIVATION
    # =====================================================

    try:
        activation = (
            subprocess.check_output(
                'cscript //Nologo "%windir%\\system32\\slmgr.vbs" /xpr', shell=True
            )
            .decode(errors="ignore")
            .strip()
        )
    except Exception:
        activation = "Unable to fetch activation status"

    # =====================================================
    # HEALTH SCORE
    # =====================================================

    cpu_overall = sum(per_core) / len(per_core)
    health_score = round(
        max(
            0,
            100
            - cpu_overall * 0.2
            - memory.percent * 0.2
            - psutil.disk_usage("/").percent * 0.1,
        ),
        1,
    )
    health_color = (
        "#ef4444"
        if health_score < 50
        else "#f59e0b"
        if health_score < 75
        else "#22c55e"
    )
    health_label = (
        "Poor" if health_score < 50 else "Fair" if health_score < 75 else "Good"
    )

    # =====================================================
    # KV TABLE HELPER
    # =====================================================

    def kv_rows(data):
        return "".join(
            f'<tr><td class="kv-key">{k}</td><td class="kv-val">{v}</td></tr>'
            for k, v in data.items()
        )

    report_time = datetime.now().strftime("%A, %B %d %Y at %H:%M:%S")
    hostname = platform.node()

    # =====================================================
    # HTML
    # =====================================================

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>System Report — {hostname}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
:root{{
  --bg:#0f1117;--bg2:#161b27;--bg3:#1e2436;--bg4:#252d3d;
  --border:rgba(255,255,255,0.07);--border2:rgba(255,255,255,0.12);
  --text:#e8eaf0;--text2:#8a95b0;--text3:#5a6480;
  --accent:#4f8ef7;--accent2:#3b73e0;
  --green:#22c55e;--amber:#f59e0b;--red:#ef4444;
  --radius:12px;--radius-sm:8px;
  --mono:'JetBrains Mono',monospace;
}}
body{{font-family:'Inter',-apple-system,sans-serif;background:var(--bg);color:var(--text);font-size:14px;line-height:1.6;}}
.header{{background:linear-gradient(135deg,#0d1520 0%,#111827 50%,#0d1a2e 100%);border-bottom:1px solid var(--border);padding:40px 48px 32px;position:relative;overflow:hidden;}}
.header::before{{content:'';position:absolute;top:-80px;right:-80px;width:360px;height:360px;background:radial-gradient(circle,rgba(79,142,247,0.12) 0%,transparent 70%);pointer-events:none;}}
.header-inner{{max-width:1200px;margin:0 auto;display:flex;align-items:flex-start;justify-content:space-between;gap:24px;}}
.header-eyebrow{{font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:8px;}}
.header h1{{font-size:28px;font-weight:600;color:#fff;letter-spacing:-.02em;margin-bottom:6px;}}
.header-sub{{font-size:13px;color:var(--text2);}}
.health-badge{{display:flex;flex-direction:column;align-items:center;gap:4px;padding:16px 24px;background:var(--bg3);border:1px solid var(--border2);border-radius:var(--radius);min-width:120px;}}
.health-score-num{{font-size:36px;font-weight:600;line-height:1;}}
.health-score-label{{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--text2);}}
.nav{{background:var(--bg2);border-bottom:1px solid var(--border);padding:0 48px;position:sticky;top:0;z-index:100;}}
.nav-inner{{max-width:1200px;margin:0 auto;display:flex;gap:2px;overflow-x:auto;scrollbar-width:none;}}
.nav-inner::-webkit-scrollbar{{display:none;}}
.nav-tab{{padding:14px 16px;font-size:13px;font-weight:500;color:var(--text3);cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap;transition:color .2s,border-color .2s;text-decoration:none;}}
.nav-tab:hover{{color:var(--text2);}}
.nav-tab.active{{color:var(--accent);border-bottom-color:var(--accent);}}
.main{{max-width:1200px;margin:0 auto;padding:40px 48px;display:flex;flex-direction:column;gap:32px;}}
.card{{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;}}
.card-header{{padding:18px 24px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;}}
.card-icon{{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;}}
.card-title{{font-size:14px;font-weight:600;color:var(--text);letter-spacing:-.01em;}}
.card-count{{margin-left:auto;font-size:12px;color:var(--text3);background:var(--bg4);padding:2px 8px;border-radius:20px;}}
.card-body{{padding:20px 24px;}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:20px;}}
.col-span-2{{grid-column:span 2;}}
.chart-wrap{{position:relative;padding:20px 24px;}}
.chart-wrap canvas{{max-width:100%;}}
.chart-wrap-donut{{display:flex;align-items:center;gap:28px;padding:20px 24px;}}
.donut-canvas-wrap{{flex-shrink:0;width:180px;height:180px;}}
.donut-legend{{flex:1;display:flex;flex-direction:column;gap:10px;}}
.legend-item{{display:flex;align-items:center;gap:10px;font-size:13px;}}
.legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0;}}
.legend-label{{color:var(--text2);flex:1;}}
.legend-val{{color:var(--text);font-weight:500;font-variant-numeric:tabular-nums;}}
.kv-table{{width:100%;border-collapse:collapse;}}
.kv-table tr{{border-bottom:1px solid var(--border);}}
.kv-table tr:last-child{{border-bottom:none;}}
.kv-key{{padding:10px 0;color:var(--text2);font-size:13px;width:45%;vertical-align:top;}}
.kv-val{{padding:10px 0;color:var(--text);font-size:13px;font-weight:500;word-break:break-all;}}
.data-table{{width:100%;border-collapse:collapse;}}
.data-table th{{padding:10px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:var(--text3);text-align:left;border-bottom:1px solid var(--border);background:var(--bg3);}}
.data-table td{{padding:10px 12px;font-size:13px;color:var(--text2);border-bottom:1px solid var(--border);vertical-align:middle;}}
.data-table tr:last-child td{{border-bottom:none;}}
.data-table tr:hover td{{background:var(--bg3);color:var(--text);}}
.empty-row{{text-align:center;color:var(--text3);font-style:italic;padding:24px !important;}}
.usage-bar-wrap{{display:inline-block;width:80px;height:5px;background:var(--bg4);border-radius:3px;overflow:hidden;vertical-align:middle;margin-right:6px;}}
.usage-bar{{height:100%;border-radius:3px;}}
.usage-pct{{font-size:12px;color:var(--text2);font-variant-numeric:tabular-nums;}}
.proc-bar-wrap{{width:100%;height:4px;background:var(--bg4);border-radius:2px;overflow:hidden;}}
.proc-bar{{height:100%;background:var(--accent);border-radius:2px;}}
.pid-cell{{color:var(--text3);font-family:var(--mono);font-size:12px;}}
.proc-name{{color:var(--text);font-weight:500;}}
.pct-cell{{color:var(--text2);font-family:var(--mono);font-size:12px;text-align:right;}}
.stat-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px;}}
.stat-card{{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px;display:flex;align-items:center;gap:12px;}}
.stat-icon{{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;}}
.stat-label{{font-size:11px;color:var(--text3);margin-bottom:2px;}}
.stat-value{{font-size:18px;font-weight:600;color:var(--text);}}
.batt-bar-wrap{{width:100%;height:8px;background:var(--bg4);border-radius:4px;overflow:hidden;}}
.batt-bar{{height:100%;border-radius:4px;}}
.temp-badge{{display:inline-block;padding:2px 10px;border:1px solid;border-radius:20px;font-size:12px;font-weight:600;font-family:var(--mono);}}
.badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:500;font-family:var(--mono);}}
.badge-blue{{background:rgba(79,142,247,0.15);color:var(--accent);}}
.app-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;}}
.app-card{{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 12px;display:flex;align-items:center;gap:10px;font-size:12px;color:var(--text2);transition:border-color .2s;}}
.app-card:hover{{border-color:var(--border2);color:var(--text);}}
.app-icon{{width:28px;height:28px;border-radius:6px;background:var(--accent2);color:#fff;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;flex-shrink:0;}}
.chip-grid{{display:flex;flex-wrap:wrap;gap:8px;}}
.startup-chip{{background:var(--bg3);border:1px solid var(--border);border-radius:20px;padding:5px 14px;font-size:12px;color:var(--text2);}}
.code-block{{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:16px;font-family:var(--mono);font-size:12px;color:var(--text2);white-space:pre-wrap;word-break:break-all;line-height:1.7;max-height:320px;overflow-y:auto;}}
.code-block::-webkit-scrollbar{{width:6px;}}
.code-block::-webkit-scrollbar-thumb{{background:var(--bg4);border-radius:3px;}}
.junk-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;}}
.junk-tile{{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-sm);padding:18px;text-align:center;}}
.junk-num{{font-size:28px;font-weight:600;font-variant-numeric:tabular-nums;color:var(--text);line-height:1;margin-bottom:4px;}}
.junk-label{{font-size:12px;color:var(--text3);}}
.gauge-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:16px;padding:20px 24px;}}
.gauge-item{{display:flex;flex-direction:column;align-items:center;gap:6px;}}
.gauge-label{{font-size:11px;color:var(--text3);text-align:center;max-width:140px;word-break:break-all;}}
.empty-message{{color:var(--text3);font-style:italic;font-size:13px;padding:8px 0;}}
section{{scroll-margin-top:56px;}}
.footer{{border-top:1px solid var(--border);padding:24px 48px;text-align:center;font-size:12px;color:var(--text3);}}
@media(max-width:900px){{
  .header,.footer{{padding:24px;}}
  .header-inner{{flex-direction:column;}}
  .nav{{padding:0 16px;}}
  .main{{padding:24px 16px;}}
  .grid-2{{grid-template-columns:1fr;}}
  .col-span-2{{grid-column:span 1;}}
  .stat-grid{{grid-template-columns:1fr;}}
  .chart-wrap-donut{{flex-direction:column;}}
}}
</style>
</head>
<body>

<div class="header">
  <div class="header-inner">
    <div>
      <div class="header-eyebrow">Windows System Report</div>
      <h1>{hostname}</h1>
      <div class="header-sub">Generated {report_time}</div>
    </div>
    <div class="health-badge">
      <div class="health-score-num" style="color:{health_color};">{health_score}</div>
      <div class="health-score-label" style="color:{health_color};">{health_label}</div>
      <div class="health-score-label">health score</div>
    </div>
  </div>
</div>

<nav class="nav">
  <div class="nav-inner">
    <a class="nav-tab active" href="#overview">Overview</a>
    <a class="nav-tab" href="#storage">Storage</a>
    <a class="nav-tab" href="#battery">Battery</a>
    <a class="nav-tab" href="#processes">Processes</a>
    <a class="nav-tab" href="#network">Network</a>
    <a class="nav-tab" href="#drivers">Drivers</a>
  </div>
</nav>

<main class="main">

  <!-- OVERVIEW -->
  <section id="overview">
    <div class="grid-2">

      <div class="card">
        <div class="card-header">
          <div class="card-icon" style="background:#1e3a5f;color:#4f8ef7;">💻</div>
          <span class="card-title">System Information</span>
        </div>
        <div class="card-body"><table class="kv-table">{kv_rows(system_info)}</table></div>
      </div>

      <div style="display:flex;flex-direction:column;gap:20px;">
        <div class="card">
          <div class="card-header">
            <div class="card-icon" style="background:#1a3320;color:#22c55e;">⚙️</div>
            <span class="card-title">CPU</span>
          </div>
          <div class="card-body"><table class="kv-table">{kv_rows(cpu_info)}</table></div>
        </div>
        <div class="card">
          <div class="card-header">
            <div class="card-icon" style="background:#2d1f4a;color:#a78bfa;">🧠</div>
            <span class="card-title">Memory</span>
          </div>
          <div class="card-body"><table class="kv-table">{kv_rows(memory_info)}</table></div>
        </div>
      </div>

      <div class="card col-span-2">
        <div class="card-header">
          <div class="card-icon" style="background:#1e2e4a;color:#60a5fa;">🖥</div>
          <span class="card-title">GPU Information</span>
        </div>
        <div style="padding:0;">
          <table class="data-table">
            <thead><tr><th>Name</th><th>Driver Version</th><th>Processor</th><th>VRAM</th></tr></thead>
            <tbody>{gpu_rows}</tbody>
          </table>
        </div>
      </div>

      <!-- GRAPH 1: CPU per-core bar -->
      <div class="card">
        <div class="card-header">
          <div class="card-icon" style="background:#1a3320;color:#22c55e;">📈</div>
          <span class="card-title">CPU Usage — per core</span>
        </div>
        <div class="chart-wrap" style="height:220px;">
          <canvas id="cpuChart"></canvas>
        </div>
      </div>

      <!-- GRAPH 2: RAM donut -->
      <div class="card">
        <div class="card-header">
          <div class="card-icon" style="background:#2d1f4a;color:#a78bfa;">🧠</div>
          <span class="card-title">RAM Breakdown</span>
        </div>
        <div class="chart-wrap-donut">
          <div class="donut-canvas-wrap"><canvas id="ramChart"></canvas></div>
          <div class="donut-legend">
            <div class="legend-item">
              <div class="legend-dot" style="background:#a78bfa;"></div>
              <span class="legend-label">Used</span>
              <span class="legend-val">{ram_used_gb} GB</span>
            </div>
            <div class="legend-item">
              <div class="legend-dot" style="background:#22c55e;"></div>
              <span class="legend-label">Available</span>
              <span class="legend-val">{ram_free_gb} GB</span>
            </div>
            <div class="legend-item">
              <div class="legend-dot" style="background:#3b73e0;"></div>
              <span class="legend-label">Cached / Other</span>
              <span class="legend-val">{ram_cached_gb} GB</span>
            </div>
            <div class="legend-item" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border);">
              <span class="legend-label" style="color:var(--text3);font-size:12px;">Total usage</span>
              <span class="legend-val" style="font-size:20px;">{memory.percent}%</span>
            </div>
          </div>
        </div>
      </div>

    </div>
  </section>

  <!-- STORAGE -->
  <section id="storage">
    <div style="display:flex;flex-direction:column;gap:20px;">
      <!-- GRAPH 3: Disk grouped bar -->
      <div class="card">
        <div class="card-header">
          <div class="card-icon" style="background:#1a2e1a;color:#4ade80;">📊</div>
          <span class="card-title">Disk Space by Drive</span>
        </div>
        <div class="chart-wrap" style="height:240px;">
          <canvas id="diskChart"></canvas>
        </div>
      </div>
      <div class="card">
        <div class="card-header">
          <div class="card-icon" style="background:#1a2e1a;color:#4ade80;">💾</div>
          <span class="card-title">Storage Details</span>
        </div>
        <div style="padding:0;">
          <table class="data-table">
            <thead><tr><th>Drive</th><th>File System</th><th>Total</th><th>Used</th><th>Free</th><th>Usage</th></tr></thead>
            <tbody>{disk_rows}</tbody>
          </table>
        </div>
      </div>
    </div>
  </section>

  <!-- BATTERY -->
  <section id="battery">
    <div class="card">
      <div class="card-header">
        <div class="card-icon" style="background:#1a2e1a;color:#4ade80;">🔋</div>
        <span class="card-title">Battery</span>
      </div>
      <div class="card-body">{battery_html}</div>
    </div>
  </section>

  <!-- PROCESSES -->
  <section id="processes">
    <div style="display:flex;flex-direction:column;gap:20px;">
      <!-- GRAPH 5: Top 10 processes horizontal bar -->
      <div class="card">
        <div class="card-header">
          <div class="card-icon" style="background:#1e2d3a;color:#60a5fa;">📊</div>
          <span class="card-title">Top 10 Processes by Memory</span>
        </div>
        <div class="chart-wrap" style="height:300px;">
          <canvas id="procChart"></canvas>
        </div>
      </div>
  </section>

  <!-- NETWORK -->
  <section id="network">
    <div class="card">
      <div class="card-header">
        <div class="card-icon" style="background:#1e2e3a;color:#38bdf8;">📡</div>
        <span class="card-title">WiFi Information</span>
      </div>
      <div style="padding:0;">
        <table class="data-table">
          <thead><tr><th style="width:40%;">Property</th><th>Value</th></tr></thead>
          <tbody>{wifi_rows}</tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- DRIVERS -->
  <section id="drivers">
    <div class="card">
      <div class="card-header">
        <div class="card-icon" style="background:#2a2a1e;color:#fbbf24;">🔧</div>
        <span class="card-title">Driver Report</span>
      </div>
      <div style="padding:0;max-height:480px;overflow-y:auto;">
        <table class="data-table">
          <thead><tr><th>Module Name</th><th>Display Name</th><th>Type</th><th>Status</th></tr></thead>
          <tbody>{driver_rows}</tbody>
        </table>
      </div>
    </div>
  </section>
  <!-- MAINTENANCE -->
  <section id="maintenance">
    <div class="grid-2">
      <div class="card">
        <div class="card-header">
          <div class="card-icon" style="background:#2a1e1e;color:#f87171;">🗑</div>
          <span class="card-title">Junk File Scan</span>
        </div>
        <div class="card-body">
          <div class="junk-grid">
            <div class="junk-tile"><div class="junk-num">{junk_files:,}</div><div class="junk-label">Junk Files</div></div>
            <div class="junk-tile"><div class="junk-num">{junk_size_mb}</div><div class="junk-label">MB on Disk</div></div>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-header">
          <div class="card-icon" style="background:#1e2a2a;color:#2dd4bf;">🔑</div>
          <span class="card-title">Windows Activation</span>
        </div>
        <div class="card-body"><div class="code-block">{activation}</div></div>
      </div>
    </div>
  </section>

</main>

<footer class="footer">Advanced System Report &middot; {report_time} &middot; {hostname}</footer>

<script>
Chart.defaults.color = '#8a95b0';
Chart.defaults.borderColor = 'rgba(255,255,255,0.07)';
Chart.defaults.font.family = "Inter,-apple-system,sans-serif";
Chart.defaults.font.size = 12;

// 1 — CPU per-core bar
(function(){{
  const labels = {cpu_labels_json};
  const data   = {cpu_data_json};
  const colors = data.map(v => v > 80 ? '#ef4444' : v > 60 ? '#f59e0b' : '#22c55e');
  new Chart(document.getElementById('cpuChart'), {{
    type: 'bar',
    data: {{ labels, datasets: [{{ label: 'CPU %', data, backgroundColor: colors, borderRadius: 4, borderSkipped: false }}] }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: c => ' ' + c.parsed.y.toFixed(1) + '%' }} }} }},
      scales: {{
        y: {{ min:0, max:100, ticks: {{ callback: v => v+'%' }}, grid: {{ color:'rgba(255,255,255,0.05)' }} }},
        x: {{ grid: {{ display:false }} }}
      }}
    }}
  }});
}})();

// 2 — RAM donut
(function(){{
  new Chart(document.getElementById('ramChart'), {{
    type: 'doughnut',
    data: {{
      labels: ['Used','Available','Cached/Other'],
      datasets: [{{ data: [{ram_used_gb},{ram_free_gb},{ram_cached_gb}], backgroundColor: ['#a78bfa','#22c55e','#3b73e0'], borderColor: '#161b27', borderWidth: 3, hoverOffset: 6 }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false, cutout: '70%',
      plugins: {{ legend: {{ display:false }}, tooltip: {{ callbacks: {{ label: c => ' ' + c.parsed.toFixed(2) + ' GB' }} }} }}
    }}
  }});
}})();

// 3 — Disk grouped bar
(function(){{
  const labels = {disk_labels_json};
  const used   = {disk_used_json};
  const free   = {disk_free_json};
  new Chart(document.getElementById('diskChart'), {{
    type: 'bar',
    data: {{
      labels,
      datasets: [
        {{ label: 'Used', data: used, backgroundColor: '#4f8ef7', borderRadius: 4, borderSkipped: false }},
        {{ label: 'Free', data: free, backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: 4, borderSkipped: false }}
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{ position:'top', labels: {{ boxWidth:12, padding:16, usePointStyle:true, pointStyle:'circle' }} }},
        tooltip: {{ callbacks: {{ label: c => ' ' + c.parsed.y.toFixed(2) + ' GB' }} }}
      }},
      scales: {{
        x: {{ grid: {{ display:false }} }},
        y: {{ ticks: {{ callback: v => v + ' GB' }}, grid: {{ color:'rgba(255,255,255,0.05)' }} }}
      }}
    }}
  }});
}})();

// 4 — Top 10 processes horizontal bar
(function(){{
  const labels = {proc_names_json};
  const data   = {proc_pcts_json};
  new Chart(document.getElementById('procChart'), {{
    type: 'bar',
    data: {{
      labels,
      datasets: [{{ label: 'Memory %', data, backgroundColor: 'rgba(79,142,247,0.7)', borderColor: '#4f8ef7', borderWidth: 1, borderRadius: 4, borderSkipped: false }}]
    }},
    options: {{
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display:false }}, tooltip: {{ callbacks: {{ label: c => ' ' + c.parsed.x.toFixed(2) + '%' }} }} }},
      scales: {{
        x: {{ min:0, ticks: {{ callback: v => v+'%' }}, grid: {{ color:'rgba(255,255,255,0.05)' }} }},
        y: {{ grid: {{ display:false }} }}
      }}
    }}
  }});
}})();

// Sticky nav scroll tracking
const tabs = document.querySelectorAll('.nav-tab');
const secs = document.querySelectorAll('section[id]');
const obs  = new IntersectionObserver(entries => {{
  entries.forEach(e => {{
    if (e.isIntersecting) tabs.forEach(t => t.classList.toggle('active', t.getAttribute('href') === '#' + e.target.id));
  }});
}}, {{ rootMargin: '-30% 0px -60% 0px' }});
secs.forEach(s => obs.observe(s));
tabs.forEach(t => t.addEventListener('click', e => {{
  e.preventDefault();
  document.querySelector(t.getAttribute('href'))?.scrollIntoView({{ behavior:'smooth' }});
}}));
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nSystem report saved to:\n{os.path.abspath(output_path)}")
    if open_report:
        webbrowser.open(f"file:///{os.path.abspath(output_path)}")

    return os.path.abspath(output_path)
