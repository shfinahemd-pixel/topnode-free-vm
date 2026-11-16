#!/usr/bin/env python3
# ============================================================
#  TopNode VPS Bot - LXC/LXD VPS manager for Discord
#  Made by Shafin & topnode
# ============================================================
import asyncio
import os
import re
import secrets
import sqlite3
import string
import time

import discord
from discord.ext import commands

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env")
except Exception:
    pass

# ---------------- Config ----------------
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
MAIN_ADMIN_IDS = {int(x) for x in re.findall(r"\d{15,22}", os.getenv("MAIN_ADMIN_ID", ""))}
VPS_ROLE_ID = int(os.getenv("VPS_USER_ROLE_ID", "0") or 0)
PREFIX = os.getenv("BOT_PREFIX", "!")
BOT_NAME = os.getenv("BOT_NAME", "TopNode")
CREDIT = "Made by Shafin & topnode"
DB_PATH = os.getenv("DB_PATH", "/root/vps.db")
DEFAULT_IMAGE = os.getenv("DEFAULT_IMAGE", "ubuntu:24.04")

# Put your photo link here (or set LOGO_URL / BANNER_URL in /root/.env).
# Left empty on purpose - no images are shown until you add yours.
LOGO_URL = os.getenv("LOGO_URL", "").strip()
BANNER_URL = os.getenv("BANNER_URL", "").strip()

COLOR = 0x5865F2
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,30}$")
START_TIME = time.time()

# ---------------- Database ----------------
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript(
    """
    CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, is_main INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS vps (
        name TEXT PRIMARY KEY, owner_id INTEGER NOT NULL,
        cpu INTEGER, ram_mb INTEGER, disk_gb INTEGER, image TEXT,
        suspended INTEGER DEFAULT 0, created_at INTEGER);
    CREATE TABLE IF NOT EXISTS ports (
        host_port INTEGER PRIMARY KEY, vps_name TEXT, container_port INTEGER, proto TEXT);
    """
)
for _id in MAIN_ADMIN_IDS:
    db.execute("INSERT OR IGNORE INTO admins(user_id,is_main) VALUES(?,1)", (_id,))
db.commit()


def is_main_admin(uid: int) -> bool:
    return db.execute("SELECT 1 FROM admins WHERE user_id=? AND is_main=1", (uid,)).fetchone() is not None


def is_admin(uid: int) -> bool:
    return db.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,)).fetchone() is not None


def get_vps(name: str):
    return db.execute("SELECT * FROM vps WHERE name=?", (name,)).fetchone()


def can_manage(uid: int, row) -> bool:
    return row is not None and (row["owner_id"] == uid or is_admin(uid))


# ---------------- LXC helpers ----------------
async def run(*args: str, stdin: str | None = None, timeout: int = 300):
    """Run a command (no shell). Returns (returncode, output)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(
            proc.communicate(stdin.encode() if stdin is not None else None), timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "Command timed out."
    return proc.returncode, out.decode(errors="replace").strip()


def lxc(*args: str, **kw):
    return run("lxc", *args, **kw)


# ---------------- Embeds ----------------
def make_embed(title: str, desc: str = "", color: int = COLOR) -> discord.Embed:
    e = discord.Embed(title=f"{BOT_NAME} | {title}", description=desc, color=color)
    e.set_footer(text=CREDIT)
    if LOGO_URL:
        e.set_thumbnail(url=LOGO_URL)
    if BANNER_URL:
        e.set_image(url=BANNER_URL)
    return e


def ok(title, desc=""):
    return make_embed(title, desc, 0x2ECC71)


def bad(title, desc=""):
    return make_embed(title, desc, 0xE74C3C)


def clip(text: str, n: int = 1800) -> str:
    return text if len(text) <= n else text[-n:]


# ---------------- Bot ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}help | {BOT_NAME}"))
    print(f"[{BOT_NAME}] logged in as {bot.user} | {CREDIT}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        return await ctx.send(embed=bad("Missing argument", f"Usage: `{PREFIX}{ctx.command.name} {ctx.command.signature}`"))
    if isinstance(error, (commands.BadArgument, commands.MemberNotFound)):
        return await ctx.send(embed=bad("Invalid argument", str(error)))
    if isinstance(error, commands.CheckFailure):
        return await ctx.send(embed=bad("Permission denied", "You are not allowed to use this command."))
    print("Command error:", repr(error))
    await ctx.send(embed=bad("Error", clip(str(error), 500)))


def admin_only():
    return commands.check(lambda ctx: is_admin(ctx.author.id))


def main_admin_only():
    return commands.check(lambda ctx: is_main_admin(ctx.author.id))


async def get_owned(ctx, name: str):
    row = get_vps(name.lower())
    if not can_manage(ctx.author.id, row):
        await ctx.send(embed=bad("Not found", "No such VPS, or it is not yours."))
        return None
    return row


async def deny_if_suspended(ctx, row) -> bool:
    if row["suspended"] and not is_admin(ctx.author.id):
        await ctx.send(embed=bad("Suspended", "This VPS is suspended. Contact an admin."))
        return True
    return False


# ---------------- General ----------------
@bot.command(name="help")
async def help_cmd(ctx):
    p = PREFIX
    e = make_embed("Help")
    e.add_field(name="User", value=(
        f"`{p}myvps` - your VPS list\n`{p}manage <name>` - start/stop/restart panel\n"
        f"`{p}vps-stats <name>` - live info\n`{p}vps-password <name>` - reset root password\n"
        f"`{p}ports add <name> <container_port> [tcp|udp]` - get a public port\n"
        f"`{p}ports list <name>` / `{p}ports remove <host_port>`\n`{p}ping` / `{p}uptime`"), inline=False)
    e.add_field(name="Admin", value=(
        f"`{p}create @user <name> <cpu> <ram_mb> <disk_gb> [image]`\n"
        f"`{p}delete-vps <name>` | `{p}resize-vps <name> <cpu> <ram_mb> <disk_gb>`\n"
        f"`{p}suspend-vps <name>` | `{p}unsuspend-vps <name>`\n"
        f"`{p}list-all` | `{p}exec <name> <command>` | `{p}system-health`\n"
        f"`{p}admin-add @user` | `{p}admin-remove @user` | `{p}admin-list`\n"
        f"`{p}add-admin <id>` | `{p}rm-admin <id>` (main admin)"), inline=False)
    await ctx.send(embed=e)


@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(embed=ok("Pong", f"Latency: `{round(bot.latency * 1000)} ms`"))


@bot.command(name="uptime")
async def uptime(ctx):
    s = int(time.time() - START_TIME)
    await ctx.send(embed=ok("Uptime", f"`{s // 86400}d {s % 86400 // 3600}h {s % 3600 // 60}m {s % 60}s`"))


# ---------------- VPS lifecycle ----------------
@bot.command(name="create")
@admin_only()
async def create(ctx, member: discord.Member, name: str, cpu: int, ram_mb: int, disk_gb: int, image: str = DEFAULT_IMAGE):
    name = name.lower()
    if not NAME_RE.match(name):
        return await ctx.send(embed=bad("Bad name", "Use 3-31 chars: a-z, 0-9, `-`, starting with a letter."))
    if not (1 <= cpu <= 64 and 128 <= ram_mb <= 262144 and 1 <= disk_gb <= 4096):
        return await ctx.send(embed=bad("Bad resources", "CPU 1-64, RAM 128-262144 MB, disk 1-4096 GB."))
    if not re.match(r"^[A-Za-z0-9:/._-]{3,60}$", image):
        return await ctx.send(embed=bad("Bad image", "Invalid image name."))
    if get_vps(name):
        return await ctx.send(embed=bad("Exists", f"`{name}` already exists."))

    msg = await ctx.send(embed=make_embed("Creating", f"Building `{name}` for {member.mention}..."))
    rc, out = await lxc("launch", image, name, "-c", f"limits.cpu={cpu}", "-c", f"limits.memory={ram_mb}MB",
                        "-d", f"root,size={disk_gb}GB", timeout=900)
    if rc != 0:
        return await msg.edit(embed=bad("Create failed", f"```{clip(out)}```"))

    password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    await asyncio.sleep(5)
    await lxc("exec", name, "--", "chpasswd", stdin=f"root:{password}\n")
    db.execute("INSERT INTO vps VALUES(?,?,?,?,?,?,0,?)", (name, member.id, cpu, ram_mb, disk_gb, image, int(time.time())))
    db.commit()

    if VPS_ROLE_ID and ctx.guild:
        role = ctx.guild.get_role(VPS_ROLE_ID)
        if role:
            try:
                await member.add_roles(role, reason=f"{BOT_NAME} VPS created")
            except discord.HTTPException:
                pass

    await msg.edit(embed=ok("VPS created", f"`{name}` is ready for {member.mention}.\nSpecs: **{cpu} vCPU / {ram_mb} MB / {disk_gb} GB**"))
    try:
        await member.send(embed=ok("Your VPS", f"Name: `{name}`\nRoot password: ||{password}||\nManage: `{PREFIX}manage {name}`"))
    except discord.HTTPException:
        await ctx.send(embed=bad("DM failed", "Could not DM the user. Use `vps-password` to reset it."))


@bot.command(name="delete-vps")
@admin_only()
async def delete_vps(ctx, name: str):
    row = get_vps(name.lower())
    if not row:
        return await ctx.send(embed=bad("Not found", "No such VPS."))
    rc, out = await lxc("delete", row["name"], "--force", timeout=120)
    if rc != 0:
        return await ctx.send(embed=bad("Delete failed", f"```{clip(out)}```"))
    db.execute("DELETE FROM ports WHERE vps_name=?", (row["name"],))
    db.execute("DELETE FROM vps WHERE name=?", (row["name"],))
    db.commit()
    await ctx.send(embed=ok("Deleted", f"`{row['name']}` removed."))


@bot.command(name="resize-vps")
@admin_only()
async def resize_vps(ctx, name: str, cpu: int, ram_mb: int, disk_gb: int):
    row = get_vps(name.lower())
    if not row:
        return await ctx.send(embed=bad("Not found", "No such VPS."))
    n = row["name"]
    errs = []
    for key, val in (("limits.cpu", str(cpu)), ("limits.memory", f"{ram_mb}MB")):
        rc, out = await lxc("config", "set", n, key, val)
        if rc:
            errs.append(out)
    rc, out = await lxc("config", "device", "set", n, "root", f"size={disk_gb}GB")
    if rc:
        rc, out = await lxc("config", "device", "override", n, "root", f"size={disk_gb}GB")
        if rc:
            errs.append(out)
    if errs:
        return await ctx.send(embed=bad("Resize problem", f"```{clip(chr(10).join(errs))}```"))
    db.execute("UPDATE vps SET cpu=?,ram_mb=?,disk_gb=? WHERE name=?", (cpu, ram_mb, disk_gb, n))
    db.commit()
    await ctx.send(embed=ok("Resized", f"`{n}` is now **{cpu} vCPU / {ram_mb} MB / {disk_gb} GB**"))


@bot.command(name="suspend-vps")
@admin_only()
async def suspend_vps(ctx, name: str):
    row = get_vps(name.lower())
    if not row:
        return await ctx.send(embed=bad("Not found", "No such VPS."))
    await lxc("stop", row["name"], "--force")
    db.execute("UPDATE vps SET suspended=1 WHERE name=?", (row["name"],))
    db.commit()
    await ctx.send(embed=ok("Suspended", f"`{row['name']}` stopped and locked."))


@bot.command(name="unsuspend-vps")
@admin_only()
async def unsuspend_vps(ctx, name: str):
    row = get_vps(name.lower())
    if not row:
        return await ctx.send(embed=bad("Not found", "No such VPS."))
    db.execute("UPDATE vps SET suspended=0 WHERE name=?", (row["name"],))
    db.commit()
    await lxc("start", row["name"])
    await ctx.send(embed=ok("Unsuspended", f"`{row['name']}` is running again."))


# ---------------- User VPS views ----------------
@bot.command(name="myvps")
async def myvps(ctx):
    rows = db.execute("SELECT * FROM vps WHERE owner_id=?", (ctx.author.id,)).fetchall()
    if not rows:
        return await ctx.send(embed=bad("No VPS", "You do not own any VPS."))
    lines = [f"`{r['name']}` - {r['cpu']} vCPU / {r['ram_mb']} MB / {r['disk_gb']} GB" + (" (suspended)" if r["suspended"] else "") for r in rows]
    await ctx.send(embed=make_embed("Your VPS", "\n".join(lines)))


@bot.command(name="list-all")
@admin_only()
async def list_all(ctx):
    rows = db.execute("SELECT * FROM vps ORDER BY created_at DESC LIMIT 60").fetchall()
    if not rows:
        return await ctx.send(embed=bad("Empty", "No VPS created yet."))
    lines = [f"`{r['name']}` <@{r['owner_id']}> - {r['cpu']}c/{r['ram_mb']}MB/{r['disk_gb']}GB" + (" [S]" if r["suspended"] else "") for r in rows]
    await ctx.send(embed=make_embed(f"All VPS ({len(rows)})", clip("\n".join(lines), 3900)))


class ManageView(discord.ui.View):
    def __init__(self, name: str, owner_id: int):
        super().__init__(timeout=180)
        self.name, self.owner_id = name, owner_id

    async def _act(self, inter: discord.Interaction, action: str):
        row = get_vps(self.name)
        if not can_manage(inter.user.id, row):
            return await inter.response.send_message("Not your VPS.", ephemeral=True)
        if row["suspended"] and not is_admin(inter.user.id):
            return await inter.response.send_message("VPS is suspended.", ephemeral=True)
        await inter.response.defer(ephemeral=True)
        args = {"start": ("start", self.name), "stop": ("stop", self.name, "--force"), "restart": ("restart", self.name, "--force")}[action]
        rc, out = await lxc(*args, timeout=120)
        await inter.followup.send(f"{'Done' if rc == 0 else 'Failed'}: {action} `{self.name}`\n{clip(out, 300) if rc else ''}", ephemeral=True)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success)
    async def b_start(self, inter, _):
        await self._act(inter, "start")

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger)
    async def b_stop(self, inter, _):
        await self._act(inter, "stop")

    @discord.ui.button(label="Restart", style=discord.ButtonStyle.primary)
    async def b_restart(self, inter, _):
        await self._act(inter, "restart")


@bot.command(name="manage")
async def manage(ctx, name: str):
    row = await get_owned(ctx, name)
    if not row:
        return
    if await deny_if_suspended(ctx, row):
        return
    e = make_embed(f"Manage {row['name']}", f"**{row['cpu']} vCPU / {row['ram_mb']} MB / {row['disk_gb']} GB**\nImage: `{row['image']}`")
    await ctx.send(embed=e, view=ManageView(row["name"], row["owner_id"]))


@bot.command(name="vps-stats", aliases=["vpsinfo"])
async def vps_stats(ctx, name: str):
    row = await get_owned(ctx, name)
    if not row:
        return
    rc, out = await lxc("info", row["name"])
    await ctx.send(embed=make_embed(f"{row['name']} stats", f"```{clip(out, 1800)}```"))


@bot.command(name="vps-password")
async def vps_password(ctx, name: str):
    row = await get_owned(ctx, name)
    if not row or await deny_if_suspended(ctx, row):
        return
    password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    rc, out = await lxc("exec", row["name"], "--", "chpasswd", stdin=f"root:{password}\n")
    if rc:
        return await ctx.send(embed=bad("Failed", f"```{clip(out, 500)}```\nIs the VPS running?"))
    try:
        await ctx.author.send(embed=ok("New password", f"`{row['name']}` root password: ||{password}||"))
        await ctx.send(embed=ok("Password reset", "Sent to your DMs."))
    except discord.HTTPException:
        await ctx.send(embed=bad("DM failed", "Enable DMs from server members and retry."))


@bot.command(name="exec")
@admin_only()
async def exec_cmd(ctx, name: str, *, command: str):
    row = get_vps(name.lower())
    if not row:
        return await ctx.send(embed=bad("Not found", "No such VPS."))
    rc, out = await lxc("exec", row["name"], "--", "bash", "-lc", command, timeout=60)
    await ctx.send(embed=make_embed(f"exec {row['name']} (rc={rc})", f"```{clip(out or '(no output)', 1800)}```"))


# ---------------- Port forwarding ----------------
@bot.group(name="ports", invoke_without_command=True)
async def ports(ctx):
    await ctx.send(embed=make_embed("Ports", f"`{PREFIX}ports add <name> <container_port> [tcp|udp]`\n`{PREFIX}ports list <name>`\n`{PREFIX}ports remove <host_port>`"))


@ports.command(name="add")
async def ports_add(ctx, name: str, container_port: int, proto: str = "tcp"):
    row = await get_owned(ctx, name)
    if not row or await deny_if_suspended(ctx, row):
        return
    proto = proto.lower()
    if proto not in ("tcp", "udp") or not (1 <= container_port <= 65535):
        return await ctx.send(embed=bad("Invalid", "Protocol must be tcp/udp, port 1-65535."))
    count = db.execute("SELECT COUNT(*) c FROM ports WHERE vps_name=?", (row["name"],)).fetchone()["c"]
    if count >= 5 and not is_admin(ctx.author.id):
        return await ctx.send(embed=bad("Limit", "Max 5 forwarded ports per VPS."))
    used = {r["host_port"] for r in db.execute("SELECT host_port FROM ports")}
    host_port = next((p for p in range(20000, 30000) if p not in used), None)
    if host_port is None:
        return await ctx.send(embed=bad("Full", "No free host ports."))
    rc, out = await lxc("config", "device", "add", row["name"], f"proxy-{host_port}", "proxy",
                        f"listen={proto}:0.0.0.0:{host_port}", f"connect={proto}:127.0.0.1:{container_port}")
    if rc:
        return await ctx.send(embed=bad("Failed", f"```{clip(out, 500)}```"))
    db.execute("INSERT INTO ports VALUES(?,?,?,?)", (host_port, row["name"], container_port, proto))
    db.commit()
    await ctx.send(embed=ok("Port forwarded", f"Host port **{host_port}/{proto}** -> `{row['name']}`:{container_port}"))


@ports.command(name="list")
async def ports_list(ctx, name: str):
    row = await get_owned(ctx, name)
    if not row:
        return
    rows = db.execute("SELECT * FROM ports WHERE vps_name=?", (row["name"],)).fetchall()
    text = "\n".join(f"`{r['host_port']}/{r['proto']}` -> {r['container_port']}" for r in rows) or "No forwarded ports."
    await ctx.send(embed=make_embed(f"Ports for {row['name']}", text))


@ports.command(name="remove")
async def ports_remove(ctx, host_port: int):
    pr = db.execute("SELECT * FROM ports WHERE host_port=?", (host_port,)).fetchone()
    if not pr:
        return await ctx.send(embed=bad("Not found", "No such forwarded port."))
    row = get_vps(pr["vps_name"])
    if not can_manage(ctx.author.id, row):
        return await ctx.send(embed=bad("Denied", "Not your VPS."))
    await lxc("config", "device", "remove", pr["vps_name"], f"proxy-{host_port}")
    db.execute("DELETE FROM ports WHERE host_port=?", (host_port,))
    db.commit()
    await ctx.send(embed=ok("Removed", f"Port {host_port} closed."))


# ---------------- Admin management ----------------
@bot.command(name="admin-add")
@main_admin_only()
async def admin_add(ctx, member: discord.Member):
    db.execute("INSERT OR IGNORE INTO admins(user_id,is_main) VALUES(?,0)", (member.id,))
    db.commit()
    await ctx.send(embed=ok("Admin added", member.mention))


@bot.command(name="admin-remove")
@main_admin_only()
async def admin_remove(ctx, member: discord.Member):
    if is_main_admin(member.id):
        return await ctx.send(embed=bad("Denied", "Use `rm-admin` for main admins."))
    db.execute("DELETE FROM admins WHERE user_id=?", (member.id,))
    db.commit()
    await ctx.send(embed=ok("Admin removed", member.mention))


@bot.command(name="add-admin")
@main_admin_only()
async def add_admin(ctx, user_id: int):
    db.execute("INSERT OR REPLACE INTO admins(user_id,is_main) VALUES(?,1)", (user_id,))
    db.commit()
    await ctx.send(embed=ok("Main admin added", f"`{user_id}`"))


@bot.command(name="rm-admin")
@main_admin_only()
async def rm_admin(ctx, user_id: int):
    mains = db.execute("SELECT COUNT(*) c FROM admins WHERE is_main=1").fetchone()["c"]
    if is_main_admin(user_id) and mains <= 1:
        return await ctx.send(embed=bad("Denied", "At least one main admin must remain."))
    db.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    db.commit()
    await ctx.send(embed=ok("Admin removed", f"`{user_id}`"))


@bot.command(name="admin-list")
@admin_only()
async def admin_list(ctx):
    rows = db.execute("SELECT * FROM admins").fetchall()
    mains = "\n".join(f"<@{r['user_id']}>" for r in rows if r["is_main"]) or "-"
    regs = "\n".join(f"<@{r['user_id']}>" for r in rows if not r["is_main"]) or "-"
    e = make_embed("Admins")
    e.add_field(name="Main admins", value=mains)
    e.add_field(name="Admins", value=regs)
    await ctx.send(embed=e)


@bot.command(name="system-health", aliases=["health"])
@admin_only()
async def system_health(ctx):
    _, load = await run("cat", "/proc/loadavg")
    _, mem = await run("free", "-m")
    _, disk = await run("df", "-h", "/")
    count = db.execute("SELECT COUNT(*) c FROM vps").fetchone()["c"]
    await ctx.send(embed=make_embed("System health", f"VPS: **{count}**\nLoad: `{load}`\n```{mem}\n\n{disk}```"))


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set (see /root/.env)")
    if not MAIN_ADMIN_IDS:
        print("WARNING: MAIN_ADMIN_ID not set - nobody can run admin commands.")
    bot.run(TOKEN)
