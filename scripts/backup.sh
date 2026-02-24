#!/usr/bin/env bash
# backup.sh — Titanium-Agentic session backup
# Run at SESSION END (step 2 of ritual) BEFORE any git commit.
# Creates timestamped tarball of sandbox + V36, keeps last 5.
# Storage: ~/ClaudeCode/agentic-rd-sandbox/.backups/
# Never modifies source directories. Read-only pass.

set -euo pipefail

SANDBOX="$HOME/ClaudeCode/agentic-rd-sandbox"
V36="$HOME/Projects/titanium-v36"
BACKUPS="$SANDBOX/.backups"
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
ARCHIVE="$BACKUPS/titanium-backup-$TIMESTAMP.tar.gz"
MAX_BACKUP_DIR_MB=200   # Hard cap: total .backups/ size (MB). Never balloon storage.

echo "=== Titanium Backup — $TIMESTAMP ==="

# Create backup dir if missing
mkdir -p "$BACKUPS"

# Storage guard: if .backups/ already exceeds MAX_BACKUP_DIR_MB, skip and warn
CURRENT_MB=$(du -sm "$BACKUPS" 2>/dev/null | awk '{print $1}' || echo 0)
if [ "$CURRENT_MB" -ge "$MAX_BACKUP_DIR_MB" ]; then
    echo "⚠️  SKIP: .backups/ is ${CURRENT_MB}MB (>= ${MAX_BACKUP_DIR_MB}MB limit)."
    echo "   Delete old backups manually or run: rm $BACKUPS/titanium-backup-*.tar.gz"
    exit 1
fi

# Create tarball: sandbox (excluding .backups/ and *.db) + V36
tar -czf "$ARCHIVE" \
    --exclude="$SANDBOX/.backups" \
    --exclude="$SANDBOX/*.db" \
    --exclude="$SANDBOX/__pycache__" \
    --exclude="$SANDBOX/.pytest_cache" \
    --exclude="$SANDBOX/**/__pycache__" \
    -C "$(dirname "$SANDBOX")" "$(basename "$SANDBOX")" \
    -C "$(dirname "$V36")" "$(basename "$V36")" \
    2>/dev/null || true

SIZE=$(du -sh "$ARCHIVE" 2>/dev/null | cut -f1)
echo "✅ Backup created: $ARCHIVE ($SIZE)"

# Keep last 5 backups — purge older ones
BACKUP_COUNT=$(ls "$BACKUPS"/titanium-backup-*.tar.gz 2>/dev/null | wc -l | tr -d ' ')
if [ "$BACKUP_COUNT" -gt 5 ]; then
    REMOVE_COUNT=$((BACKUP_COUNT - 5))
    ls -t "$BACKUPS"/titanium-backup-*.tar.gz | tail -n "$REMOVE_COUNT" | xargs rm -f
    echo "🗑️  Purged $REMOVE_COUNT old backup(s). Keeping last 5."
fi

echo "📦 Backups in storage: $(ls "$BACKUPS"/titanium-backup-*.tar.gz 2>/dev/null | wc -l | tr -d ' ')"
echo "=== Backup complete ==="
