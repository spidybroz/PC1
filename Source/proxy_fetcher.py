"""
Production-ready free proxy fetcher.
Fetches from public free proxy lists, normalizes to http://ip:port, optionally validates, writes to Customize/proxies.txt.
Run standalone: python source/proxy_fetcher.py
Or bots will auto-fetch when proxies.txt is empty (if enabled).
"""
import os
import re
import sys
import time
import urllib.request
import urllib.error
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUSTOMIZE_DIR = os.path.join(PROJECT_ROOT, 'Customize')
PROXIES_FILE = os.path.join(CUSTOMIZE_DIR, 'proxies.txt')

# Free public proxy list URLs (no auth, no signup) – production sources
FREE_PROXY_SOURCES = [
    'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
    'https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt',
]

REQUEST_TIMEOUT = 15
VALIDATE_TIMEOUT = 5
MAX_PROXIES_TO_SAVE = 2000
MAX_VALIDATE_WORKERS = 50


def normalize_proxy(line):
    """Return http://ip:port or None if invalid."""
    line = (line or '').strip()
    if not line or line.startswith('#'):
        return None
    # Strip scheme if present
    for p in ('http://', 'https://', 'socks4://', 'socks5://'):
        if line.lower().startswith(p):
            line = line[len(p):].strip()
            break
    # ip:port
    if ':' in line and '@' not in line:
        parts = line.rsplit(':', 1)
        if len(parts) == 2 and parts[1].isdigit() and 1 <= int(parts[1]) <= 65535:
            return f"http://{parts[0].strip()}:{parts[1].strip()}"
    return None


def fetch_url(url):
    """Fetch text from URL with timeout and retries. Returns list of lines or empty."""
    for attempt in range(2):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={'User-Agent': 'SpidyCrawler/1.0'})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as r:
                text = r.read().decode('utf-8', errors='ignore')
                return [normalize_proxy(line) for line in text.splitlines()]
        except (urllib.error.URLError, OSError, Exception) as e:
            if attempt == 0:
                time.sleep(1)
            continue
    return []


def validate_proxy(proxy_url):
    """Quick check: try to connect through proxy. Returns True if likely working."""
    if not proxy_url or not proxy_url.startswith('http://'):
        return False
    try:
        import socket
        # Parse host and port
        part = proxy_url.replace('http://', '').strip()
        if '@' in part:
            part = part.split('@', 1)[1]
        host, _, port = part.partition(':')
        port = int(port) if port.isdigit() else 80
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(VALIDATE_TIMEOUT)
        sock.connect((host, port))
        sock.close()
        return True
    except Exception:
        return False


def fetch_all_sources():
    """Fetch from all sources, dedupe, return list of http://ip:port (no auth)."""
    seen = set()
    result = []
    for url in FREE_PROXY_SOURCES:
        lines = fetch_url(url)
        for p in lines:
            if p and p not in seen:
                seen.add(p)
                result.append(p)
        time.sleep(0.5)
    return result


def fetch_and_save(validate=True, max_save=MAX_PROXIES_TO_SAVE, log=print):
    """
    Fetch free proxies, optionally validate, save to Customize/proxies.txt.
    Returns number of proxies written.
    """
    os.makedirs(CUSTOMIZE_DIR, exist_ok=True)
    log("[PROXY] Fetching free proxy lists...")
    raw = fetch_all_sources()
    log(f"[PROXY] Fetched {len(raw)} raw proxies from free sources.")
    if not raw:
        log("[PROXY] No proxies fetched. Check network or try again later.")
        return 0

    if validate:
        log("[PROXY] Validating proxies (quick connect check)...")
        working = []
        with ThreadPoolExecutor(max_workers=MAX_VALIDATE_WORKERS) as ex:
            futures = {ex.submit(validate_proxy, p): p for p in raw[:500]}
            for f in as_completed(futures):
                if f.result():
                    working.append(futures[f])
        log(f"[PROXY] {len(working)} proxies passed validation.")
        to_save = working[:max_save]
    else:
        to_save = raw[:max_save]

    if not to_save:
        to_save = raw[:max_save]

    with open(PROXIES_FILE, 'w', encoding='utf-8') as f:
        f.write("# Auto-generated free proxies. One per line.\n")
        for p in to_save:
            f.write(p + "\n")
    log(f"[PROXY] Saved {len(to_save)} proxies to {PROXIES_FILE}")
    return len(to_save)


def main():
    import argparse
    p = argparse.ArgumentParser(description='Fetch free proxies into Customize/proxies.txt')
    p.add_argument('--no-validate', action='store_true', help='Skip validation (faster, more proxies, some may be dead)')
    p.add_argument('--max', type=int, default=MAX_PROXIES_TO_SAVE, help=f'Max proxies to save (default {MAX_PROXIES_TO_SAVE})')
    args = p.parse_args()
    n = fetch_and_save(validate=not args.no_validate, max_save=args.max)
    sys.exit(0 if n else 1)


if __name__ == '__main__':
    main()
