#!/bin/bash

# Deployment script for F2F Bot
# This script can be run manually on the server or called by CI/CD

set -e  # Exit on error

echo "🚀 Starting F2F Bot Deployment"

# Configuration
APP_DIR="/home/app"
BACKUP_DIR="$APP_DIR/backups"
LOG_FILE="/var/log/bot_deploy.log"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    echo "[ERROR] $1" >> "$LOG_FILE"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
    echo "[SUCCESS] $1" >> "$LOG_FILE"
}

# Navigate to app directory
cd "$APP_DIR" || error "Failed to navigate to $APP_DIR"

# Create backup
log "Creating backup..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/backup_$TIMESTAMP.tar.gz" --exclude='*.db' --exclude='__pycache__' . 2>/dev/null || true
success "Backup created: backup_$TIMESTAMP.tar.gz"

# Keep only last 5 backups
log "Cleaning old backups..."
cd "$BACKUP_DIR"
ls -t backup_*.tar.gz | tail -n +6 | xargs rm -f 2>/dev/null || true
cd "$APP_DIR"

# Pull latest changes
log "Pulling latest changes from Git..."
git fetch origin main || error "Failed to fetch from origin"
git reset --hard origin/main || error "Failed to reset to origin/main"
success "Code updated to latest version"

# Check for dependency changes
if git diff HEAD@{1} HEAD --name-only | grep -q "requirements.txt"; then
    log "Dependencies changed, installing/updating..."
    pip install -r requirements.txt --upgrade || error "Failed to install dependencies"
    success "Dependencies updated"
else
    log "No dependency changes detected"
fi

# Database migrations (if needed)
# Uncomment if you have migration scripts
# log "Running database migrations..."
# python migrate.py || error "Migration failed"

# Restart application
log "Restarting application..."

# CONFIGURE YOUR RESTART METHOD HERE:
# Choose one of the following methods and uncomment it:

# Method 1: systemd service
# sudo systemctl restart bot || error "Failed to restart bot service"
# sudo systemctl status bot --no-pager

# Method 2: PM2
# pm2 restart bot || error "Failed to restart bot with PM2"
# pm2 status

# Method 3: Manual process restart
# pkill -f "python.*bot.py" || true
# sleep 2
# nohup python bot.py > /var/log/bot.log 2>&1 &
# sleep 1
# if pgrep -f "python.*bot.py" > /dev/null; then
#     success "Bot restarted successfully"
# else
#     error "Bot failed to start"
# fi

# Method 4: Screen session
# screen -S bot -X quit || true
# sleep 2
# screen -dmS bot python bot.py
# success "Bot restarted in screen session"

# Method 5: Docker (if using containers)
# docker-compose down
# docker-compose up -d --build
# success "Docker containers restarted"

log "⚠️  RESTART METHOD NOT CONFIGURED!"
log "Please edit deploy.sh and uncomment your preferred restart method"

# Display current version
CURRENT_COMMIT=$(git rev-parse --short HEAD)
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

success "Deployment completed!"
log "Current branch: $CURRENT_BRANCH"
log "Current commit: $CURRENT_COMMIT"
log "Deployment log: $LOG_FILE"

echo ""
echo "✅ All done!"
