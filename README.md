# Zorin OS Fixes

A consolidated repository for Zorin OS fixes, including wake-source suspend fixes, display resolution notes, and other desktop repair work.

## Included Fixes

- `Zorin OS Stay Asleep` wake-source service and script for persistent suspend reliability.
- Placeholder for display resolution fix documentation.
- Reference links to existing repositories:
  - https://github.com/shawnmbrooks85/Zorin-OS-Stay-Asleep
  - https://github.com/shawnmbrooks85/zorin-imsm-raid0-busybox-fix

## Contents

- `mini-disable-wakeup.service` — systemd service unit for applying wake-source settings.
- `mini-disable-wakeup.sh` — shell script disabling known wake sources and clearing RTC wake alarms.
- `commands.sh` — convenience command record for install/test operations.
- `README.md` — documentation for this consolidated fix repository.

## Purpose

This repository is intended to gather all Zorin OS desktop fixes in one place so they can be shared, documented, and versioned together.

## Next Steps

1. Add the display resolution fix files or notes.
2. Add the `zorin-imsm-raid0-busybox-fix` files if available.
3. Commit and push to a new GitHub repository such as `Zorin-OS-Fixes`.

## Install

```bash
sudo install -m 0755 mini-disable-wakeup.sh /usr/local/sbin/mini-disable-wakeup.sh
sudo install -m 0644 mini-disable-wakeup.service /etc/systemd/system/mini-disable-wakeup.service
sudo systemctl daemon-reload
sudo systemctl enable mini-disable-wakeup.service
sudo systemctl start mini-disable-wakeup.service
```

## Notes

- The current contents are copied from the existing `Zorin OS Stay Asleep` fix.
- This repo is a starting point for a broader Zorin OS fix collection.
