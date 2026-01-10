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
from fake_useragent import UserAgent
from urllib.parse import urlparse

# Set UTF-8 encoding for stdout/stderr
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(PROJECT_ROOT, 'Logs')
CUSTOMIZE_DIR = os.path.join(PROJECT_ROOT, 'Customize')

class HumanLikeTrafficBot:
    def __init__(self, urls, headless=False):
        self.urls = urls
        self.headless = headless
        self.driver = None
        self.current_user_agent = None
        self.stay_duration = self.read_stay_duration()
        
        # Create logs directory if it doesn't exist
        os.makedirs(LOGS_DIR, exist_ok=True)
        
        self.setup_logging()
        self.setup_driver()
        
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
        """Setup comprehensive logging with real-time output"""
        log_file = os.path.join(LOGS_DIR, 'SC_BOT.log')
        
        # Clear previous log file to start fresh
        with open(log_file, 'w') as f:
            f.write("")
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()  # This ensures real-time console output
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def setup_driver(self):
        """Setup Chrome driver with human-like configurations"""
        try:
            from selenium.webdriver.chrome.options import Options
            
            options = Options()
            
            # Random user agent
            ua = UserAgent()
            self.current_user_agent = ua.random
            options.add_argument(f'--user-agent={self.current_user_agent}')
            
            # Common browser arguments
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            # Disable automatic redirects
            options.add_argument('--disable-features=NetworkService')
            
            # Headless-specific optimizations
            if self.headless:
                options.add_argument('--headless=new')  # New headless mode
                options.add_argument('--disable-gpu')  # GPU not needed in headless
                options.add_argument('--disable-software-rasterizer')
                options.add_argument('--no-first-run')
                options.add_argument('--no-default-browser-check')
                options.add_argument('--disable-background-timer-throttling')
                options.add_argument('--disable-backgrounding-occluded-windows')
                options.add_argument('--disable-renderer-backgrounding')
                options.add_argument('--disable-extensions')
                options.add_argument('--disable-plugins')
                options.add_argument('--disable-images')  # Save bandwidth
            else:
                # Window size variations only for visible mode
                resolutions = ['1920,1080', '1366,768', '1536,864', '1440,900']
                options.add_argument(f'--window-size={random.choice(resolutions)}')
            
            self.driver = webdriver.Chrome(options=options)
            
            # Execute CDP commands to prevent detection
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": self.current_user_agent
            })
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            self.logger.info(f"Driver initialized with user agent: {self.current_user_agent}")
            self.logger.info(f"Total stay duration per URL: {self.stay_duration} seconds")
            self.logger.info(f"Running in {'HEADLESS' if self.headless else 'VISIBLE'} mode")
            
        except Exception as e:
            self.logger.error(f"Failed to setup driver: {str(e)}")
            raise
    
    def human_delay(self, min_seconds=2, max_seconds=8):
        """Random delay to mimic human thinking time"""
        delay = random.uniform(min_seconds, max_seconds)
        self.logger.debug(f"Human delay: {delay:.2f}s")
        time.sleep(delay)
    
    def random_mouse_movements(self):
        """Simulate random mouse movements"""
        try:
            self.logger.info("Performing random mouse movements")
            
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
            
            self.logger.info("Completed mouse movements")
            
        except Exception as e:
            self.logger.debug(f"Mouse movement interrupted: {str(e)}")
    
    def scroll_behavior(self):
        """Simulate natural scrolling behavior"""
        try:
            self.logger.info("Performing scrolling behavior")
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
                
            self.logger.info("Completed scrolling")
                
        except Exception as e:
            self.logger.debug(f"Scrolling interrupted: {str(e)}")
    
    def click_random_elements(self):
        """Click on random interactive elements"""
        try:
            self.logger.info("Looking for clickable elements...")
            
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
            
            self.logger.info(f"Found {len(clickable_elements)} clickable elements")
            
            if clickable_elements:
                # Click 1-3 random elements
                click_count = random.randint(1, min(3, len(clickable_elements)))
                self.logger.info(f"Attempting to click {click_count} elements")
                
                for i in range(click_count):
                    element = random.choice(clickable_elements)
                    try:
                        # Remove the element from list to avoid clicking same element twice
                        clickable_elements.remove(element)
                        
                        self.logger.info(f"Preparing to click element {i+1}: {element.tag_name}")
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                        self.human_delay(1, 3)
                        
                        # Get element text for logging
                        element_text = element.text[:50] + "..." if len(element.text) > 50 else element.text
                        self.logger.info(f"Clicking element: {element.tag_name} with text: '{element_text}'")
                        
                        element.click()
                        self.logger.info(f"Successfully clicked element {i+1}")
                        self.human_delay(2, 5)
                        
                    except Exception as e:
                        self.logger.warning(f"Could not click element: {str(e)}")
                        continue
                        
            else:
                self.logger.info("No clickable elements found on this page")
                        
        except Exception as e:
            self.logger.error(f"Element clicking failed: {str(e)}")
    
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
            self.logger.info(f"Visiting: {target_url}")
            self.logger.info(f"Scheduled stay duration: {self.stay_duration} seconds")
            
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
                self.logger.warning(f"URL was redirected from {target_normalized} to {current_normalized}")
                visit_log['redirected_to'] = current_normalized
                
                # Try to go back to original URL
                try:
                    self.logger.info("Attempting to navigate back to original URL...")
                    self.driver.get(target_url)
                    time.sleep(3)  # Wait for navigation
                    
                    # Check again
                    new_current = self.driver.current_url
                    new_normalized = self.normalize_url(new_current)
                    
                    if new_normalized == target_normalized:
                        self.logger.info("Successfully returned to original URL")
                        visit_log['redirect_fixed'] = True
                    else:
                        self.logger.warning(f"Still on redirected URL: {new_normalized}")
                        visit_log['redirect_fixed'] = False
                except Exception as e:
                    self.logger.error(f"Failed to return to original URL: {str(e)}")
                    visit_log['redirect_fixed'] = False
            else:
                self.logger.info("Successfully loaded exact target URL")
                visit_log['redirect_fixed'] = True
            
            # Calculate action plan based on total duration
            action_plan = self.calculate_action_plan(self.stay_duration)
            
            # Initial human delay after page load
            initial_delay = random.uniform(*action_plan['initial_load_delay'])
            self.logger.info(f"Initial page load delay: {initial_delay:.2f}s")
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
                self.logger.info(f"Starting session {session_count} - {remaining_time:.1f}s remaining")
                
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
                self.logger.info(f"Session {session_count} will perform {len(sessions)} actions")
                
                # Execute sessions
                for session_name, session_function in sessions:
                    if time.time() - start_time >= self.stay_duration:
                        self.logger.info("Time limit reached, stopping session")
                        break
                        
                    self.logger.info(f"Executing: {session_name}")
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
                        self.logger.info("Skipping action delay due to time constraints")
                
                # Break between sessions
                remaining_time = self.stay_duration - (time.time() - start_time)
                if remaining_time > 10:  # Only break if significant time remains
                    break_duration = min(
                        random.uniform(*action_plan['break_duration_range']),
                        remaining_time * 0.8  # Don't use all remaining time for break
                    )
                    self.logger.info(f"Break between sessions: {break_duration:.1f}s")
                    time.sleep(break_duration)
                else:
                    self.logger.info("No time for break between sessions")
            
            # Ensure exact time is spent
            remaining_time = self.stay_duration - (time.time() - start_time)
            if remaining_time > 0:
                self.logger.info(f"Final delay of {remaining_time:.1f}s to complete scheduled duration")
                time.sleep(remaining_time)
                visit_log['actual_duration'] = self.stay_duration
            else:
                visit_log['actual_duration'] = time.time() - start_time
            
            visit_log['end_time'] = datetime.now().isoformat()
            visit_log['total_actions'] = action_count
            visit_log['total_sessions'] = session_count
            
            self.logger.info(f"Completed visit to {url}. Duration: {visit_log['actual_duration']:.2f}s, Actions: {action_count}, Sessions: {session_count}")
            
        except Exception as e:
            visit_log['status'] = 'error'
            visit_log['error'] = str(e)
            self.logger.error(f"Error visiting {url}: {str(e)}")
        
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
        
        self.logger.info(f"Starting bot session with {len(self.urls)} URLs")
        self.logger.info(f"Each URL will be visited for {self.stay_duration} seconds")
        
        for i, url in enumerate(self.urls, 1):
            self.logger.info(f"Processing URL {i}/{len(self.urls)}")
            
            # Random delay between URL visits (1-5 minutes)
            if i > 1:
                between_visit_delay = random.uniform(60, 300)
                self.logger.info(f"Waiting {between_visit_delay:.2f}s before next visit")
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
            self.logger.info("Browser closed")

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
            
            print("\n" + "="*60)
            print("🤖 MULTI-BOT SESSION SUMMARY")
            print("="*60)
            print(f"✅ Successful bots: {len(successful_bots)}")
            print(f"❌ Failed bots: {len(failed_bots)}")
            print(f"📊 Total URLs processed: {len(successful_bots) * len(urls)}")
            print(f"💾 Individual bot logs saved in: {LOGS_DIR}/bot_*/")
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