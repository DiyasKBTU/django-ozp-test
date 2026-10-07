#!/bin/bash
# Деректер қоры мен жүктелген суреттердің күнделікті резервтік көшірмесі.
# Соңғы 14 күннің көшірмелері сақталады, ескілері өшіріледі.
#
# Орнату (root атынан):
#   sudo cp deploy/backup.sh /usr/local/bin/ozp-backup.sh
#   sudo chmod +x /usr/local/bin/ozp-backup.sh
#   sudo crontab -e   →   30 3 * * * /usr/local/bin/ozp-backup.sh
# Қалпына келтіру: DEPLOY.md, «Бэкаптан қалпына келтіру».

set -euo pipefail

DB_NAME="ozp_test"
PROJECT_DIR="/srv/ozp-test"
BACKUP_DIR="/var/backups/ozp-test"
KEEP_DAYS=14

DATE=$(date +%Y-%m-%d)
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# 1. Деректер қоры (postgres пайдаланушысы атынан, құпия сөз керек емес)
sudo -u postgres pg_dump --no-owner "$DB_NAME" | gzip > "$BACKUP_DIR/db-$DATE.sql.gz"

# 2. Сұрақтар мен контексттердің суреттері
if [ -d "$PROJECT_DIR/media" ]; then
    tar -czf "$BACKUP_DIR/media-$DATE.tar.gz" -C "$PROJECT_DIR" media
fi

# 3. 14 күннен ескі көшірмелерді өшіру
find "$BACKUP_DIR" -name "*.gz" -mtime +$KEEP_DAYS -delete

echo "$(date '+%F %T') бэкап дайын: $BACKUP_DIR/db-$DATE.sql.gz"
