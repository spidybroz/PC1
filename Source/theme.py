"""
Hacker Spiderman theme: 0 GUI, clear logs, spider-web style.
ANSI colors: green/cyan (hacker) + red accent (Spiderman). Plain English for normal users.
"""
import sys

# ANSI colors (work in Windows 10+ with VT enabled, and Unix)
R = "\033[91m"   # red
G = "\033[92m"   # green
C = "\033[96m"   # cyan
Y = "\033[93m"   # yellow
B = "\033[94m"   # blue
M = "\033[95m"   # magenta
W = "\033[97m"   # white
D = "\033[90m"   # dim
RESET = "\033[0m"

def no_color():
    """Disable colors if not a TTY (e.g. log file)."""
    return not (hasattr(sys.stdout, 'isatty') and sys.stdout.isatty())

def style(msg, color=G):
    if no_color():
        return msg
    return f"{color}{msg}{RESET}"

def banner():
    """Hacker Spiderman ASCII banner - 0 GUI, console only. ASCII-safe for Windows."""
    return style("""
  +===========================================================+
  |  SPIDY CRAWLER  -  friendly neighborhood traffic           |
  |  0 GUI  |  console only  |  each bot logs IP + country     |
  |  === WEB === CRAWL === LOG ===                             |
  +===========================================================+
""", C)

# Plain-English log prefixes (understandable to anyone)
PREFIX = {
    "web": "[WEB]",
    "spider": "[SPIDER]",
    "bot": "[BOT]",
    "crawl": "[CRAWL]",
    "ok": "[OK]",
    "warn": "[!]",
    "err": "[X]",
    "ip": "[IP]",
    "loc": "[LOCATION]",
}

def log_line(prefix_key, message, color=None):
    """One clear line for logs. prefix_key = web, spider, bot, crawl, ok, warn, err, ip, loc."""
    p = PREFIX.get(prefix_key, "[LOG]")
    line = f"  {p} {message}"
    if color and not no_color():
        return f"{color}{line}{RESET}"
    return line

def format_bot_line(bot_id, message, level="info"):
    """Bot log line: [BOT 3] Clear message."""
    pre = f"[BOT {bot_id}]"
    if level == "warn":
        return log_line("warn", f"{pre} {message}", Y)
    if level == "error":
        return log_line("err", f"{pre} {message}", R)
    return log_line("bot", f"{pre} {message}", G)

def format_ip_country(ip, country):
    """Line for IP and country display."""
    return log_line("ip", f"IP: {ip}  |  Country: {country}", C)
