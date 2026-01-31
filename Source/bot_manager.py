import sys
import time
import random
import logging
import json
import os
import io
import concurrent.futures
import re
from SC_BOT import HumanLikeTrafficBot


class TableLogFormatter(logging.Formatter):
    """Format log lines as a table: TIMESTAMP | BOT | MESSAGE (fixed-width columns)."""
    def __init__(self, bot_id):
        self.bot_id = bot_id
        super().__init__()

    def format(self, record):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        msec = int((record.created % 1) * 1000)
        ts = "%s,%03d" % (ts, msec)
        ts = (ts + " " * 24)[:24]
        bot_col = ("%s" % self.bot_id).ljust(4)
        msg = record.getMessage().replace("\r\n", " ").replace("\n", " | ")
        return "%s | %s | %s" % (ts, bot_col, msg)

# Force UTF-8 encoding for Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def _theme():
    try:
        from theme import style, log_line, format_bot_line, format_ip_country, PREFIX
        return style, log_line, format_bot_line, format_ip_country, PREFIX
    except ImportError:
        return None, None, None, None, {}


def _is_proxy_related_error(err):
    """True if the error is likely due to a bad/dead proxy (retry with different proxy)."""
    s = (str(err) or "").lower()
    return any(x in s for x in (
        "err_tunnel_connection_failed",
        "err_proxy_connection_failed",
        "connection_refused",
        "connection_reset",
        "tunnel connection failed",
        "proxy",
        "net::err_",
    ))

class BotManager:
    def __init__(self):
        self.max_bots = 1  # Minimal fallback
        self.bot_instances = []
        self.session_logs = []
        
        # Get project root (same as SC_BOT.py)
        self.PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.LOGS_DIR = os.path.join(self.PROJECT_ROOT, 'Logs')
        self.CUSTOMIZE_DIR = os.path.join(self.PROJECT_ROOT, 'Customize')
        
    def read_bot_count(self):
        """Read bot count from bot_count.txt file - UNLIMITED SCALING"""
        try:
            count_file = os.path.join(self.CUSTOMIZE_DIR, "bot_count.txt")
            
            if not os.path.exists(count_file):
                print(f"[ERROR] bot_count.txt is empty. Please add a number.")
                return self.max_bots  # Use minimal fallback
            
            with open(count_file, 'r') as f:
                content = f.read().strip()
                
            if not content:
                print(f"[ERROR] bot_count.txt is empty. Please add a number.")
                return self.max_bots  # Use minimal fallback
            
            bot_count = int(content)
            
            # Validate bot count (minimum 1, no maximum - run all together)
            if bot_count < 1:
                bot_count = 1

            # No caps, no confirmation prompt - all bots start together (10k, 100k, etc.)
            ram_gb = (bot_count * 200) / 1024
            print(f"[TARGET] Bot count: {bot_count} (all start together, ~{ram_gb:.1f} GB RAM estimate)")
            return bot_count
            
        except Exception as e:
            print(f"[ERROR] Error reading bot_count.txt: {str(e)}")
            return self.max_bots  # Use minimal fallback
    
    def read_proxies(self):
        """Read proxy list from Customize/proxies.txt. If empty, auto-fetch free proxies (production-ready)."""
        proxy_list = []
        proxy_file = os.path.join(self.CUSTOMIZE_DIR, "proxies.txt")
        if os.path.exists(proxy_file):
            try:
                with open(proxy_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            proxy_list.append(line)
            except Exception as e:
                print(f"[WARNING] Could not read proxies.txt: {e}")
        if not proxy_list:
            try:
                from proxy_fetcher import fetch_and_save
                print("[GLOBE] No proxies.txt or empty – fetching free proxies...")
                n = fetch_and_save(validate=False, max_save=2000, log=print)
                if n:
                    with open(proxy_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                proxy_list.append(line)
            except Exception as e:
                print(f"[GLOBE] Auto-fetch proxies skipped: {e}")
        if proxy_list:
            print(f"[GLOBE] Loaded {len(proxy_list)} proxies (different IP/location per bot)")
        return proxy_list
    
    def setup_bot_logging(self, bot_id):
        """Setup individual logging for each bot — table-style file log, clear console."""
        bot_logs_dir = os.path.join(self.LOGS_DIR, f'bot_{bot_id}')
        os.makedirs(bot_logs_dir, exist_ok=True)
        
        log_file = os.path.join(bot_logs_dir, 'bot_activity.log')
        
        # Table header (fresh file each run so log is easy to read)
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("TIMESTAMP             | BOT  | MESSAGE\n")
                f.write("----------------------+------+--------------------------------------------------\n")
        except Exception:
            pass
        
        logger = logging.getLogger(f'bot_{bot_id}')
        logger.setLevel(logging.INFO)
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setFormatter(TableLogFormatter(bot_id))
        logger.addHandler(file_handler)
        
        if bot_id <= 50:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter('  [BOT %s]  %%(message)s' % bot_id))
            logger.addHandler(console_handler)
        
        return logger, bot_logs_dir
    
    def _run_one_bot(self, bot_id, urls, stay_duration, proxy=None):
        """Single attempt: create bot, detect IP, run, save. Returns session_log or raises."""
        bot_logger, bot_logs_dir = self.setup_bot_logging(bot_id)
        step_log_path = os.path.join(bot_logs_dir, 'steps.log')
        try:
            with open(step_log_path, 'w', encoding='utf-8') as f:
                f.write("Step\tTime\tWhat happened\n")
                f.write("-----\t------\t--------------------------------------------------\n")
        except Exception:
            step_log_path = None
        bot = HumanLikeTrafficBot(urls, headless=True, proxy=proxy, step_log_path=step_log_path)
        bot.logger = bot_logger
        try:
            bot.detect_and_log_ip_country()
            ip_file = os.path.join(bot_logs_dir, 'ip_country.txt')
            try:
                with open(ip_file, 'w', encoding='utf-8') as f:
                    f.write("IP: %s\nCountry: %s\n" % (getattr(bot, 'bot_ip', 'unknown'), getattr(bot, 'bot_country', 'unknown')))
            except Exception:
                pass
            if bot_id <= 50:
                bot_logger.info("Bot started. Visiting %s page(s). (IP/country above.)", len(urls))
            session_log = bot.run()
            session_log['bot_id'] = bot_id
            session_log['bot_logs_dir'] = bot_logs_dir
            session_log['bot_ip'] = getattr(bot, 'bot_ip', None)
            session_log['bot_country'] = getattr(bot, 'bot_country', None)
            bot_final_file = os.path.join(bot_logs_dir, 'session_final.json')
            with open(bot_final_file, 'w', encoding='utf-8') as f:
                json.dump(session_log, f, indent=2)
            if bot_id <= 50:
                bot_logger.info("[OK] Bot %s DONE", bot_id)
            return session_log
        finally:
            bot.cleanup()

    def run_single_bot(self, bot_id, urls, stay_duration, proxy=None, proxy_list=None):
        """Run one bot; on proxy-related failure retry with next proxy (up to 3 proxies)."""
        style, log_line, _, _, _ = _theme() or (lambda s, c=None: s, lambda *a: "  [LOG] " + str(a[1]), None, None, {})
        emergency_logger = logging.getLogger('emergency')
        if not emergency_logger.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter('%(message)s'))
            emergency_logger.addHandler(h)
            emergency_logger.setLevel(logging.ERROR)

        # If we have a proxy list, try up to 3 different proxies on proxy-related failure
        if proxy_list and len(proxy_list) > 0:
            max_tries = min(3, len(proxy_list))
            last_err = None
            for i in range(max_tries):
                proxy = proxy_list[(bot_id - 1 + i) % len(proxy_list)]
                try:
                    result = self._run_one_bot(bot_id, urls, stay_duration, proxy=proxy)
                    # Check for "soft" failure: visit completed but with proxy error (e.g. ERR_TUNNEL on page)
                    visits = result.get('visits') or []
                    if visits and any(
                        v.get('status') == 'error' and _is_proxy_related_error(v.get('error') or '')
                        for v in visits
                    ) and i < max_tries - 1:
                        emergency_logger.error("[BOT %s] Page failed (proxy) -> retrying with next proxy (%s/%s)", bot_id, i + 1, max_tries)
                        time.sleep(2)
                        continue
                    return result
                except Exception as e:
                    last_err = e
                    if _is_proxy_related_error(e) and i < max_tries - 1:
                        emergency_logger.error("[BOT %s] Proxy failed -> retrying with next proxy (%s/%s)", bot_id, i + 1, max_tries)
                        time.sleep(2)
                    else:
                        emergency_logger.error("[BOT %s] FAIL -> %s", bot_id, str(e)[:60])
                        return {'bot_id': bot_id, 'status': 'failed', 'error': str(last_err)}
            return {'bot_id': bot_id, 'status': 'failed', 'error': str(last_err)}

        # No proxy list: retry twice with same proxy
        last_err = None
        for attempt in range(1, 3):
            try:
                return self._run_one_bot(bot_id, urls, stay_duration, proxy=proxy)
            except Exception as e:
                last_err = e
                emergency_logger.error("[BOT %s] FAIL -> %s | retry %s/2", bot_id, str(e)[:60], attempt)
                if attempt == 1:
                    time.sleep(2)
        return {'bot_id': bot_id, 'status': 'failed', 'error': str(last_err)}
    
    def run_distributed_bots(self, urls, stay_duration):
        """Run multiple bots — 0 GUI, clear logs, IP/country per bot."""
        style, log_line, _, _, _ = _theme() or (lambda s, c=None: s, lambda *a: "  [LOG] " + str(a[1]), None, None, {})
        
        try:
            from theme import banner
            print(banner())
        except ImportError:
            pass
        
        bot_count = self.read_bot_count()
        
        print(log_line("spider", "Starting %s bots at once (no browser windows — 0 GUI)." % bot_count))
        print(log_line("web", "Each bot will visit %s page(s), %s seconds per page." % (len(urls), stay_duration)))
        print(log_line("crawl", "Logs (with IP and country per bot): %s" % self.LOGS_DIR))
        print("  " + "─" * 56)
        
        max_concurrent = bot_count
        print(log_line("ok", "All %s bots will start together." % max_concurrent))
        
        proxy_list = self.read_proxies()
        if proxy_list and len(proxy_list) < bot_count:
            print(log_line("loc", "Using %s proxies for %s bots (IP/country shown in each bot log)." % (len(proxy_list), bot_count)))
        elif proxy_list:
            print(log_line("ip", "Each bot uses a different proxy - see IP and country in Logs/bot_*/bot_activity.log"))
        if proxy_list:
            # Pre-import in main thread so worker threads see it (avoids ImportError in threads)
            try:
                from seleniumwire import webdriver as _  # noqa: F401
            except ImportError:
                print(log_line("err", "selenium-wire missing. Run: pip install --upgrade selenium-wire"))
                return []
        print("  " + "─" * 56)
        
        def run_bot_with_limits(bot_id):
            proxy = proxy_list[(bot_id - 1) % len(proxy_list)] if proxy_list else None
            return self.run_single_bot(bot_id, urls, stay_duration, proxy=proxy, proxy_list=proxy_list)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            future_to_bot = {
                executor.submit(run_bot_with_limits, bot_id): bot_id 
                for bot_id in range(1, bot_count + 1)
            }
            
            print(log_line("bot", "All %s bots are running. Each bot's IP and country are in its log file." % bot_count))
            if bot_count > 50:
                print(log_line("warn", "Only first 50 bots show live messages here; all write to Logs/bot_*/"))
            print()
            
            completed_count = 0
            successful_bots = 0
            failed_bots = 0
            
            for future in concurrent.futures.as_completed(future_to_bot):
                bot_id = future_to_bot[future]
                completed_count += 1
                try:
                    result = future.result()
                    self.session_logs.append(result)
                    if result.get('status') != 'failed':
                        successful_bots += 1
                    else:
                        failed_bots += 1
                    
                    if bot_count > 10000:
                        step = max(1000, bot_count // 100)
                        if completed_count % step == 0 or completed_count == bot_count:
                            print(log_line("ok", "Progress: %s/%s done (ok: %s, failed: %s)." % (completed_count, bot_count, successful_bots, failed_bots)))
                    elif bot_count > 50:
                        if completed_count % 10 == 0 or completed_count == bot_count:
                            print(log_line("ok", "Progress: %s/%s done (ok: %s, failed: %s)." % (completed_count, bot_count, successful_bots, failed_bots)))
                    else:
                        print(log_line("ok", "Bot %s finished. (Done: %s/%s)" % (bot_id, completed_count, bot_count)))
                except Exception as e:
                    failed_bots += 1
                    print(log_line("err", "Bot %s error: %s" % (bot_id, e)))
                    self.session_logs.append({'bot_id': bot_id, 'status': 'exception', 'error': str(e)})
        
        return self.session_logs
