#!/bin/bash
# ============================================================
#  TopNode VPS Bot - Installer
#  Made by Shafin & topnode
# ============================================================
set -e

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; CYN='\033[0;36m'
MAG='\033[0;35m'; WHT='\033[1;37m'; NC='\033[0m'

step() { echo -e "${GRN}[+]${NC} $1"; }
warn() { echo -e "${YEL}[!]${NC} $1"; }
err()  { echo -e "${RED}[x]${NC} $1"; }

banner() {
    clear
    echo -e "${MAG}"
    cat <<'ART'
  _____ ___  ____  _   _  ___  ____  _____
 |_   _/ _ \|  _ \| \ | |/ _ \|  _ \| ____|
   | || | | | |_) |  \| | | | | | | |  _|
   | || |_| |  __/| |\  | |_| | |_| | |___
   |_| \___/|_|   |_| \_|\___/|____/|_____|
ART
    echo -e "${NC}${CYN}          >>> VPS DISCORD BOT INSTALLER <<<${NC}"
    echo -e "${YEL}               Made by Shafin & topnode${NC}\n"
}

need_root() {
    if [ "$EUID" -ne 0 ]; then
        err "Please run as root (sudo ./install.sh)"
        exit 1
    fi
}

install_base() {
    export DEBIAN_FRONTEND=noninteractive
    step "Updating system..."
    apt-get update
    apt-get upgrade -y

    step "Installing packages..."
    apt-get install -y --no-install-recommends \
        ca-certificates curl git snapd \
        python3 python3-pip python3-venv \
        lxc lxc-utils uidmap iproute2

    systemctl enable --now snapd.socket
    [ -e /snap ] || ln -sf /var/lib/snapd/snap /snap

    step "Installing LXD..."
    if ! snap list lxd >/dev/null 2>&1; then
        snap install lxd
    fi
    snap wait system seed.loaded || true
    export PATH="$PATH:/snap/bin"

    if ! lxc storage list >/dev/null 2>&1 || [ -z "$(lxc storage list --format csv 2>/dev/null)" ]; then
        step "Initializing LXD..."
        lxd init --auto
    else
        step "LXD already initialized."
    fi
}

install_python() {
    step "Creating Python virtual environment..."
    python3 -m venv /root/venv
    /root/venv/bin/python -m pip install --upgrade pip
    /root/venv/bin/python -m pip install -U discord.py python-dotenv
}

deploy_bot() {
    DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ ! -f "$DIR/bot.py" ]; then
        err "bot.py not found next to install.sh"
        exit 1
    fi
    install -m 600 "$DIR/bot.py" /root/bot.py
    /root/venv/bin/python -m py_compile /root/bot.py
    step "Bot copied to /root/bot.py (syntax OK)."
}

configure_env() {
    ENV_FILE=/root/.env
    touch "$ENV_FILE"; chmod 600 "$ENV_FILE"

    read -rsp "$(echo -e "${CYN}Discord bot token: ${NC}")" TOKEN_IN; echo
    [ -n "$TOKEN_IN" ] || { err "Token cannot be empty."; exit 1; }

    while true; do
        read -rp "$(echo -e "${CYN}Main admin Discord ID (comma-separate for many): ${NC}")" ADMIN_IN
        [[ "$ADMIN_IN" =~ ^[0-9]{15,22}(,[0-9]{15,22})*$ ]] && break
        warn "Enter numeric Discord ID(s)."
    done

    read -rp "$(echo -e "${CYN}VPS user role ID (Enter to skip): ${NC}")" ROLE_IN
    if [ -n "$ROLE_IN" ] && ! [[ "$ROLE_IN" =~ ^[0-9]{15,22}$ ]]; then
        err "Invalid role ID."; exit 1
    fi

    read -rp "$(echo -e "${CYN}Command prefix [!]: ${NC}")" PREFIX_IN
    PREFIX_IN="${PREFIX_IN:-!}"
    if [[ "$PREFIX_IN" =~ [[:space:]] ]] || [ "${#PREFIX_IN}" -gt 5 ]; then
        err "Prefix: 1-5 chars, no spaces."; exit 1
    fi

    TMP="$(mktemp)"
    grep -vE '^(DISCORD_TOKEN|MAIN_ADMIN_ID|VPS_USER_ROLE_ID|BOT_PREFIX)=' "$ENV_FILE" > "$TMP" || true
    {
        echo "DISCORD_TOKEN=$TOKEN_IN"
        echo "MAIN_ADMIN_ID=$ADMIN_IN"
        echo "VPS_USER_ROLE_ID=$ROLE_IN"
        echo "BOT_PREFIX=$PREFIX_IN"
    } >> "$TMP"
    install -m 600 "$TMP" "$ENV_FILE"
    rm -f "$TMP"
    unset TOKEN_IN
    step "Settings saved to /root/.env"
}

create_service() {
    cat > /etc/systemd/system/bot.service <<'EOF'
[Unit]
Description=TopNode VPS Discord Bot (Made by Shafin & topnode)
Wants=network-online.target
After=network-online.target snap.lxd.daemon.service

[Service]
User=root
WorkingDirectory=/root
Environment=PATH=/snap/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=PYTHONUNBUFFERED=1
Environment=BOT_NAME=TopNode
EnvironmentFile=-/root/.env
ExecStart=/root/venv/bin/python /root/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable bot
    systemctl restart bot
    sleep 3
    if systemctl is-active --quiet bot; then
        step "Bot is running!"
    else
        err "Bot failed to start. Logs:"
        journalctl -u bot -n 40 --no-pager || true
        exit 1
    fi
}

main() {
    banner
    need_root
    install_base
    install_python
    deploy_bot
    configure_env
    create_service
    echo -e "\n${GRN}Installation complete!${NC}  Logs: journalctl -u bot -f"
    echo -e "${YEL}Made by Shafin & topnode${NC}\n"
}

main "$@"
