import sys
import time
import random
import logging
import json
import os
import concurrent.futures
from threading import Semaphore
import re
from SC_BOT import HumanLikeTrafficBot

# Force UTF-8 encoding for Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

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
            
            # Validate bot count (minimum 1, maximum UNLIMITED)
            if bot_count < 1:
                bot_count = 1

            # Show warnings for large numbers but allow them
            if bot_count > 1000:
                print(f"[WARNING] EXTREME WARNING: Running {bot_count} bots!")
                print(f"[RAM] This will use ~{bot_count * 200}MB RAM and significant CPU!")
                print(f"[FIRE] Only proceed if you have a powerful system!")
                input("Press Enter to continue or Ctrl+C to cancel...")
            elif bot_count > 500:
                print(f"[WARNING] HIGH LOAD: Running {bot_count} bots")
                print(f"[MEMORY] Expected RAM usage: ~{bot_count * 200}MB")
            elif bot_count > 100:
                print(f"[CHART] Large scale: {bot_count} bots")
                
            print(f"[TARGET] Configured bot count: {bot_count}")
            return bot_count
            
        except Exception as e:
            print(f"[ERROR] Error reading bot_count.txt: {str(e)}")
            return self.max_bots  # Use minimal fallback
    
    # ... rest of the methods remain the same ...
    def setup_bot_logging(self, bot_id):
        """Setup individual logging for each bot"""
        bot_logs_dir = os.path.join(self.LOGS_DIR, f'bot_{bot_id}')
        os.makedirs(bot_logs_dir, exist_ok=True)
        
        log_file = os.path.join(bot_logs_dir, 'bot_activity.log')
        
        # Create bot-specific logger
        logger = logging.getLogger(f'bot_{bot_id}')
        logger.setLevel(logging.INFO)
        
        # Clear previous handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Add file handler for this bot
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
        
        # Only show console output for first 50 bots to avoid spam
        if bot_id <= 50:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(f'%(asctime)s - BOT_{bot_id} - %(levelname)s - %(message)s'))
            logger.addHandler(console_handler)
        
        return logger, bot_logs_dir
    
    def run_single_bot(self, bot_id, urls, stay_duration):
        """Run a single bot instance"""
        try:
            bot_logger, bot_logs_dir = self.setup_bot_logging(bot_id)
            
            # Only log startup for first 50 bots to avoid console spam
            if bot_id <= 50:
                bot_logger.info(f"[ROCKET] Bot {bot_id} STARTING with {len(urls)} URLs")
            
            # Create bot instance with optimized settings
            bot = HumanLikeTrafficBot(urls, headless=True)
            bot.logger = bot_logger  # Override with bot-specific logger
            
            # Run the bot
            session_log = bot.run()
            session_log['bot_id'] = bot_id
            session_log['bot_logs_dir'] = bot_logs_dir
            
            # Save bot-specific session log
            bot_final_file = os.path.join(bot_logs_dir, 'session_final.json')
            with open(bot_final_file, 'w') as f:
                json.dump(session_log, f, indent=2)
            
            if bot_id <= 50:
                bot_logger.info(f"[OK] Bot {bot_id} COMPLETED successfully")
            return session_log
            
        except Exception as e:
            # Emergency logger for all failed bots
            emergency_logger = logging.getLogger('emergency')
            if not emergency_logger.handlers:
                emergency_handler = logging.StreamHandler()
                emergency_handler.setFormatter(logging.Formatter('%(asctime)s - EMERGENCY - %(levelname)s - %(message)s'))
                emergency_logger.addHandler(emergency_handler)
                emergency_logger.setLevel(logging.ERROR)
            
            emergency_logger.error(f"[ERROR] Bot {bot_id} FAILED: {str(e)}")
            return {'bot_id': bot_id, 'status': 'failed', 'error': str(e)}
        finally:
            if 'bot' in locals():
                bot.cleanup()
    
    def run_distributed_bots(self, urls, stay_duration):
        """Run multiple bots with intelligent resource management"""
        bot_count = self.read_bot_count()
        
        print(f"\n[ROCKET] STARTING {bot_count} BOT INSTANCES SIMULTANEOUSLY...")
        print(f"[CHART] URLs per bot: {len(urls)}")
        print(f"[CLOCK] Duration per URL: {stay_duration} seconds")
        print(f"[FOLDER] Logs directory: {self.LOGS_DIR}")
        print("="*60)
        
        # Intelligent concurrency based on bot count
        if bot_count <= 50:
            max_concurrent = bot_count  # All at once for small numbers
        elif bot_count <= 100:
            max_concurrent = 50  # Reasonable for medium scale
        else:
            max_concurrent = 80  # High but manageable for large scale
        
        print(f"[LIGHTNING] Max concurrent bots: {max_concurrent}")
        print("="*60)
        
        semaphore = Semaphore(max_concurrent)
        
        def run_bot_with_limits(bot_id):
            with semaphore:
                return self.run_single_bot(bot_id, urls, stay_duration)
        
        # Use ThreadPoolExecutor for parallel execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            # Submit all bot tasks
            future_to_bot = {
                executor.submit(run_bot_with_limits, bot_id): bot_id 
                for bot_id in range(1, bot_count + 1)
            }
            
            print(f"[TARGET] All {bot_count} bots submitted for execution!")
            print("[CHART] Bots are now running in parallel...")
            if bot_count > 50:
                print("[MUTE] Console output limited to first 50 bots to reduce spam")
            
            # Collect results as they complete
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
                    
                    # Show progress for large numbers
                    if bot_count > 50 and completed_count % 10 == 0:
                        print(f"[CHART] Progress: {completed_count}/{bot_count} ([OK]{successful_bots} [ERROR]{failed_bots})")
                    elif bot_count <= 50:
                        print(f"[OK] Bot {bot_id} finished ({completed_count}/{bot_count})")

                        
                except Exception as e:
                    failed_bots += 1
                    print(f"[ERROR] Bot {bot_id} generated exception: {e}")
                    self.session_logs.append({'bot_id': bot_id, 'status': 'exception', 'error': str(e)})
        
        return self.session_logs