import sys
import time
import re
import random
import logging
from datetime import datetime
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import json
import os
import io
from fake_useragent import UserAgent
from urllib.parse import urlparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(PROJECT_ROOT, 'Logs')
CUSTOMIZE_DIR = os.path.join(PROJECT_ROOT, 'Customize')

class HumanLikeTrafficBot:
    def __init__(self, urls, headless=False, proxy=None, step_log_path=None):
        self.urls = urls
        self.headless = headless
        self.proxy = proxy  # e.g. http://user:pass@host:port or socks5://host:port (different IP/location per bot)
        self.driver = None
        self.current_user_agent = None
        self.bot_ip = None
        self.bot_country = None
        self.stay_duration = self.read_stay_duration()
        self.step_log_path = step_log_path
        self._step_counter = 0

        # Create logs directory if it doesn't exist
        os.makedirs(LOGS_DIR, exist_ok=True)

        self.setup_logging()
        self.setup_driver()

    def _step_log(self, what_happened):
        """Append one step line: Step N | Time | What happened (user-friendly summary log)."""
        if not self.step_log_path:
            return
        self._step_counter += 1
        ts = time.strftime("%H:%M:%S", time.localtime())
        line = "%s\t%s\t%s\n" % (self._step_counter, ts, what_happened)
        try:
            with open(self.step_log_path, 'a', encoding='utf-8') as f:
                f.write(line)
        except Exception:
            pass
        
    def read_stay_duration(self):
        """Read stay duration from spend_time.txt file and validate it"""
        try:
            duration_file = os.path.join(CUSTOMIZE_DIR, "spend_time.txt")  # Changed to CUSTOMIZE_DIR
            
            if not os.path.exists(duration_file):
                raise FileNotFoundError(f"{duration_file} not found. Please create the file with time in seconds.")
            
            with open(duration_file, 'r') as f:
                content = f.read().strip()
                
            if not content:
                raise ValueError("spend_time.txt is empty. Please add time in seconds.")
            
            # Extract numeric value (handle cases like "600 seconds" or just "600")
            import re
            numbers = re.findall(r'\d+', content)
            if not numbers:
                raise ValueError("No valid number found in spend_time.txt")
            
            duration_seconds = int(numbers[0])
            
            # Validate duration range (1 minute to 24 hours)
            min_duration = 60  # 1 minute
            max_duration = 86400  # 24 hours
            
            if duration_seconds < min_duration:
                raise ValueError(f"Duration too short. Minimum is {min_duration} seconds (1 minute)")
            if duration_seconds > max_duration:
                raise ValueError(f"Duration too long. Maximum is {max_duration} seconds (24 hours)")
            
            # Convert to minutes and hours for logging
            minutes = duration_seconds // 60
            hours = minutes // 60
            remaining_minutes = minutes % 60
            
            if hours > 0:
                duration_display = f"{hours}h {remaining_minutes}m"
            else:
                duration_display = f"{minutes}m"
                
            print(f"Loaded stay duration: {duration_seconds} seconds ({duration_display})")
            
            return duration_seconds
            
        except FileNotFoundError as e:
            print(f"ERROR: {str(e)}")
            raise
        except ValueError as e:
            print(f"ERROR: Invalid duration in spend_time.txt: {str(e)}")
            raise
        except Exception as e:
            print(f"ERROR: Error reading spend_time.txt: {str(e)}")
            raise
    
    def normalize_url(self, url):
        """Normalize URL to ensure consistent format"""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Parse URL to handle www vs non-www properly
        parsed = urlparse(url)
        
        # Reconstruct URL with proper scheme and netloc
        normalized_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            normalized_url += f"?{parsed.query}"
        if parsed.fragment:
            normalized_url += f"#{parsed.fragment}"
            
        return normalized_url
    
    def setup_driver_for_exact_url(self, target_url):
        """Configure driver to handle redirects and maintain exact URL"""
        try:
            # Disable automatic redirect following
            self.driver.execute_cdp_cmd('Network.setRequestInterception', {
                'patterns': [{'urlPattern': '*', 'resourceType': 'Document', 'interceptionStage': 'HeadersReceived'}]
            })
        except:
            # If CDP command fails, we'll handle it differently
            pass
        
        # Set up custom request handler to monitor redirects
        self.target_url = self.normalize_url(target_url)
        self.original_url_visited = False
        
    def handle_redirects(self, current_url):
        """Handle redirects and try to maintain the exact requested URL"""
        current_normalized = self.normalize_url(current_url)
        target_normalized = self.normalize_url(self.target_url)
        
        self.logger.info(f"Current URL: {current_normalized}")
        self.logger.info(f"Target URL: {target_normalized}")
        
        # If we're not on the exact URL, try to navigate back
        if current_normalized != target_normalized:
            self.logger.warning(f"URL redirected from {target_normalized} to {current_normalized}")
            
            try:
                # Try to go back to original URL
                self.logger.info("Attempting to return to original URL...")
                self.driver.get(self.target_url)
                
                # Wait and check again
                time.sleep(2)
                new_current = self.driver.current_url
                new_normalized = self.normalize_url(new_current)
                
                if new_normalized == target_normalized:
                    self.logger.info("Successfully returned to original URL")
                else:
                    self.logger.warning(f"Still on redirected URL: {new_normalized}")
                    
            except Exception as e:
                self.logger.error(f"Failed to return to original URL: {str(e)}")
    
    def calculate_action_plan(self, total_duration):
        """Calculate intelligent time distribution for actions"""
        # Convert to minutes for easier calculation
        total_minutes = total_duration / 60
        
        if total_duration <= 300:  # 5 minutes or less
            # Short visit: Quick actions
            plan = {
                'initial_load_delay': (5, 15),
                'scroll_sessions': random.randint(1, 2),
                'click_sessions': random.randint(1, 2),  # Ensure clicking happens
                'mouse_movement_sessions': random.randint(1, 2),
                'break_duration_range': (10, 30),  # seconds
                'action_delay_range': (1, 3)  # seconds
            }
        elif total_duration <= 1800:  # 30 minutes or less
            # Medium visit: Balanced actions
            plan = {
                'initial_load_delay': (5, 20),
                'scroll_sessions': random.randint(2, 4),
                'click_sessions': random.randint(2, 4),  # More clicking
                'mouse_movement_sessions': random.randint(2, 4),
                'break_duration_range': (20, 60),  # seconds
                'action_delay_range': (2, 5)  # seconds
            }
        else:  # Longer visits
            # Extended visit: More varied actions with longer breaks
            plan = {
                'initial_load_delay': (10, 30),
                'scroll_sessions': random.randint(3, 6),
                'click_sessions': random.randint(3, 6),  # Even more clicking
                'mouse_movement_sessions': random.randint(3, 6),
                'break_duration_range': (30, 120),  # seconds
                'action_delay_range': (3, 8)  # seconds
            }
        
        self.logger.info(f"Action plan calculated: {plan}")
        return plan
    
    def setup_logging(self):
        """Setup comprehensive logging — table-style file, real-time console."""
        log_file = os.path.join(LOGS_DIR, 'SC_BOT.log')
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("TIMESTAMP             | LEVEL   | MESSAGE\n")
                f.write("----------------------+---------+--------------------------------------------------\n")
        except Exception:
            pass
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)-22s | %(levelname)-7s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(log_file, mode='a', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def setup_driver(self):
        """Setup Chrome driver with human-like configurations; optional proxy for different IP/location."""
        try:
            from selenium.webdriver.chrome.options import Options

            if self.proxy:
                self._step_log("Selenium-wire starting, proxy: %s" % (self.proxy.strip().split('@')[-1] if '@' in self.proxy else self.proxy.strip()))
            else:
                self._step_log("Browser starting (no proxy)")

            options = Options()
            
            # Random user agent
            ua = UserAgent()
            self.current_user_agent = ua.random
            options.add_argument(f'--user-agent={self.current_user_agent}')
            
            # Common browser arguments + suppress Chrome stderr noise (GPU/USB etc)
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--log-level=3')
            options.add_argument('--disable-logging')
            
            options.add_argument('--disable-features=NetworkService')
            
            if self.headless:
                options.add_argument('--headless=new')  # New headless mode (harder to detect)
                options.add_argument('--disable-gpu')
                options.add_argument('--disable-software-rasterizer')
                options.add_argument('--no-first-run')
                options.add_argument('--no-default-browser-check')
                options.add_argument('--disable-background-timer-throttling')
                options.add_argument('--disable-backgrounding-occluded-windows')
                options.add_argument('--disable-renderer-backgrounding')
                options.add_argument('--disable-extensions')
                options.add_argument('--disable-plugins')
                options.add_argument('--disable-images')  # Save bandwidth
                # Realistic viewport (sites check dimensions) – avoid "headless" viewport
                resolutions = ['1920,1080', '1366,768', '1536,864', '1440,900', '1280,720']
                options.add_argument('--window-size=%s' % random.choice(resolutions))
            else:
                # Window size variations only for visible mode
                resolutions = ['1920,1080', '1366,768', '1536,864', '1440,900']
                options.add_argument(f'--window-size={random.choice(resolutions)}')
            
            # PROXY: require selenium-wire (use main-thread-loaded module to avoid thread import issues)
            if self.proxy:
                proxy_url = self.proxy.strip()
                if not proxy_url.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
                    proxy_url = 'http://' + proxy_url
                try:
                    import sys as _sys
                    _m = _sys.modules.get('seleniumwire')
                    if _m is None:
                        import importlib
                        _m = importlib.import_module('seleniumwire')
                    wire_webdriver = getattr(_m, 'webdriver')
                except (ImportError, AttributeError) as e:
                    self.logger.error("[PROXY] BLOCKING: selenium-wire not installed. Run: pip install selenium-wire")
                    raise RuntimeError("Proxy required but selenium-wire missing. pip install selenium-wire") from e
                last_err = None
                for attempt in range(1, 4):
                    try:
                        seleniumwire_options = {
                            'proxy': {
                                'http': proxy_url,
                                'https': proxy_url,
                                'no_proxy': 'localhost,127.0.0.1'
                            },
                            'connection_timeout': 25,
                            'verify_ssl': False
                        }
                        self.driver = wire_webdriver.Chrome(options=options, seleniumwire_options=seleniumwire_options)
                        ok_msg = proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url
                        self.logger.info("[PROXY] OK -> %s", ok_msg)
                        self._step_log("Proxy OK -> %s" % ok_msg)
                        break
                    except Exception as e:
                        last_err = e
                        self.logger.warning("[PROXY] FAIL attempt %s/3 -> %s", attempt, str(e)[:80])
                        if attempt < 3:
                            time.sleep(2 * attempt)
                else:
                    self.logger.error("[PROXY] DEAD after 3 attempts")
                    raise last_err
            else:
                self.driver = webdriver.Chrome(options=options)
            # Anti-detection: CDP + JS so bots are less likely to be blocked
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": self.current_user_agent,
                "acceptLanguage": "en-US,en;q=0.9"
            })
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            # Mask automation signals (reduce chance of security/anti-bot blocking)
            try:
                self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                    'source': """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });
                    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'], configurable: true });
                    if (!window.chrome) window.chrome = { runtime: {} };
                    """
                })
            except Exception:
                pass

            self.logger.info("Browser ready. Stay time per page: %s seconds (no GUI, console only).", self.stay_duration)
            self._step_log("Browser ready. Stay time per page: %s s (no GUI)." % self.stay_duration)
            
        except Exception as e:
            self.logger.error("Browser setup failed: %s", str(e))
            raise
    
    def detect_and_log_ip_country(self):
        """Detect this bot's public IP and country (through proxy if any). Log to bot file for user."""
        if not self.driver:
            return
        try:
            self.driver.get("https://ipinfo.io/json")
            time.sleep(1.5)
            body = self.driver.find_element(By.TAG_NAME, "body").text
            data = json.loads(body)
            self.bot_ip = data.get("ip", "unknown")
            self.bot_country = data.get("country", data.get("region", "unknown"))
            try:
                from theme import format_ip_country
                line = format_ip_country(self.bot_ip, self.bot_country)
            except ImportError:
                line = "IP: %s  |  Country: %s" % (self.bot_ip, self.bot_country)
            self.logger.info("=== This bot is using: IP %s | Country: %s ===", self.bot_ip, self.bot_country)
            self.logger.info("(Your site analytics will show this IP and country as a visitor)")
            self._step_log("IP/country: %s | %s" % (self.bot_ip, self.bot_country))
        except Exception as e:
            self.bot_ip = "unknown"
            self.bot_country = "unknown"
            self.logger.warning("Could not detect IP/country: %s", str(e))
            err_short = str(e).split('\n')[0][:60]
            self._step_log("Could not detect IP/country: %s" % err_short)
    
    def human_delay(self, min_seconds=2, max_seconds=8):
        """Random delay to mimic human thinking time"""
        delay = random.uniform(min_seconds, max_seconds)
        self.logger.debug(f"Human delay: {delay:.2f}s")
        time.sleep(delay)
    
    def random_mouse_movements(self):
        """Simulate random mouse movements"""
        try:
            self.logger.info("Moving mouse around the page (like a real user)")
            
            # Reduced movements in headless mode to save CPU
            movement_count = random.randint(2, 5) if self.headless else random.randint(3, 8)
            
            actions = ActionChains(self.driver)
            
            # Move to random positions on the page
            for i in range(movement_count):
                x_offset = random.randint(100, 500)
                y_offset = random.randint(100, 500)
                actions.move_by_offset(x_offset, y_offset)
                actions.perform()
                self.logger.debug(f"Mouse movement {i+1}: x={x_offset}, y={y_offset}")
                time.sleep(random.uniform(0.5, 2))
                
            # Return to original position
            actions.move_by_offset(-x_offset, -y_offset)
            actions.perform()
            
            self.logger.info("Done moving mouse.")
            
        except Exception as e:
            self.logger.debug("Mouse movement interrupted: %s", str(e))
    
    def scroll_behavior(self):
        """Simulate natural scrolling behavior"""
        try:
            self.logger.info("Scrolling the page up and down")
            scroll_actions = [
                (0, random.randint(300, 800)),  # Initial scroll
                (random.randint(-200, 200), random.randint(200, 500)),  # Random scroll
                (0, random.randint(-400, -200)),  # Scroll back up a bit
                (0, random.randint(400, 1200))   # Final scroll
            ]
            
            for i, (x_scroll, y_scroll) in enumerate(scroll_actions):
                self.driver.execute_script(f"window.scrollBy({x_scroll}, {y_scroll})")
                self.logger.debug(f"Scroll {i+1}: x={x_scroll}, y={y_scroll}")
                self.human_delay(1, 3)
                
            self.logger.info("Done scrolling.")
                
        except Exception as e:
            self.logger.debug("Scrolling interrupted: %s", str(e))
    
    def click_random_elements(self):
        """Click on random interactive elements"""
        try:
            self.logger.info("Looking for links and buttons to click...")
            
            # Find all clickable elements
            clickable_selectors = [
                'a', 'button', 'input[type="button"]', 'input[type="submit"]',
                '[onclick]', '[role="button"]'
            ]
            
            all_elements = []
            for selector in clickable_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                all_elements.extend(elements)
                self.logger.debug(f"Found {len(elements)} elements with selector: {selector}")
            
            # Filter visible and clickable elements
            clickable_elements = [
                elem for elem in all_elements 
                if elem.is_displayed() and elem.is_enabled()
            ]
            
            self.logger.info("Found %s links or buttons.", len(clickable_elements))
            
            if clickable_elements:
                click_count = random.randint(1, min(3, len(clickable_elements)))
                self.logger.info("Clicking %s of them (like a real visitor).", click_count)
                
                for i in range(click_count):
                    element = random.choice(clickable_elements)
                    try:
                        clickable_elements.remove(element)
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                        self.human_delay(1, 3)
                        element_text = (element.text[:50] + "...") if len(element.text) > 50 else element.text
                        self.logger.info("Clicked: %s", element_text or "(link/button)")
                        element.click()
                        self.human_delay(2, 5)
                    except Exception as e:
                        self.logger.warning("Could not click one element (page may have changed).")
                        continue
            else:
                self.logger.info("No links or buttons found on this page.")
                        
        except Exception as e:
            self.logger.error("Clicking failed: %s", str(e))
    
    def detect_verification(self):
        """Detect common verification challenges"""
        verification_indicators = {
            'captcha': [
                'iframe[src*="captcha"]',
                'div[class*="captcha"]',
                'img[alt*="CAPTCHA"]',
                'input[name*="captcha"]'
            ],
            'cloudflare': [
                'div[id="cf-content"]',
                'div[class*="challenge"]'
            ],
            'honeypot': [
                'input[style*="display: none"]',
                'input[name*="honeypot"]'
            ]
        }
        
        detected_challenges = {}
        
        for challenge_type, selectors in verification_indicators.items():
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        detected_challenges[challenge_type] = True
                        self.logger.warning(f"Detected {challenge_type} challenge")
                        break
                except Exception:
                    continue
        
        return detected_challenges
    
    def handle_verification(self, challenges):
        """Handle detected verification challenges"""
        if challenges:
            self.logger.error("Verification challenges detected. Manual intervention may be required.")
            
            # Log detailed information about the challenge
            challenge_info = {
                'timestamp': datetime.now().isoformat(),
                'url': self.driver.current_url,
                'challenges': list(challenges.keys()),
                'user_agent': self.current_user_agent,
                'page_title': self.driver.title
            }
            
            # Save challenge details to file in logs folder
            challenge_file = os.path.join(LOGS_DIR, 'verification_challenges.log')  # Uses LOGS_DIR
            with open(challenge_file, 'a') as f:
                f.write(json.dumps(challenge_info) + '\n')
            
            return False
        return True
    
    def visit_url(self, url):
        """Visit a single URL and simulate human behavior using calculated duration"""
        visit_log = {
            'url': url,
            'start_time': datetime.now().isoformat(),
            'user_agent': self.current_user_agent,
            'scheduled_duration': self.stay_duration,
            'verification_detected': False,
            'actions_performed': [],
            'status': 'success'
        }
        
        try:
            # Normalize the target URL
            target_url = self.normalize_url(url)
            self.logger.info("Opening page: %s", target_url)
            self.logger.info("Will stay on this page for %s seconds.", self.stay_duration)
            self._step_log("Opening page: %s" % target_url)

            # Navigate to the exact URL
            self.driver.get(target_url)
            
            # Wait for page to load
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Check if we were redirected
            current_url = self.driver.current_url
            current_normalized = self.normalize_url(current_url)
            target_normalized = self.normalize_url(target_url)
            
            if current_normalized != target_normalized:
                self.logger.warning("Page redirected to a different address. Trying original URL again.")
                visit_log['redirected_to'] = current_normalized
                self._step_log("Request to %s -> 307 (redirect)" % target_url)
                
                # Try to go back to original URL
                try:
                    self.logger.info("Going back to the original page...")
                    self.driver.get(target_url)
                    time.sleep(3)  # Wait for navigation
                    
                    # Check again
                    new_current = self.driver.current_url
                    new_normalized = self.normalize_url(new_current)
                    
                    if new_normalized == target_normalized:
                        self.logger.info("Back on the original page.")
                        visit_log['redirect_fixed'] = True
                    else:
                        self.logger.warning("Still on a different page after redirect.")
                        visit_log['redirect_fixed'] = False
                except Exception as e:
                    self.logger.error(f"Failed to return to original URL: {str(e)}")
                    visit_log['redirect_fixed'] = False
            else:
                self.logger.info("Page loaded correctly.")
                visit_log['redirect_fixed'] = True
                self._step_log("Page loaded correctly.")

            action_plan = self.calculate_action_plan(self.stay_duration)
            initial_delay = random.uniform(*action_plan['initial_load_delay'])
            self.logger.info("Waiting a few seconds (like a real user), then browsing...")
            time.sleep(initial_delay)
            visit_log['actions_performed'].append({
                'action': 'initial_load_delay',
                'duration': initial_delay,
                'timestamp': datetime.now().isoformat()
            })
            
            start_time = time.time()
            action_count = 0
            session_count = 0
            
            while time.time() - start_time < self.stay_duration:
                session_count += 1
                remaining_time = self.stay_duration - (time.time() - start_time)
                self.logger.info("Browsing round %s — about %s seconds left on this page.", session_count, int(remaining_time))
                
                # Detect verification challenges
                challenges = self.detect_verification()
                if challenges and not self.handle_verification(challenges):
                    visit_log['verification_detected'] = True
                    visit_log['status'] = 'verification_failed'
                    break
                
                # Perform action sessions based on the plan
                sessions = []
                
                # Add scroll sessions
                for i in range(action_plan['scroll_sessions']):
                    sessions.append((f'scrolling_{i+1}', self.scroll_behavior))
                
                # Add click sessions - ENSURED THIS HAPPENS
                for i in range(action_plan['click_sessions']):
                    sessions.append((f'clicking_{i+1}', self.click_random_elements))
                
                # Add mouse movement sessions
                for i in range(action_plan['mouse_movement_sessions']):
                    sessions.append((f'mouse_movements_{i+1}', self.random_mouse_movements))
                
                # Shuffle sessions for more natural behavior
                random.shuffle(sessions)
                self.logger.info("Doing %s actions this round (scroll, click, move mouse).", len(sessions))
                
                # Execute sessions
                for session_name, session_function in sessions:
                    if time.time() - start_time >= self.stay_duration:
                        self.logger.info("Time’s up on this page. Moving on.")
                        break
                        
                    self.logger.info("Action: %s", session_name.replace('_', ' '))
                    session_function()
                    action_count += 1
                    
                    visit_log['actions_performed'].append({
                        'action': session_name,
                        'session_number': session_count,
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    # Short delay between actions in same session
                    action_delay = random.uniform(*action_plan['action_delay_range'])
                    if time.time() - start_time + action_delay < self.stay_duration:
                        self.logger.debug(f"Action delay: {action_delay:.2f}s")
                        time.sleep(action_delay)
                    else:
                        self.logger.info("Short on time — skipping short pause.")
                
                # Break between sessions
                remaining_time = self.stay_duration - (time.time() - start_time)
                if remaining_time > 10:  # Only break if significant time remains
                    break_duration = min(
                        random.uniform(*action_plan['break_duration_range']),
                        remaining_time * 0.8  # Don't use all remaining time for break
                    )
                    self.logger.info("Short pause (like a real user), then continuing.")
                    time.sleep(break_duration)
                else:
                    self.logger.info("No pause — almost done.")
            
            # Ensure exact time is spent
            remaining_time = self.stay_duration - (time.time() - start_time)
            if remaining_time > 0:
                self.logger.info("Finishing up (staying full time on page).")
                time.sleep(remaining_time)
                visit_log['actual_duration'] = self.stay_duration
            else:
                visit_log['actual_duration'] = time.time() - start_time
            
            visit_log['end_time'] = datetime.now().isoformat()
            visit_log['total_actions'] = action_count
            visit_log['total_sessions'] = session_count
            
            self.logger.info("Done with this page. Time spent: %s sec, actions done: %s.", int(visit_log.get('actual_duration', 0)), action_count)
            
        except Exception as e:
            visit_log['status'] = 'error'
            visit_log['error'] = str(e)
            self.logger.error("Something went wrong on this page: %s", str(e))
            err_short = str(e).split('\n')[0][:60]
            self._step_log("Something went wrong on this page: %s" % err_short)

        return visit_log
    
    def run(self):
        """Run the bot for all URLs using the duration from file"""
        session_log = {
            'session_start': datetime.now().isoformat(),
            'total_urls': len(self.urls),
            'scheduled_duration_per_url': self.stay_duration,
            'user_agent': self.current_user_agent,
            'visits': []
        }
        
        self.logger.info("Starting. Will visit %s page(s), %s seconds per page.", len(self.urls), self.stay_duration)
        self._step_log("Bot started. Visiting %s page(s), %s s per page." % (len(self.urls), self.stay_duration))

        for i, url in enumerate(self.urls, 1):
            self.logger.info("Page %s of %s.", i, len(self.urls))
            
            if i > 1:
                between_visit_delay = random.uniform(60, 300)
                self.logger.info("Waiting a bit before next page (like a real user).")
                time.sleep(between_visit_delay)
            
            visit_log = self.visit_url(url)
            session_log['visits'].append(visit_log)
            
            # Save progress after each visit in logs folder
            progress_file = os.path.join(LOGS_DIR, 'session_progress.json')  # Uses LOGS_DIR
            with open(progress_file, 'w') as f:
                json.dump(session_log, f, indent=2)
        
        session_log['session_end'] = datetime.now().isoformat()
        return session_log
    
    def cleanup(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()
            self.logger.info("Browser closed. Bot finished.")
            self._step_log("Bot DONE, browser closed.")

def main():
    """Main function to run the bot(s)"""
    
    # Read URLs from urls.txt file
    urls_file = os.path.join(CUSTOMIZE_DIR, "urls.txt")
    try:
        with open(urls_file, 'r') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        if not urls:
            print(f"ERROR: No URLs found in {urls_file}")
            return
            
        print(f"Loaded {len(urls)} URLs from {urls_file}")
        
    except FileNotFoundError:
        print(f"ERROR: URLs file not found: {urls_file}")
        return
    except Exception as e:
        print(f"ERROR: Error reading {urls_file}: {str(e)}")
        return
    
    # Read stay duration
    try:
        duration_file = os.path.join(CUSTOMIZE_DIR, "spend_time.txt")
        with open(duration_file, 'r') as f:
            content = f.read().strip()
        stay_duration = int(re.findall(r'\d+', content)[0])
    except:
        stay_duration = 600  # Default 10 minutes
    
    # Check if multi-bot mode is requested
    bot_count_file = os.path.join(CUSTOMIZE_DIR, "bot_count.txt")
    bot_count_file_no_ext = os.path.join(CUSTOMIZE_DIR, "bot_count")

    if os.path.exists(bot_count_file) or os.path.exists(bot_count_file_no_ext):
        # Multi-bot mode - Import and use BotManager
        try:
            from bot_manager import BotManager
            
            # Use the file that exists
            actual_bot_count_file = bot_count_file if os.path.exists(bot_count_file) else bot_count_file_no_ext
            # Line 680 - Remove Unicode arrow and use ASCII
            print(f"[TARGET] Multi-bot mode detected! Using: {actual_bot_count_file}")
            
            bot_manager = BotManager()
            all_session_logs = bot_manager.run_distributed_bots(urls, stay_duration)
            
            # Generate master summary
            successful_bots = [log for log in all_session_logs if log.get('status') != 'failed' and log.get('status') != 'exception']
            failed_bots = [log for log in all_session_logs if log.get('status') == 'failed' or log.get('status') == 'exception']
            
            try:
                from theme import banner, log_line, style
                print()
                print(style("  ─── Session finished ───", "\033[96m"))
                print(log_line("ok", "Bots that finished OK: %s" % len(successful_bots)))
                print(log_line("err", "Bots that failed: %s" % len(failed_bots)))
                print(log_line("crawl", "Each bot's log (with IP and country) is in: %s" % (LOGS_DIR + "/bot_*/")))
            except ImportError:
                print("\n" + "="*60)
                print("Session finished. OK: %s | Failed: %s | Logs: %s/bot_*/" % (len(successful_bots), len(failed_bots), LOGS_DIR))
                print("="*60)
            
        except ImportError as e:
            print(f"ERROR: Could not import BotManager. Running in single bot mode.")
            print(f"Error details: {e}")
            run_single_bot(urls)
            
    else:
        # Single bot mode (backward compatibility)
        print("🔄 Single bot mode detected (no bot_count file found)")
        run_single_bot(urls)

def run_single_bot(urls):
    """Run single bot instance (backward compatibility)"""
    print("Running in single bot mode...")
    bot = HumanLikeTrafficBot(urls, headless=True)
    
    try:
        session_log = bot.run()
        
        # Save final session log in logs folder
        final_file = os.path.join(LOGS_DIR, 'session_final.json')
        with open(final_file, 'w') as f:
            json.dump(session_log, f, indent=2)
        
        print("\n" + "="*50)
        print("Bot session completed successfully!")
        print(f"Visited {len(session_log['visits'])} URLs")
        print(f"Duration per URL: {bot.stay_duration} seconds")
        print(f"All log files saved in: {LOGS_DIR} folder")
        print("="*50)
        
    except Exception as e:
        print(f"ERROR: Bot session failed: {str(e)}")
    
    finally:
        bot.cleanup()
        
if __name__ == "__main__":
    main()
