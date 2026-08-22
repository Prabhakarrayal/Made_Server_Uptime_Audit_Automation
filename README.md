# Made Server Uptime Audit Automation 

## 📌 Project Overview 

This project automates the daily server uptime audit that was originally being performed manually through SSH.

The objective is simple: 

> Connect from a central Ubuntu/root machine to each server, collect uptime and a few basic system-health indicators, disconnect, and record the results locally.

The automation is intentionally **read-only on the remote servers**. It does not modify server configuration, install packages, restart services, create remote files, or change system state.

---

# 📖 The Story Behind the Project

When I joined the team, one of my regular operational tasks was to check the uptime of the assigned servers every day.

The original workflow was completely manual:

```text
SSH → Server 1
uptime
check basic information
exit

SSH → Server 2
uptime
check basic information
exit

SSH → Server 3
uptime
check basic information
exit

...
```

With around 15 servers, this became repetitive and time-consuming. More importantly, it was easy to lose track of which server had already been checked or accidentally miss a server.

After spending roughly a month performing this task manually, I realized that I was already familiar with Bash and Python and started thinking:

> "Why am I repeating the same SSH and information-gathering steps every day when the process is predictable enough to automate?"

I first looked at what information was actually required and how it was available on the Ubuntu servers.

The basic requirement was uptime, but during the manual check I was also expected to glance at basic indicators such as:

- Disk usage
- Memory usage
- System load
- Logged-in users
- Temperature, when available

For detailed monitoring and historical visualization, the environment already has Grafana and other monitoring mechanisms. Therefore, this project was not intended to replace a monitoring platform. It was designed specifically to automate the **daily operational audit**.

That led to this project.

---

# 🎯 Goals

The automation was designed with the following goals:

1. Eliminate repetitive manual SSH sessions.
2. Check every server consistently.
3. Collect uptime from every server.
4. Collect basic system information where available.
5. Record the results in a readable daily log.
6. Continue checking other servers if one server is unreachable.
7. Keep all operations on remote servers read-only.
8. Make the parser tolerant of differences between server output formats.

---

# 🏗️ Architecture

```text
                    Central Ubuntu Machine
                         /opt/uptime
                              │
                              │
                     vincentio_servers.txt
                              │
                              ▼
                     uptime_audit.py
                              │
                ┌─────────────┼─────────────┐
                │             │             │
                ▼             ▼             ▼
             Server 1      Server 2      Server 3
                │             │             │
             SSH +         SSH +         SSH +
             commands      commands      commands
                │             │             │
                └─────────────┼─────────────┘
                              │
                              ▼
                     Output returned to
                     the central machine
                              │
                              ▼
                    Local parsing / logic
                              │
                              ▼
                    server_uptimes.log
```

Every SSH connection originates from the central machine.

The script does **not** SSH from Server 1 into Server 2.

---

# 🔐 Remote Server Safety

The remote collection is intentionally read-only.

The main information-gathering commands are:

```bash
uptime
landscape-sysinfo
```

When Landscape is unavailable, the Python implementation can use standard Linux commands instead.

The script does not perform operations such as:

```text
rm
mv
cp
chmod
chown
systemctl
service
reboot
shutdown
apt
yum
dnf
```

No remote output is redirected into a remote file.

The collected output is returned through SSH and processed on the central machine.

The log file is local:

```text
server_uptimes.log
```

---

# 📋 Server Inventory Format

The server inventory is stored in:

```text
vincentio_servers.txt
```

Format:

```text
name,username,ip,password
```

Example:

```text
BHEEMAIAH1,ubuntu,10.121.220.21,<password>
BHEEMAIAH2,ubuntu,10.121.220.22,<password>
```

> **Security note:** The example above uses `<password>` intentionally. Real passwords should never be committed to a public GitHub repository.

For production use, SSH keys or a proper secrets-management solution are preferable to plaintext passwords.

---

# ⚙️ Prerequisites

Before running the automation, confirm the following with the system administrator/senior responsible for the servers.

## Central Ubuntu machine

Required:

- Bash
- Python 3
- SSH client
- `sshpass` if password-based SSH is being used
- Python `paramiko` for the Python implementation

Example:

```bash
python3 --version
ssh -V
sshpass -V
```

Python dependency:

```bash
pip install paramiko
```

## Remote servers

The remote servers should provide:

```bash
uptime
```

For the optional Landscape-based metrics:

```bash
landscape-sysinfo
```

Before relying on `landscape-sysinfo`, verify its availability on the organization's servers:

```bash
command -v landscape-sysinfo
```

or:

```bash
landscape-sysinfo
```

### Important operational note

Do not install Landscape or any other package on production servers just for this project without approval.

If `landscape-sysinfo` is not installed, confirm with the senior whether the standard-command fallback should be used.

---

# 🧩 Why `landscape-sysinfo`?

`landscape-sysinfo` is associated with Canonical's Landscape management tooling and is commonly found in Ubuntu environments that use Landscape.

It conveniently presents several basic system indicators in one human-readable output:

```text
System load
Swap usage
Users logged in
Usage of /
Temperature
Memory usage
Processes
```

Example:

```text
System load:  4.82                Swap usage:  0%       Users logged in: 1
Usage of /:   17.8% of 442.37GB   Temperature: 40.0 C
Memory usage: 71%                 Processes:   1215
```

This made it convenient for the daily audit because one command provides several basic indicators.

However, `landscape-sysinfo` should **not** be considered a universal Linux requirement.

Some servers may not have it, and some systems may expose different information.

That is why the Python implementation includes a fallback approach.

---

# 🔄 Landscape Alternative

There is no single universal Linux command that exactly replaces `landscape-sysinfo`.

However, the same underlying information can be obtained using standard Linux commands:

| Information | Standard Linux source |
|---|---|
| Uptime | `uptime` |
| Load | `/proc/loadavg` |
| Memory | `free` |
| Disk | `df -h /` |
| Logged-in users | `who` |
| Temperature | `sensors` when available |
| Processes | `ps` |

Therefore, the fallback can collect:

```bash
uptime
free
df -h /
cat /proc/loadavg
who
```

Temperature is treated as optional because hardware temperature sensors are not guaranteed to exist, especially on virtual machines.

---

# 🧠 Parsing Challenge

One of the most useful lessons from this project was that **parsing command output by fixed field numbers is fragile**.

Initially, the parser assumed a format similar to:

```text
Memory usage: 71%
Users logged in: 1
Temperature: 40.0 C
```

and used fixed `awk` positions.

However, the production servers actually returned:

```text
System load:  4.82                Swap usage:  0%       Users logged in: 1
Usage of /:   17.8% of 442.37GB   Temperature: 40.0 C
Memory usage: 71%                 Processes:   1215
```

Multiple metrics appeared on the same line.

This caused incorrect extraction.

For example, an early parser used:

```bash
awk '{print $2}'
```

for temperature.

On the actual line:

```text
Usage of /: 17.8% of 442.37GB Temperature: 40.0 C
```

field 2 was:

```text
of
```

Therefore the log incorrectly showed:

```text
TEMP: of
```

Similarly, a fixed field position for users returned:

```text
Swap
```

instead of:

```text
1
```

which caused:

```text
integer expression expected
```

---

# ✅ Better Parsing Strategy

The improved parser does not depend unnecessarily on absolute field positions.

Instead, it searches for semantic labels.

For example:

### Temperature

Find:

```text
Temperature:
```

Then take the value immediately after it.

```text
Temperature: 40.0 C
             ↑
             value
```

### Users

Find:

```text
Users logged in:
```

Then use the final field:

```text
Users logged in: 1
                ↑
                value
```

### Disk

Find the percentage associated with:

```text
Usage of /
```

### Memory

Find the percentage associated with:

```text
Memory usage:
```

This approach is more resilient to spacing changes and additional fields.

---

# 🧪 Why This Matters

Command output is designed primarily for humans, not as a stable API.

For example, the following two outputs communicate the same information:

```text
Memory usage: 71%
```

and:

```text
Memory usage: 71%    Processes: 1215
```

A parser based purely on `$3` may work for one format and fail for another.

A parser based on recognizable labels is generally safer.

---

# 🖥️ Servers Without Landscape

Some servers in the environment do not provide the same Landscape information.

For example, a management server may return only the standard Ubuntu login information followed by:

```bash
uptime
```

In that situation, the automation should not treat missing optional metrics as a server failure.

The expected behavior is:

```text
UPTIME → available
DISK   → N/A
RAM    → N/A
LOAD   → N/A
TEMP   → N/A
```

This is important because:

> Missing monitoring metadata does not necessarily mean that the server is down.

---

# 📊 Log Format

The output is intentionally human-readable because the primary requirement is a daily operational record.

Example:

```text
========================================
Audit Run: 19-08-2026 16:05:03
========================================

[SERVER - BHEEMAIAH1 ]: 10.121.220.21
    └─ [ UPTIME: OK ] : 10:35:05 up 178 days, 17:31, 2 users, load average: 4.54, 6.31, 6.27
    └─ [ DISK: 18%(good) ] [ RAM: 71%(good) ] [ LOAD: 4.54(good) ] [ TEMP: 41(good) ]
```

The log is appended using:

```bash
>>
```

Therefore:

- Existing history is preserved.
- A missing log file is automatically created.
- Each audit receives a timestamp.

---

# 🚦 Threshold Logic

The current basic thresholds are intentionally simple.

### Disk

```text
< 80%   → good
80-89%  → warn
≥ 90%   → critical
```

### RAM

```text
< 80%   → good
≥ 80%   → warn
```

### Load

```text
≤ 5.0   → good
> 5.0   → high
```

### Temperature

```text
< 55°C  → good
≥ 55°C  → HOT
```

### Uptime

The current audit flags uptime that does not contain a day count.

For example:

```text
up 178 days → OK
```

while:

```text
up 20:01 → ALERT
```

This does not automatically mean that the server is unhealthy. It means the server has a relatively recent uptime and should be reviewed.

The thresholds are operational conventions for this audit and should be adjusted according to the organization's requirements.

---

# 🛠️ Challenges Faced

## Challenge 1 — Manual repetition

Checking 15 servers manually required repeated:

```text
SSH
uptime
exit
```

### Solution

Automated the workflow with Bash/Python.

---

## Challenge 2 — Different `landscape-sysinfo` output formats

The initial parser assumed fixed field positions.

### Solution

Changed the extraction strategy to search for meaningful labels and extract values relative to those labels.

---

## Challenge 3 — Servers without Landscape information

Some management servers did not expose the same metrics.

### Solution

Treat optional metrics as `N/A` and keep the uptime check operational.

---

## Challenge 4 — Invalid numeric comparisons

The original parser sometimes extracted:

```text
Swap
```

or:

```text
of
```

and Bash attempted to compare those strings with integers.

This produced:

```text
integer expression expected
```

### Solution

- Corrected the extraction logic.
- Added numeric validation before performing numeric comparisons.

---

## Challenge 5 — Keeping the remote operation safe

The automation needed to replace manual checking without changing the server state.

### Solution

Keep the remote command set limited to information-gathering commands:

```bash
uptime
landscape-sysinfo
```

or standard read-only alternatives.

All parsing and log writing happen on the central machine.

---

# 🔐 Security Considerations

The current implementation supports password-based SSH because that matches the original operational environment.

However, storing passwords in:

```text
vincentio_servers.txt
```

is not ideal for a public repository.

### Never commit:

```text
real_passwords
private_keys
production IP inventories
```

to GitHub.

Use:

- `.gitignore`
- environment variables
- SSH keys
- secret managers
- organization-approved credential storage

for production deployments.

A safe repository can contain an example file such as:

```text
vincentio_servers.example.txt
```

with placeholder credentials.

---

# 🚀 Running the Bash Version

From the project directory:

```bash
cd /opt/uptime
```

Run:

```bash
./uptime_audit.sh
```

If executable permission is missing:

```bash
bash uptime_audit.sh
```

The local log will be:

```text
/opt/uptime/server_uptimes.log
```

when executed from `/opt/uptime`.

---

# 🐍 Running the Python Version

Install Paramiko:

```bash
python3 -m pip install paramiko
```

Then:

```bash
python3 uptime_audit.py
```

The Python implementation follows the same operational workflow as the Bash version.

---

# 🆚 Bash vs Python

Both implementations can accomplish the same task.

### Bash

Advantages:

- Already available on Linux.
- Excellent for simple system administration tasks.
- Uses native SSH and command-line tools.
- Small and straightforward.

### Python

Advantages:

- Better structured parsing.
- Easier exception handling.
- Easier to extend.
- Paramiko provides programmatic SSH.
- Easier to add CSV/JSON/reporting functionality later.

For this project, Bash is a natural fit because the original task itself is a Linux administration workflow. Python provides a cleaner foundation if the project grows.

---

# 🔄 Current Workflow

```text
1. Read server inventory
2. Read one server's credentials
3. Open SSH connection
4. Run uptime
5. Run Landscape or standard fallback commands
6. Capture output locally
7. Parse the returned text
8. Apply basic thresholds
9. Append results to local log
10. Close SSH connection
11. Continue with next server
```

---

# 📁 Suggested Repository Structure

```text
server-uptime-audit/
│
├── README.md
├── uptime_audit.sh
├── uptime_audit.py
├── vincentio_servers.example.txt
├── .gitignore
│
└── logs/
    └── .gitkeep
```

The real:

```text
vincentio_servers.txt
server_uptimes.log
```

should remain outside a public repository when they contain production credentials or sensitive infrastructure information.

---

# 🔮 Future Improvements

The project is intentionally kept simple because the original requirement is a daily uptime audit.

Possible future improvements include:

- SSH key authentication
- Parallel SSH connections
- CSV/JSON reporting
- HTML reports
- Email notifications
- Integration with existing monitoring systems
- Historical uptime analysis
- Automatic reboot detection
- Centralized credential management
- Better handling of OS-specific command differences

These are future possibilities, not requirements of the current implementation.

---

# 📌 Key Takeaways

This project taught me several practical infrastructure concepts:

1. Automating repetitive Linux administration tasks.
2. Working with SSH programmatically.
3. Reading structured inventory data.
4. Processing Linux command output.
5. Understanding the limitations of human-readable CLI output.
6. Writing robust parsers instead of relying blindly on fixed field positions.
7. Handling unavailable metrics gracefully.
8. Separating remote data collection from local processing.
9. Designing automation that remains read-only on production systems.
10. Turning a repetitive operational task into a repeatable process.

---

# 👨‍💻 Project Motivation

This project started from a very practical problem rather than being created as a theoretical exercise.

I had been performing the same server uptime check manually for approximately a month. Since I was already familiar with Bash and Python, I decided to investigate whether the process could be automated without changing the operational behavior.

The result was a small automation tool that follows the same workflow I was already performing manually:

```text
SSH → collect information → exit → next server
```

The difference is that the repetitive work is now performed consistently by the script, while the final report remains available for the daily operational record.

---

# ⚠️ Disclaimer

This project is intended as an internal/educational automation pattern.
And the server Credentals used in this project here are only for understanding practice. 
Before deploying it against production infrastructure:

- Confirm the required commands with the responsible senior/administrator.
- Confirm that automated SSH access is permitted.
- Follow the organization's credential and security policies.
- Do not install additional packages on production servers without approval.
- Test the automation on an approved server before wider deployment.

## 👤 Author & Maintainer

**Prabhakar Rayal**

B.Tech CSE | Graphic Era Hill University  
📍 Rishikesh, Uttarakhand, India  

[GitHub Profile](https://github.com/Prabhakarrayal), 

[LinkedIn Profile](https://in.linkedin.com/in/prabhakar-rayal-6639682), 

[Naukari Profile](https://www.naukri.com/mnjuser/profile?id=&altresid)

## ⭐ Support

If this project helped you learn about AWS or Bash, please Star ⭐ this repository!
