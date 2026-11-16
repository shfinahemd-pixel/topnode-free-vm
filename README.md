# TopNode VPS Bot

**Made by Shafin & topnode**

Discord bot for managing LXC/LXD VPS containers: create, resize, suspend, port forwarding, and admin controls, all from Discord.

## Requirements

- Fresh Ubuntu or Debian server (root access)
- Discord bot token ([Developer Portal](https://discord.com/developers/applications)); enable **Message Content** and **Server Members** intents
- Your Discord user ID (main admin)

## Install

Put `bot.py` and `install.sh` in the same folder, then:

```bash
chmod +x install.sh
sudo ./install.sh
```

The installer sets up LXD, a Python virtualenv, saves your settings to `/root/.env`, and creates a `bot.service` systemd unit (auto-start, auto-restart).

## Managing the bot

| Action | Command |
|---|---|
| Status | `systemctl status bot` |
| Live logs | `journalctl -u bot -f` |
| Restart | `sudo systemctl restart bot` |
| Stop | `sudo systemctl stop bot` |

## Configuration (`/root/.env`)

| Variable | Description | Default |
|---|---|---|
| `DISCORD_TOKEN` | Bot token | required |
| `MAIN_ADMIN_ID` | Main admin ID(s), comma-separated | required |
| `VPS_USER_ROLE_ID` | Role given to VPS owners | none |
| `BOT_PREFIX` | Command prefix | `!` |
| `BOT_NAME` | Name shown in embeds | `TopNode` |
| `LOGO_URL` | Your thumbnail photo URL | empty (no image) |
| `BANNER_URL` | Your banner photo URL | empty (no image) |
| `DEFAULT_IMAGE` | Default LXC image | `ubuntu:24.04` |

**Adding your photo:** add `LOGO_URL=https://...` (and optionally `BANNER_URL=...`) to `/root/.env`, then `sudo systemctl restart bot`.

## Commands

**Users:** `myvps`, `manage <name>`, `vps-stats <name>`, `vps-password <name>`, `ports add|list|remove`, `ping`, `uptime`

**Admins:** `create @user <name> <cpu> <ram_mb> <disk_gb> [image]`, `delete-vps`, `resize-vps`, `suspend-vps`, `unsuspend-vps`, `list-all`, `exec`, `system-health`

**Main admins:** `admin-add`, `admin-remove`, `add-admin <id>`, `rm-admin <id>`, `admin-list`

## Notes

- The bot runs as root because it controls LXC directly. Keep the token and server secured.
- `vps.db` (SQLite) is created automatically in `/root`.
