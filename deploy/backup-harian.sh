#!/bin/sh
# Cron harian, mis. `15 1 * * * /opt/sikadin/deploy/backup-harian.sh`. Simpan salinan di luar server juga (rclone/scp).
cd /opt/sikadin/backend && SIKADIN_DB=/var/lib/sikadin/sikadin.db ./.venv/bin/python -m app.admin backup --dir /var/backups/sikadin --keep 30
