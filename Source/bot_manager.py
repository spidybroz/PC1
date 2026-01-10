import sys
import time
import random
import logging
import json
import os
import io
import concurrent.futures
import threading
import psutil
import gc
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
        self.max_bots = 1
        self.bot_instances = []
        self.session_logs = []
        self.completed_count = 0
        self.successful_bots = 0
        self.failed_bots = 0
        self.lock = threading.Lock()
        
        # Get project root
        self.PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.LOGS_DIR = os.path.join(self.PROJECT_ROOT, 'Logs')
        self.CUSTOMIZE_DIR = os.path.join(self.PROJECT_ROOT, 'Customize')
        
    def read_bot_count(self):
        """Read bot count from bot_count.txt file - UNLIMITED SCALING"""
        try:
            count_file = os.path.join(self.CUSTOMIZE_DIR, "bot_count.txt")
            
            if not os.path.exists(count_file):
                print(f"[ERROR] bot_count.txt is empty. Please add a number.")
                return self.max_bots
            
            with open(count_file, 'r') as f:
                content = f.read().strip()
                
            if not content:
                print(f"[ERROR] bot_count.txt is empty. Please add a number.")
                return self.max_bots
            
            bot_count = int(content)
            
            # Validate bot count
            if bot_count < 1:
                bot_count = 1
                
            return bot_count
            
        except Exception as e:
            print(f"[ERROR] Error reading bot_count.txt: {str(e)}")
            return self.max_bots
    
    def setup_bot_logging(self, bot_id):
        """Setup lightweight logging for each bot"""
        bot_logs_dir = os.path.join(self.LOGS_DIR, f'bot_{bot_id}')
        os.makedirs(bot_logs_dir, exist_ok=True)
        
        log_file = os.path.join(bot_logs_dir, 'bot_activity.log')
        
        # Create lightweight logger
        logger = logging.getLogger(f'bot_{bot_id}')
        logger.setLevel(logging.INFO)
        
        # Clear previous handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Add file handler only (no console output)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
        
        return logger, bot_logs_dir
    
    def run_single_bot(self, bot_id, urls, stay_duration):
        """Run a single bot instance with optimized resource usage"""
        try:
            bot_logger, bot_logs_dir = self.setup_bot_logging(bot_id)
            
            # Create bot instance with ultra-minimal settings
            bot = HumanLikeTrafficBot(urls, headless=True)
            bot.logger = bot_logger
            
            # Run the bot
            session_log = bot.run()
            session_log['bot_id'] = bot_id
            session_log['bot_logs_dir'] = bot_logs_dir
            
            # Save session log
            bot_final_file = os.path.join(bot_logs_dir, 'session_final.json')
            with open(bot_final_file, 'w') as f:
                json.dump(session_log, f, indent=2)
            
            return {'bot_id': bot_id, 'status': 'success'}
            
        except Exception as e:
            return {'bot_id': bot_id, 'status': 'failed', 'error': str(e)}
        finally:
            if 'bot' in locals():
                bot.cleanup()
            # Force garbage collection
            gc.collect()
    
    def run_distributed_bots(self, urls, stay_duration):
        """Run ALL bots simultaneously (no limiting)"""
        bot_count = self.read_bot_count()
        
        print(f"\n[EXTREME SCALING] STARTING {bot_count} BOT INSTANCES SIMULTANEOUSLY!")
        print(f"[WARNING] This will consume massive resources!")
        print(f"[ESTIMATE] RAM: ~{bot_count * 150 / 1024:.1f} GB")
        print(f"[CPU] All cores will be utilized")
        print("="*70)
        
        # No concurrency limits - run ALL at once
        max_concurrent = bot_count
        
        print(f"[FULL PARALLEL] Max concurrent bots: {max_concurrent}")
        print("[STRATEGY] All bots start together for maximum impact")
        print("="*70)
        
        # Track start time
        start_time = time.time()
        
        # Use ProcessPoolExecutor for better CPU utilization
        with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count() * 2) as executor:
            # Submit all bot tasks at once
            futures = []
            for bot_id in range(1, bot_count + 1):
                future = executor.submit(self.run_single_bot, bot_id, urls, stay_duration)
                futures.append(future)
            
            print(f"[LAUNCHED] All {bot_count} bots submitted for simultaneous execution!")
            print("[STATUS] Monitoring progress...")
            
            # Collect results as they complete
            results = []
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result(timeout=3600)  # 1 hour timeout
                    results.append(result)
                    
                    with self.lock:
                        self.completed_count += 1
                        if result.get('status') == 'success':
                            self.successful_bots += 1
                        else:
                            self.failed_bots += 1
                        
                        # Show progress every 1000 bots
                        if self.completed_count % 1000 == 0:
                            elapsed = time.time() - start_time
                            print(f"[PROGRESS] {self.completed_count}/{bot_count} "
                                  f"(✓{self.successful_bots} ✗{self.failed_bots}) "
                                  f"Elapsed: {elapsed:.1f}s")
                            
                except concurrent.futures.TimeoutError:
                    print(f"[TIMEOUT] Bot timed out after 1 hour")
                    self.failed_bots += 1
                except Exception as e:
                    print(f"[ERROR] Exception in bot: {e}")
                    self.failed_bots += 1
        
        total_time = time.time() - start_time
        
        print("\n" + "="*70)
        print("🎯 MASSIVE SCALE OPERATION COMPLETE!")
        print("="*70)
        print(f"✅ Successful bots: {self.successful_bots}")
        print(f"❌ Failed bots: {self.failed_bots}")
        print(f"⏱️ Total time: {total_time:.1f} seconds")
        print(f"🚀 Average speed: {bot_count/total_time:.2f} bots/second")
        print(f"📊 Total URLs processed: {self.successful_bots * len(urls)}")
        print(f"💾 Logs saved in: {self.LOGS_DIR}")
        print("="*70)
        
        return results
