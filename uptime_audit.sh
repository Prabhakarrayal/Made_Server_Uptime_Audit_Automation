#!/bin/bash
# ==============================================================================
# Script Name: uptime_audit.sh
# Purpose: Master Dashboard - Uptime, Disk, RAM, Load, Users, and Temp
# ==============================================================================

# 1. VARIABLES
SERVER_FILE="servers.txt"
LOG_FILE="server_uptimes.log"

if [[ ! -f "$SERVER_FILE" ]]; then
    echo "🚨 ERROR: $SERVER_FILE not found!"
    exit 1
fi

# 2. LOG HEADER
echo "" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
echo "Audit Run: $(date '+%d-%m-%Y %H:%M:%S')" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

echo "Starting daily uptime audit. Please wait..."

# 3. THE MASTER LOOP
while IFS=, read -r name username ip password; do

    [[ -z "$name" ]] && continue

    # Grab all data in one trip
    RAW_DATA=$(sshpass -p "$password" ssh -n \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout=3 \
        "$username@$ip" \
        "uptime; landscape-sysinfo 2>/dev/null" 2>/dev/null)

    if [[ -z "$RAW_DATA" ]]; then
        echo "[SERVER - $name ]: [ CRITICAL ] : No Response (Timeout) at $ip" >> "$LOG_FILE"
        echo "🚨 [SERVER - $name ] is DOWN or Unreachable!"
        continue
    fi

    # ==========================================================================
    # EXTRACTION PHASE
    # ==========================================================================

    # Uptime
    UPTIME_TEXT=$(echo "$RAW_DATA" | grep -m1 -E '[0-9]+:[0-9]+:[0-9]+ up ')

    # Disk usage
    VAL_DISK=$(echo "$RAW_DATA" | awk '
        /Usage of \// {
            for (i=1; i<=NF; i++) {
                if ($i ~ /^[0-9]+(\.[0-9]+)?%$/) {
                    print $i
                    exit
                }
            }
        }
    ' | cut -d% -f1 | cut -d. -f1)

    # RAM usage
    VAL_RAM=$(echo "$RAW_DATA" | awk '
        /Memory usage:/ {
            for (i=1; i<=NF; i++) {
                if ($i ~ /^[0-9]+(\.[0-9]+)?%$/) {
                    print $i
                    exit
                }
            }
        }
    ' | cut -d% -f1 | cut -d. -f1)

    # System load
    VAL_LOAD=$(echo "$RAW_DATA" | awk '
        /System load:/ {
            print $3
            exit
        }
    ')

    # Users logged in
    VAL_USERS=$(echo "$RAW_DATA" | awk '
        /Users logged in:/ {
            print $NF
            exit
        }
    ')

    # Temperature
    VAL_TEMP=$(echo "$RAW_DATA" | awk '
        /Temperature:/ {
            for (i=1; i<=NF; i++) {
                if ($i == "Temperature:") {
                    print $(i+1)
                    exit
                }
            }
        }
    ' | cut -d. -f1)

    # ==========================================================================
    # REMARK LOGIC PHASE
    # ==========================================================================

    # Uptime Logic
    if [[ "$UPTIME_TEXT" == *" day"* || "$UPTIME_TEXT" == *" days"* ]]; then
        RMK_UP="OK"
    else
        RMK_UP="ALERT"
    fi

    # Disk Logic
    RMK_DISK="N/A"

    if [[ "$VAL_DISK" =~ ^[0-9]+$ ]]; then
        if [ "$VAL_DISK" -ge 90 ]; then
            RMK_DISK="CRITICAL"
        elif [ "$VAL_DISK" -ge 80 ]; then
            RMK_DISK="warn"
        else
            RMK_DISK="good"
        fi
    fi

    # RAM Logic
    RMK_RAM="N/A"

    if [[ "$VAL_RAM" =~ ^[0-9]+$ ]]; then
        if [ "$VAL_RAM" -ge 80 ]; then
            RMK_RAM="warn"
        else
            RMK_RAM="good"
        fi
    fi

    # Users Logic
    RMK_USERS="N/A"

    if [[ "$VAL_USERS" =~ ^[0-9]+$ ]]; then
        if [ "$VAL_USERS" -gt 1 ]; then
            RMK_USERS="alert"
        else
            RMK_USERS="good"
        fi
    fi

    # Temperature Logic
    RMK_TEMP="N/A"

    if [[ "$VAL_TEMP" =~ ^[0-9]+$ ]]; then
        if [ "$VAL_TEMP" -ge 55 ]; then
            RMK_TEMP="HOT"
        else
            RMK_TEMP="good"
        fi
    else
        VAL_TEMP="VM"
        RMK_TEMP="no-sensor"
    fi

    # Load Logic
    RMK_LOAD="N/A"

    if [[ "$VAL_LOAD" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        RMK_LOAD=$(echo "$VAL_LOAD" | awk '{
            if ($1 > 5.0)
                print "high"
            else
                print "good"
        }')
    fi

    # ==========================================================================
    # DASHBOARD ASSEMBLY
    # ==========================================================================

    echo "[SERVER - $name ]: $ip" >> "$LOG_FILE"

    echo "    └─ [ UPTIME: $RMK_UP ] : $UPTIME_TEXT" >> "$LOG_FILE"

    echo "    └─ [ DISK: ${VAL_DISK}%(${RMK_DISK}) ] [ RAM: ${VAL_RAM}%(${RMK_RAM}) ] [ LOAD: ${VAL_LOAD}(${RMK_LOAD}) ] [ TEMP: ${VAL_TEMP}(${RMK_TEMP}) ]" >> "$LOG_FILE"

    echo "" >> "$LOG_FILE"

    echo "Audited [SERVER - $name ] -> Check log for dashboard."

done < "$SERVER_FILE"

echo "----------------------------------------"
echo "Audit complete. Check server_uptimes.log for details."
