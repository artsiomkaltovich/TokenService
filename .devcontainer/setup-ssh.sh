#!/usr/bin/env bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
if [ ! -f ~/.ssh/id_ed25519 ]; then
    ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
fi
echo ""
echo "=== DEVCONTAINER SSH PUBLIC KEY ==="
cat ~/.ssh/id_ed25519.pub
echo "==================================="
echo ""
