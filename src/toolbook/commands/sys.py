import os
import json
import typer
from toolbook.tSys import FileOrganizer, SysInfo

app = typer.Typer()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _header(title: str) -> None:
    typer.secho(f"\n{'━' * 50}", fg=typer.colors.BRIGHT_BLACK)
    typer.secho(f"  {title}", fg=typer.colors.CYAN, bold=True)
    typer.secho(f"{'━' * 50}", fg=typer.colors.BRIGHT_BLACK)


def _row(label: str, value) -> None:
    typer.secho(f"  {label:<22}", fg=typer.colors.YELLOW, nl=False)
    typer.secho(str(value), fg=typer.colors.WHITE)


def _print_system(data: dict) -> None:
    _header("🖥️  System Information")
    _row("OS",        data["system"])
    _row("Node Name", data["node_name"])
    _row("Release",   data["release"])
    _row("Version",   data["version"])
    _row("Machine",   data["machine"])
    _row("Processor", data["processor"])


def _print_cpu(data: dict) -> None:
    _header("⚙️  CPU Information")
    _row("Physical Cores",       data["physical_cores"])
    _row("Total Cores",          data["total_cores"])
    _row("CPU Usage",            f"{data['cpu_usage_percent']}%")
    _row("Frequency (MHz)",      data["cpu_frequency_mhz"])
    _row("Max Frequency (MHz)",  data["cpu_max_frequency_mhz"])
    _row("Min Frequency (MHz)",  data["cpu_min_frequency_mhz"])

    per_core = data.get("cpu_per_core_usage", [])
    if per_core:
        typer.secho("\n  Per-Core Usage", fg=typer.colors.YELLOW)
        for i, pct in enumerate(per_core):
            bar_len = int(pct / 5)          # 20 chars = 100 %
            bar  = ("█" * bar_len).ljust(20)
            typer.secho(f"    Core {i:>2}  [{bar}] {pct:>5.1f}%", fg=typer.colors.WHITE)

    load = data.get("cpu_load_average")
    _row("Load Average (1/5/15m)", ", ".join(str(round(x, 2)) for x in load) if load else "N/A")


def _print_memory(data: dict) -> None:
    _header("🧠  Memory Information")
    _row("Total RAM",     f"{data['total_ram_gb']} GB")
    _row("Available RAM", f"{data['available_ram_gb']} GB")
    _row("Used RAM",      f"{data['used_ram_gb']} GB")
    _row("RAM Usage",     f"{data['ram_usage_percent']}%")


def _print_disk(disks: list) -> None:
    _header("💾  Disk Information")
    for idx, disk in enumerate(disks, 1):
        typer.secho(f"\n  Drive #{idx}  {disk['drive']}", fg=typer.colors.MAGENTA, bold=True)
        _row("File System",  disk["file_system"])
        _row("Total Space",  f"{disk['total_space_gb']} GB")
        _row("Used Space",   f"{disk['used_space_gb']} GB")
        _row("Free Space",   f"{disk['free_space_gb']} GB")
        _row("Usage",        f"{disk['usage_percent']}%")


def _print_battery(data: dict) -> None:
    _header("🔋  Battery Information")
    if "battery" in data:
        _row("Status", data["battery"])
    else:
        _row("Charge",       f"{data['battery_percent']}%")
        _row("Charging",     data["charging"])
        _row("Seconds Left", data["seconds_left"])


def _print_network(data: dict) -> None:
    _header("🌐  Network Information")
    _row("Hostname",   data["hostname"])
    _row("IP Address", data["ip_address"])


def _print_uptime(data: dict) -> None:
    _header("🕐  Uptime — Time Since Last Boot")
    _row("Booted At",      data["boot_time"])
    typer.secho(f"\n  {'Since last power-on:'}", fg=typer.colors.YELLOW)
    _row("  Seconds",  f"{data['uptime_seconds']:,} s")
    _row("  Minutes",  f"{data['uptime_minutes']:,} min")
    _row("  Hours",    f"{data['uptime_hours']:,} hr")
    typer.secho(f"\n  {'Total Uptime':<22}", fg=typer.colors.YELLOW, nl=False)
    typer.secho(data["uptime"], fg=typer.colors.BRIGHT_WHITE, bold=True)


# ──────────────────────────────────────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────────────────────────────────────

@app.command("info")
def sys_info(
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted view"),
):
    """
    Show complete system information (OS, CPU, memory, disk, battery, network, boot).
    """
    info = SysInfo()
    data = info.all()

    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return

    typer.secho("\n🔍 Toolbook System Info", fg=typer.colors.CYAN, bold=True)
    _print_system(data["system"])
    _print_cpu(data["cpu"])
    _print_memory(data["memory"])
    _print_disk(data["disk"])
    _print_battery(data["battery"])
    _print_network(data["network"])
    _print_uptime(data["uptime"])
    typer.secho(f"\n{'━' * 50}\n", fg=typer.colors.BRIGHT_BLACK)


@app.command("info-system")
def sys_info_system(
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show OS and machine information."""
    data = SysInfo().system()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return
    _print_system(data)
    typer.echo()


@app.command("info-cpu")
def sys_info_cpu(
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show CPU core count and current usage."""
    data = SysInfo().cpu()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return
    _print_cpu(data)
    typer.echo()


@app.command("info-memory")
def sys_info_memory(
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show RAM total, available, used, and usage percentage."""
    data = SysInfo().memory()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return
    _print_memory(data)
    typer.echo()


@app.command("info-disk")
def sys_info_disk(
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show disk partitions with space usage details."""
    data = SysInfo().disk()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return
    _print_disk(data)
    typer.echo()


@app.command("info-battery")
def sys_info_battery(
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show battery charge and charging status."""
    data = SysInfo().battery()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return
    _print_battery(data)
    typer.echo()


@app.command("info-network")
def sys_info_network(
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show hostname and primary IP address."""
    data = SysInfo().network()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return
    _print_network(data)
    typer.echo()


@app.command("info-uptime")
def sys_info_uptime(
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show boot time, uptime in seconds, and human-readable uptime."""
    data = SysInfo().uptime()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return
    _print_uptime(data)
    typer.echo()


# ──────────────────────────────────────────────────────────────────────────────
# Existing commands
# ──────────────────────────────────────────────────────────────────────────────

@app.command("organize-files")
def organize_files(
    folder_path: str = typer.Argument(..., help="Path to the folder you want to organise"),
):
    """
    Organise files in FOLDER_PATH into typed sub-folders
    (Images, Videos, Documents, PDFs, Music, Archives, Others).
    """
    abs_path = os.path.abspath(folder_path)
    typer.secho(f"\n📂 Target Directory: {abs_path}", fg=typer.colors.CYAN, bold=True)

    confirmed = typer.confirm("Organise files in this folder?")
    if not confirmed:
        typer.secho("❌ Cancelled.", fg=typer.colors.YELLOW)
        raise typer.Exit()

    FileOrganizer(abs_path)
