#!/usr/bin/env bash
set -euo pipefail

# Auto-update script for bud on Raspberry Pi.
# Checks if the remote main branch has new commits and pulls + reinstalls if so.

REPO_DIR="${BUD_REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
BRANCH="${BUD_BRANCH:-main}"
POST_UPDATE_CMD="${BUD_POST_UPDATE_CMD:-uv sync}"

cd "$REPO_DIR"

git fetch origin "$BRANCH" 2>/dev/null

LOCAL=$(git rev-parse "$BRANCH" 2>/dev/null || echo "none")
REMOTE=$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "none")

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "$(date -Iseconds) up-to-date ($BRANCH @ ${LOCAL:0:8})"
    exit 0
fi

echo "$(date -Iseconds) updating $BRANCH: ${LOCAL:0:8} -> ${REMOTE:0:8}"
git checkout "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH" "origin/$BRANCH"
git pull origin "$BRANCH"

if [ -n "$POST_UPDATE_CMD" ]; then
    echo "$(date -Iseconds) running post-update: $POST_UPDATE_CMD"
    eval "$POST_UPDATE_CMD"
fi

echo "$(date -Iseconds) update complete ($BRANCH @ $(git rev-parse --short HEAD))"
