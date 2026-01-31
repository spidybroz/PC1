"""
Single-file launcher: auto setup, auto config, auto download.
- Creates Customize/ and default config files if missing
- Upgrades pip and installs Python dependencies (retries once on failure)
- Pins blinker for selenium-wire, fetches free proxies if proxies.txt empty
- Runs the bot(s). Needs: Python 3.8+ and Chrome browser installed.
Usage: python run.py   OR   double-click runBot.bat
       python run.py --quick   (1 bot, 60 sec – for debugging)
"""
import os
import sys
import subprocess
import shutil

def project_root():
    return os.path.dirname(os.path.abspath(__file__))

def _pip_install(cmd, cwd, timeout=120):
    r = subprocess.run(
        [sys.executable, '-m', 'pip'] + cmd,
        cwd=cwd,
        capture_output=True,
        timeout=timeout,
        text=True,
    )
    return r

def main():
    root = project_root()
    os.chdir(root)
    if os.path.join(root, 'source') not in sys.path:
        sys.path.insert(0, os.path.join(root, 'source'))

    quick = '--quick' in sys.argv
    customize = os.path.join(root, 'Customize')
    source_dir = os.path.join(root, 'source')

    try:
        from theme import banner, style, log_line
        print(banner())
        print(style("  0 GUI — everything runs in this console (no browser windows).", "\033[96m"))
        print()
    except ImportError:
        print("=" * 60)
        print("  SpidyCrawler – one-run setup and launch (0 GUI)")
        print("=" * 60)
        print()

    print("[SETUP] Auto setup — first run may download dependencies and proxies.")
    print()

    # 1) Ensure Customize/ exists
    os.makedirs(customize, exist_ok=True)
    print("[OK] Customize folder ready")

    # 2) Create default config files if missing or empty/whitespace-only
    defaults = [
        ('urls.txt', 'https://example.com/\n'),
        ('spend_time.txt', '600\n'),
        ('bot_count.txt', '5\n'),
    ]
    def _config_empty(path):
        if not os.path.exists(path):
            return True
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return not f.read().strip()
        except Exception:
            return True

    for name, content in defaults:
        path = os.path.join(customize, name)
        if quick and name in ('bot_count.txt', 'spend_time.txt'):
            content = '1\n' if name == 'bot_count.txt' else '60\n'
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[OK] {name} set for quick test (1 bot, 60s)")
        elif _config_empty(path):
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[OK] Created {name} with default value")
    print()

    # 3) Upgrade pip (so installs work on fresh PC / user install)
    try:
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip', '--quiet'],
            cwd=root,
            capture_output=True,
            timeout=60,
        )
    except Exception:
        pass

    # 4) Install dependencies (retry once on failure)
    req = os.path.join(source_dir, 'requirements.txt')
    if os.path.exists(req):
        print("[SETUP] Installing dependencies...")
        r = _pip_install(['install', '-r', req], root)
        if r.returncode != 0:
            print("[SETUP] Retrying dependency install...")
            r = _pip_install(['install', '-r', req], root)
        if r.returncode != 0:
            print("[WARN] pip install had issues:", (r.stderr or r.stdout or "")[:200])
        else:
            print("[OK] Dependencies installed")
        # Pin blinker<1.8 so selenium-wire works (blinker 1.8+ removed _saferef)
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', 'blinker==1.7.0', '--quiet'],
            cwd=root,
            capture_output=True,
            timeout=60,
        )
        # FORCE install selenium-wire (proxies required for different IP per bot)
        print("[PROXY] Force-installing selenium-wire...")
        r2 = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--upgrade', '--force-reinstall', 'selenium-wire', '--no-deps'],
            cwd=root,
            capture_output=True,
            timeout=90,
            text=True,
        )
        if r2.returncode != 0:
            print("[PROXY] INSTALL FAILED:", (r2.stderr or r2.stdout or "")[:300])
        # Use the EXACT import the bot uses (from seleniumwire import webdriver)
        try:
            from seleniumwire import webdriver as _sw_webdriver
            print("[PROXY] OK - proxies will work")
        except ImportError as e:
            print("[PROXY] BLOCKING: selenium-wire not usable:", e)
            print("        On this PC run:  pip install blinker==1.7.0  then  pip install selenium-wire --no-deps")
            print("        Then run this script again from the SAME terminal.")
            sys.exit(1)
    print()

    # 5) Fetch free proxies if proxies.txt missing or empty
    proxies_file = os.path.join(customize, 'proxies.txt')
    need_proxies = not os.path.exists(proxies_file) or _config_empty(proxies_file)
    if need_proxies:
        try:
            from proxy_fetcher import fetch_and_save
            print("[SETUP] Fetching free proxies (first run)...")
            fetch_and_save(validate=False, max_save=2000, log=print)
        except Exception as e:
            print(f"[INFO] Proxies optional: {e}")
    print()

    # 4b) Delete old Logs folder so this run only has fresh logs (skip if files in use)
    logs_dir = os.path.join(root, 'Logs')
    if os.path.isdir(logs_dir):
        try:
            shutil.rmtree(logs_dir)
            print("[OK] Old Logs folder removed (fresh logs for this run only)")
        except OSError as e:
            if getattr(e, 'winerror', None) == 32:
                print("[OK] Logs in use — this run will overwrite log files (table format).")
            else:
                print("[WARN] Could not remove old Logs: %s" % e)
        except Exception as e:
            print("[WARN] Could not remove old Logs: %s" % e)
    print()

    # 5) Run the bot
    print("=" * 60)
    print("  Starting bot(s)")
    print("=" * 60)
    print()

    # Run SC_BOT.main() in-process so one file does everything
    import SC_BOT
    SC_BOT.main()

if __name__ == '__main__':
    main()
