Perfect choices! Here's the full setup:

---

## Step 1 — Create a Discord Webhook

1. Open Discord and go to the server/channel you want alerts in
2. Click the **gear icon** next to the channel name → **Edit Channel**
3. Go to **Integrations** → **Webhooks** → **New Webhook**
4. Give it a name like `Server Thermal Alert`
5. Click **Copy Webhook URL** — save it, you'll need it shortly

---

## Step 2 — Create the monitoring script

```bash
sudo nano /usr/local/bin/temp-monitor.sh
```

Paste this:

```bash
#!/bin/bash

WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK_URL_HERE"

# Thresholds (°C)
CPU_WARN=85
NVME_WARN=70
ACPI_WARN=75

# Alert cooldown file (prevents spam)
COOLDOWN_FILE="/tmp/temp_alert_cooldown"
COOLDOWN_SECONDS=300  # 5 minutes between alerts

# Check cooldown
if [ -f "$COOLDOWN_FILE" ]; then
    LAST_ALERT=$(cat "$COOLDOWN_FILE")
    NOW=$(date +%s)
    DIFF=$((NOW - LAST_ALERT))
    if [ "$DIFF" -lt "$COOLDOWN_SECONDS" ]; then
        exit 0
    fi
fi

# Read temps
CPU_TEMP=$(sensors | grep "Package id 0" | awk '{print $4}' | tr -d '+°C')
NVME_TEMP=$(sensors | grep "Composite" | head -1 | awk '{print $2}' | tr -d '+°C')
ACPI_TEMP=$(sensors | grep -A1 "acpitz" | grep "temp1" | awk '{print $2}' | tr -d '+°C')

ALERT=""

# Check thresholds
if (( $(echo "$CPU_TEMP > $CPU_WARN" | bc -l) )); then
    ALERT="${ALERT}🔥 **CPU Package** is at **${CPU_TEMP}°C** (threshold: ${CPU_WARN}°C)\n"
fi

if (( $(echo "$NVME_TEMP > $NVME_WARN" | bc -l) )); then
    ALERT="${ALERT}🔥 **NVMe SSD** is at **${NVME_TEMP}°C** (threshold: ${NVME_WARN}°C)\n"
fi

if (( $(echo "$ACPI_TEMP > $ACPI_WARN" | bc -l) )); then
    ALERT="${ALERT}🔥 **Motherboard** is at **${ACPI_TEMP}°C** (threshold: ${ACPI_WARN}°C)\n"
fi

# Send alert only if something is over threshold
if [ -n "$ALERT" ]; then
    HOSTNAME=$(hostname)
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    MESSAGE="🚨 **Thermal Alert on \`${HOSTNAME}\`** — ${TIMESTAMP}\n\n${ALERT}\n⚠️ Please check your server!"

    curl -s -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "{\"content\": \"$(echo -e "$MESSAGE")\"}"

    # Set cooldown timestamp
    date +%s > "$COOLDOWN_FILE"
fi
```

Replace `YOUR_WEBHOOK_URL_HERE` with your actual webhook URL.

---

## Step 3 — Make it executable

```bash
sudo chmod +x /usr/local/bin/temp-monitor.sh
```

---

## Step 4 — Set up a cron job to run every 2 minutes

```bash
sudo crontab -e
```

Add this line at the bottom:

```
*/2 * * * * /usr/local/bin/temp-monitor.sh
```

Save and exit.

---

## How it works

- Runs every **2 minutes** silently in the background
- Only sends a Discord message if a temp **crosses the threshold**
- Has a **5 minute cooldown** so you won't get spammed if temps stay high
- You'll get a message like:

```
🚨 Thermal Alert on `vrathi17-Crosshair-15-B12UGZ` — 2026-05-06 14:32:01

🔥 CPU Package is at 87.0°C (threshold: 85°C)

⚠️ Please check your server!
```

---

## Test it manually

```bash
sudo /usr/local/bin/temp-monitor.sh
```

Temporarily lower a threshold (e.g. change `CPU_WARN=85` to `CPU_WARN=30`) to trigger a test alert, then set it back.

Let me know if the test alert shows up in Discord!