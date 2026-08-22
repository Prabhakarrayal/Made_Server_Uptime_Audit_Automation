#!/usr/bin/env python3
"""
Server Uptime Audit - Python Edition

Purpose:
    Connect to each server, collect uptime and basic system information,
    parse the returned output locally, and append a daily audit to a local log.

Remote operations are read-only.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path

import paramiko


SERVER_FILE = Path("servers.txt")
LOG_FILE = Path("server_uptimes.log")

SSH_TIMEOUT = 3.0


def write_log(text: str = "") -> None:
    """Append text to the local audit log."""
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(text + "\n")


def first_match(pattern: str, text: str, flags: int = 0) -> str:
    """Return the first regex capture group, or an empty string."""
    match = re.search(pattern, text, flags)
    return match.group(1) if match else ""


def parse_metrics(raw_data: str) -> dict[str, str]:
    """
    Parse metrics from landscape-sysinfo output.

    The parser searches for labels instead of assuming fixed field positions.
    This is important because production servers may place multiple metrics
    on the same line or change spacing.
    """

    metrics = {
        "disk": "",
        "ram": "",
        "load": "",
        "users": "",
        "temp": "",
    }

    # Disk:
    # Usage of /: 17.8% of 442.37GB
    metrics["disk"] = first_match(
        r"Usage of /:\s*([0-9]+(?:\.[0-9]+)?)%",
        raw_data,
    )

    # RAM:
    # Memory usage: 71%
    metrics["ram"] = first_match(
        r"Memory usage:\s*([0-9]+(?:\.[0-9]+)?)%",
        raw_data,
    )

    # Load:
    # System load: 4.82
    metrics["load"] = first_match(
        r"System load:\s*([0-9]+(?:\.[0-9]+)?)",
        raw_data,
    )

    # Users:
    # Users logged in: 1
    metrics["users"] = first_match(
        r"Users logged in:\s*([0-9]+)",
        raw_data,
    )

    # Temperature:
    # Temperature: 41.0 C
    metrics["temp"] = first_match(
        r"Temperature:\s*([0-9]+(?:\.[0-9]+)?)\s*C",
        raw_data,
    )

    return metrics


def parse_uptime(raw_data: str) -> str:
    """
    Extract the actual uptime line.

    Do not assume it is the first line because some systems may prepend
    login/MOTD information.
    """
    for line in raw_data.splitlines():
        if re.search(r"\bup\s+", line):
            return line.strip()

    return ""


def get_remarks(metrics: dict[str, str], uptime_text: str) -> dict[str, str]:
    """Apply the same basic thresholds used by the Bash audit."""

    remarks = {
        "uptime": "OK" if re.search(r"\b\d+\s+days?\b", uptime_text) else "ALERT",
        "disk": "N/A",
        "ram": "N/A",
        "load": "N/A",
        "temp": "N/A",
    }

    # Disk
    if metrics["disk"].isdigit():
        disk = int(metrics["disk"])
        if disk >= 90:
            remarks["disk"] = "CRITICAL"
        elif disk >= 80:
            remarks["disk"] = "warn"
        else:
            remarks["disk"] = "good"

    # RAM
    if metrics["ram"].isdigit():
        ram = int(metrics["ram"])
        remarks["ram"] = "warn" if ram >= 80 else "good"

    # Load
    try:
        load = float(metrics["load"])
        remarks["load"] = "high" if load > 5.0 else "good"
    except ValueError:
        pass

    # Temperature
    if metrics["temp"].isdigit():
        temp = int(metrics["temp"])
        remarks["temp"] = "HOT" if temp >= 55 else "good"

    return remarks


def collect_server_data(
    name: str,
    username: str,
    ip: str,
    password: str,
) -> str:
    """
    Connect to one server and collect information.

    Landscape is preferred when available.
    If it is unavailable, standard Linux commands are used instead.

    All commands are information-gathering commands.
    """

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            hostname=ip,
            username=username,
            password=password,
            timeout=SSH_TIMEOUT,
            banner_timeout=SSH_TIMEOUT,
            auth_timeout=SSH_TIMEOUT,
        )

        # command -v is only used to detect whether Landscape exists.
        # No package is installed and no remote configuration is changed.
        command = r"""
if command -v landscape-sysinfo >/dev/null 2>&1; then
    uptime
    landscape-sysinfo
else
    uptime
    echo "__STANDARD_FALLBACK__"
    echo "System load: $(awk '{print $1}' /proc/loadavg)"
    echo "Memory usage: $(free | awk '/^Mem:/ {printf "%.0f", ($3/$2)*100}')%"
    echo "Usage of /: $(df -P / | awk 'NR==2 {print $5}')"
    echo "Users logged in: $(who | wc -l)"
    if command -v sensors >/dev/null 2>&1; then
        sensors 2>/dev/null | awk '/Package id 0:/ {print "Temperature:", $4; exit}'
    fi
fi
"""

        _, stdout, stderr = ssh.exec_command(command)
        raw_data = stdout.read().decode("utf-8", errors="replace").strip()

        # Read stderr so the channel is drained cleanly.
        stderr.read()

        return raw_data

    finally:
        ssh.close()


def main() -> None:
    if not SERVER_FILE.is_file():
        print(f"🚨 ERROR: {SERVER_FILE} not found!")
        raise SystemExit(1)

    now = dt.datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    write_log()
    write_log("========================================")
    write_log(f"Audit Run: {now}")
    write_log("========================================")

    print("Starting daily uptime audit. Please wait...")

    with SERVER_FILE.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()

            if not line:
                continue

            parts = line.split(",", 3)

            if len(parts) != 4:
                print(f"⚠️ Invalid server entry: {line}")
                continue

            name, username, ip, password = [part.strip() for part in parts]

            try:
                raw_data = collect_server_data(
                    name,
                    username,
                    ip,
                    password,
                )

                if not raw_data:
                    raise RuntimeError("No response received")

            except Exception as exc:
                write_log(
                    f"[SERVER - {name} ]: "
                    f"[ CRITICAL ] : No Response / SSH Error at {ip}"
                )
                print(
                    f"🚨 [SERVER - {name} ] is DOWN or Unreachable! "
                    f"({exc})"
                )
                continue

            uptime_text = parse_uptime(raw_data)
            metrics = parse_metrics(raw_data)
            remarks = get_remarks(metrics, uptime_text)

            # Servers without optional metrics.
            disk = metrics["disk"] or ""
            ram = metrics["ram"] or ""
            load = metrics["load"] or ""
            temp = metrics["temp"] or "VM"

            if not metrics["temp"]:
                remarks["temp"] = "no-sensor"

            write_log(f"[SERVER - {name} ]: {ip}")
            write_log(
                f"    └─ [ UPTIME: {remarks['uptime']} ] : "
                f"{uptime_text}"
            )
            write_log(
                f"    └─ [ DISK: {disk}%({remarks['disk']}) ] "
                f"[ RAM: {ram}%({remarks['ram']}) ] "
                f"[ LOAD: {load}({remarks['load']}) ] "
                f"[ TEMP: {temp}({remarks['temp']}) ]"
            )
            write_log()

            print(
                f"Audited [SERVER - {name} ] -> "
                f"Check log for dashboard."
            )

    print("----------------------------------------")
    print(f"Audit complete. Check {LOG_FILE} for details.")


if __name__ == "__main__":
    main()
