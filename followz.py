"""
TWITCH FOLLOW BOT v3.0 - EVENT LOOP SAFE ARCHITECTURE
COMPLETE REWRITE WITH PROPER ASYNCIO LIFECYCLE MANAGEMENT
"""

import json
import os
import random
import threading
import time
import aiohttp
import asyncio
import concurrent.futures
from datetime import datetime
import hashlib
import sys
import signal
import traceback
from typing import Optional, Dict, List, Set
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EventLoopManager:
    """
    Singleton manager for event loops to prevent "event loop is closed" errors
    """
    _instance = None
    _loops: Dict[int, asyncio.AbstractEventLoop] = {}
    _lock = threading.Lock()
    
    @classmethod
    def get_loop(cls) -> asyncio.AbstractEventLoop:
        """Get or create event loop for current thread"""
        thread_id = threading.get_ident()
        
        with cls._lock:
            if thread_id not in cls._loops:
                try:
                    # Try to get existing loop
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    # No loop exists in this thread, create new
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                cls._loops[thread_id] = loop
                
                # Set up proper cleanup
                def cleanup():
                    with cls._lock:
                        if thread_id in cls._loops:
                            try:
                                if not loop.is_closed():
                                    loop.run_until_complete(asyncio.sleep(0))
                                    loop.close()
                            except:
                                pass
                            finally:
                                del cls._loops[thread_id]
                
                # Register cleanup when thread ends
                import weakref
                ref = weakref.ref(loop)
                threading.current_thread()._cleanup = cleanup
            
            return cls._loops[thread_id]
    
    @classmethod
    def cleanup_all(cls):
        """Clean up all event loops"""
        with cls._lock:
            for thread_id, loop in list(cls._loops.items()):
                try:
                    if not loop.is_closed():
                        # Cancel all tasks
                        for task in asyncio.all_tasks(loop):
                            task.cancel()
                        loop.run_until_complete(asyncio.sleep(0))
                        loop.close()
                except:
                    pass
            cls._loops.clear()

class TwitchFollowerSafe:
    """
    COMPLETELY REWRITTEN - EVENT LOOP SAFE VERSION
    No more "event loop is closed" errors!
    """
    
    def __init__(self, max_concurrent=30):
        self.max_concurrent = max_concurrent
        self.running = False
        self.stop_event = threading.Event()
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_concurrent,
            thread_name_prefix="TwitchWorker"
        )
        
        # Statistics
        self.stats = {
            'total_follows': 0,
            'successful': 0,
            'failed': 0,
            'start_time': None,
            'active_tokens': set()
        }
        
        # Session management
        self.sessions: Dict[int, aiohttp.ClientSession] = {}
        self.session_lock = threading.Lock()
        
        # Follow tracking
        self.followed = set()
        self.follow_lock = threading.Lock()
        
        # Twitch API constants
        self.GQL_ENDPOINT = "https://gql.twitch.tv/gql"
        self.CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
        self.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        # Rate limiting
        self.min_delay = 0.2
        self.max_delay = 0.5
        
        logger.info("TwitchFollowerSafe initialized - Event Loop Safe Architecture")
    
    def _log(self, message: str, level: str = "INFO"):
        """Unified logging"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [{level}] {message}"
        
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "DEBUG":
            logger.debug(message)
        else:
            logger.info(message)
        
        # Also print to console
        print(log_msg)
        
        # Write to operations log
        with open("follow_operations.log", "a", encoding="utf-8") as f:
            f.write(log_msg + "\n")
    
    def _get_or_create_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session for current thread"""
        thread_id = threading.get_ident()
        
        with self.session_lock:
            if thread_id not in self.sessions or self.sessions[thread_id].closed:
                # Create new session with proper settings
                connector = aiohttp.TCPConnector(
                    limit=100,
                    ttl_dns_cache=300,
                    force_close=False,
                    enable_cleanup_closed=True
                )
                
                timeout = aiohttp.ClientTimeout(
                    total=30,
                    connect=10,
                    sock_read=20
                )
                
                session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    headers={
                        "Accept": "*/*",
                        "Accept-Encoding": "gzip, deflate, br",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Connection": "keep-alive",
                    }
                )
                
                self.sessions[thread_id] = session
            
            return self.sessions[thread_id]
    
    def _close_all_sessions(self):
        """Close all aiohttp sessions"""
        with self.session_lock:
            for thread_id, session in list(self.sessions.items()):
                try:
                    if not session.closed:
                        # Run in the session's event loop
                        loop = session._loop
                        if not loop.is_closed():
                            loop.run_until_complete(session.close())
                except Exception as e:
                    self._log(f"Error closing session for thread {thread_id}: {e}", "ERROR")
                finally:
                    if thread_id in self.sessions:
                        del self.sessions[thread_id]
    
    def load_tokens(self) -> List[str]:
        """Load and validate tokens"""
        tokens = []
        
        if not os.path.exists("tokens.txt"):
            self._log("ERROR: tokens.txt not found!", "ERROR")
            return []
        
        try:
            with open("tokens.txt", "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    
                    # Clean token
                    token = line.replace("oauth:", "").strip()
                    
                    # Basic validation
                    if len(token) < 30:
                        self._log(f"Line {line_num}: Token too short, skipping", "WARNING")
                        continue
                    
                    # Check for duplicates
                    if token not in tokens:
                        tokens.append(token)
                        self._log(f"Loaded token {len(tokens)}: {token[:8]}...", "DEBUG")
            
            self._log(f"Successfully loaded {len(tokens)} tokens", "SUCCESS")
            return tokens
            
        except Exception as e:
            self._log(f"Error loading tokens: {e}", "ERROR")
            return []
    
    def resolve_user_id(self, username: str) -> Optional[str]:
        """
        SAFE version - No event loop conflicts
        Returns: user_id or None
        """
        self._log(f"Resolving username: {username}", "INFO")
        
        headers = {
            "Client-Id": self.CLIENT_ID,
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
        }
        
        payload = json.dumps([{
            "operationName": "GetIDFromLogin",
            "variables": {"login": username.lower()},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "94e82a7b1e3c21e186daa73ee2afc4b8f23bade1fbbff6fe8ac133f50a2f58ca"
                }
            }
        }])
        
        # Use thread pool to avoid event loop conflicts
        future = self.thread_pool.submit(self._sync_resolve_id, username, headers, payload)
        
        try:
            result = future.result(timeout=30)
            if result:
                self._log(f"Resolved {username} -> ID: {result}", "SUCCESS")
            return result
        except concurrent.futures.TimeoutError:
            self._log(f"Timeout resolving {username}", "ERROR")
            return None
        except Exception as e:
            self._log(f"Error resolving {username}: {e}", "ERROR")
            return None
    
    def _sync_resolve_id(self, username: str, headers: dict, payload: str) -> Optional[str]:
        """
        Synchronous ID resolution using dedicated event loop
        """
        try:
            # Get thread-specific event loop
            loop = EventLoopManager.get_loop()
            
            # Run async function in this loop
            result = loop.run_until_complete(
                self._async_resolve_id(username, headers, payload)
            )
            return result
            
        except Exception as e:
            self._log(f"Sync resolve error for {username}: {e}", "ERROR")
            return None
    
    async def _async_resolve_id(self, username: str, headers: dict, payload: str) -> Optional[str]:
        """Async ID resolution"""
        session = self._get_or_create_session()
        
        try:
            async with session.post(
                self.GQL_ENDPOINT,
                headers=headers,
                data=payload,
                ssl=False
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    if data and len(data) > 0:
                        user_data = data[0].get("data", {}).get("user")
                        if user_data:
                            return user_data.get("id")
                
                return None
                
        except Exception as e:
            self._log(f"Async resolve error: {e}", "ERROR")
            return None
    
    async def _single_follow_operation(self, target_id: str, token: str, target_username: str) -> bool:
        """
        Execute a single follow operation with proper error handling
        """
        token_hash = hashlib.md5(token.encode()).hexdigest()[:8]
        
        headers = {
            "Client-Id": self.CLIENT_ID,
            "Authorization": f"OAuth {token}",
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
        }
        
        payload = json.dumps([{
            "operationName": "FollowUserMutation",
            "variables": {
                "targetId": str(target_id),
                "disableNotifications": True
            },
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "cd112d9483ede85fa0da514a5657141c24396efbc7bac0ea3623e839206573b8"
                }
            }
        }])
        
        session = self._get_or_create_session()
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with session.post(
                    self.GQL_ENDPOINT,
                    headers=headers,
                    data=payload,
                    ssl=False
                ) as response:
                    
                    if response.status in (200, 204):
                        response_text = await response.text()
                        if "errors" not in response_text.lower():
                            self._log(f"Token {token_hash}: Followed {target_username}", "SUCCESS")
                            
                            with self.follow_lock:
                                self.stats['successful'] += 1
                                self.stats['active_tokens'].add(token_hash)
                                self.followed.add(f"{token_hash}:{target_id}")
                            
                            return True
                    
                    # If we get here, follow failed
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    
                    return False
                    
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._log(f"Token {token_hash}: Attempt {attempt + 1} failed - {e}", "ERROR")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
        
        with self.follow_lock:
            self.stats['failed'] += 1
        
        return False
    
    def _token_worker_safe(self, target_id: str, token: str, target_username: str, semaphore: threading.Semaphore):
        """
        SAFE worker using dedicated event loop - NO event loop conflicts
        """
        try:
            # Acquire semaphore for rate limiting
            with semaphore:
                # Get thread-specific event loop
                loop = EventLoopManager.get_loop()
                
                # Run async operation in this thread's loop
                success = loop.run_until_complete(
                    self._single_follow_operation(target_id, token, target_username)
                )
                
                # Update stats
                if success:
                    with self.follow_lock:
                        self.stats['total_follows'] += 1
                
                # Rate limiting delay
                delay = random.uniform(self.min_delay, self.max_delay)
                time.sleep(delay)
                
        except Exception as e:
            self._log(f"Worker error: {e}", "ERROR")
            traceback.print_exc()
    
    def execute_follow_campaign(self, username: str, follow_count: int) -> bool:
        """
        Main execution method - COMPLETELY SAFE from event loop errors
        """
        if self.running:
            self._log("Bot is already running", "WARNING")
            return False
        
        self.running = True
        self.stop_event.clear()
        self.stats = {
            'total_follows': 0,
            'successful': 0,
            'failed': 0,
            'start_time': time.time(),
            'active_tokens': set()
        }
        
        self._log(f"🚀 STARTING CAMPAIGN: {username}", "CAMPAIGN")
        self._log(f"🎯 Target follows: {follow_count}", "INFO")
        
        # Step 1: Resolve username
        user_id = self.resolve_user_id(username)
        if not user_id:
            self._log(f"Failed to resolve username: {username}", "ERROR")
            self.running = False
            return False
        
        self._log(f"✅ Resolved {username} -> {user_id}", "SUCCESS")
        
        # Step 2: Load tokens
        tokens = self.load_tokens()
        if not tokens:
            self._log("No valid tokens found", "ERROR")
            self.running = False
            return False
        
        # Adjust count based on available tokens
        actual_count = min(follow_count, len(tokens))
        if actual_count < follow_count:
            self._log(f"Adjusted from {follow_count} to {actual_count} (token limit)", "WARNING")
        
        self._log(f"📊 Tokens available: {len(tokens)}", "INFO")
        self._log(f"🎯 Final target: {actual_count} follows", "INFO")
        
        # Step 3: Start workers
        semaphore = threading.Semaphore(self.max_concurrent)
        worker_threads = []
        
        # Create worker for each token (up to actual_count)
        tokens_to_use = tokens[:actual_count]
        
        self._log(f"👷 Starting {len(tokens_to_use)} workers...", "WORKERS")
        
        for i, token in enumerate(tokens_to_use):
            if self.stop_event.is_set():
                break
            
            # Create worker thread
            worker = threading.Thread(
                target=self._token_worker_safe,
                args=(user_id, token, username, semaphore),
                name=f"Worker-{i+1}",
                daemon=True
            )
            
            worker.start()
            worker_threads.append(worker)
            
            # Stagger worker creation
            if i % 10 == 0 and i > 0:
                time.sleep(0.1)
        
        # Wait for all workers to complete
        self._log("⏳ Waiting for workers to complete...", "INFO")
        
        # Monitor progress
        start_time = time.time()
        last_update = start_time
        
        while any(t.is_alive() for t in worker_threads) and not self.stop_event.is_set():
            time.sleep(1)
            
            # Update progress every 5 seconds
            current_time = time.time()
            if current_time - last_update >= 5:
                elapsed = current_time - start_time
                with self.follow_lock:
                    completed = self.stats['successful']
                    failed = self.stats['failed']
                    total = completed + failed
                
                if total > 0:
                    progress = (total / actual_count) * 100
                    rate = completed / elapsed if elapsed > 0 else 0
                    
                    self._log(
                        f"📊 Progress: {completed}/{actual_count} ({progress:.1f}%) | "
                        f"Rate: {rate:.2f}/sec | "
                        f"Elapsed: {elapsed:.1f}s | "
                        f"Failed: {failed}",
                        "PROGRESS"
                    )
                
                last_update = current_time
        
        # Campaign complete
        end_time = time.time()
        elapsed = end_time - start_time
        
        self._log("=" * 60, "SUMMARY")
        self._log(f"🎉 CAMPAIGN COMPLETE: {username}", "SUCCESS")
        self._log(f"✅ Successful follows: {self.stats['successful']}/{actual_count}", "SUMMARY")
        self._log(f"❌ Failed follows: {self.stats['failed']}", "SUMMARY")
        self._log(f"⏱️  Time elapsed: {elapsed:.1f} seconds", "SUMMARY")
        
        if elapsed > 0:
            rate = self.stats['successful'] / elapsed
            self._log(f"🚀 Average rate: {rate:.2f} follows/second", "SUMMARY")
        
        self._log(f"🔑 Unique tokens used: {len(self.stats['active_tokens'])}", "SUMMARY")
        self._log("=" * 60, "SUMMARY")
        
        # Save results
        self._save_campaign_results(username, user_id, actual_count)
        
        self.running = False
        return True
    
    def _save_campaign_results(self, username: str, user_id: str, target_count: int):
        """Save campaign results to file"""
        results = {
            "username": username,
            "user_id": user_id,
            "target_follows": target_count,
            "successful_follows": self.stats['successful'],
            "failed_follows": self.stats['failed'],
            "unique_tokens": len(self.stats['active_tokens']),
            "completion_time": datetime.now().isoformat(),
            "duration_seconds": time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
        }
        
        filename = f"campaign_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            self._log(f"Results saved to {filename}", "INFO")
        except Exception as e:
            self._log(f"Error saving results: {e}", "ERROR")
    
    def stop(self):
        """Stop the bot immediately"""
        if not self.running:
            return
        
        self._log("🛑 Stopping bot...", "SHUTDOWN")
        self.stop_event.set()
        self.running = False
        
        # Give threads time to finish
        time.sleep(2)
        
        # Close all sessions
        self._close_all_sessions()
        
        # Clean up event loops
        EventLoopManager.cleanup_all()
        
        self._log("✅ Bot stopped", "SHUTDOWN")
    
    def get_status(self) -> dict:
        """Get current bot status"""
        status = {
            "running": self.running,
            "stats": self.stats.copy(),
            "followed_count": len(self.followed),
            "unique_tokens_used": len(self.stats.get('active_tokens', set()))
        }
        
        if self.stats.get('start_time'):
            status["elapsed_seconds"] = time.time() - self.stats['start_time']
        
        return status


# ============================================================================
# ENHANCED CLI WITH EVENT LOOP PROTECTION
# ============================================================================

class SafeCLI:
    """CLI with proper event loop management"""
    
    def __init__(self):
        self.bot = None
        self.monitor_thread = None
        self.stop_monitor = threading.Event()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        print(f"\n⚠️  Received signal {signum}, shutting down...")
        if self.bot:
            self.bot.stop()
        self.stop_monitor.set()
        EventLoopManager.cleanup_all()
        print("✅ Clean shutdown complete")
        sys.exit(0)
    
    def _monitor_campaign(self):
        """Monitor campaign progress"""
        last_stats = None
        
        while not self.stop_monitor.is_set() and self.bot and self.bot.running:
            try:
                status = self.bot.get_status()
                current_time = time.time()
                
                # Only update if stats changed
                if status != last_stats:
                    if status['stats'].get('start_time'):
                        elapsed = status.get('elapsed_seconds', 0)
                        successful = status['stats'].get('successful', 0)
                        failed = status['stats'].get('failed', 0)
                        total = successful + failed
                        
                        if total > 0 and elapsed > 0:
                            rate = successful / elapsed
                            progress = (total / max(total, 1)) * 100
                            
                            print(f"\r📊 Progress: {successful} successful, {failed} failed | "
                                  f"Rate: {rate:.2f}/sec | "
                                  f"Elapsed: {elapsed:.1f}s | "
                                  f"Progress: {progress:.1f}%", end="", flush=True)
                
                last_stats = status.copy()
                time.sleep(1)
                
            except Exception as e:
                print(f"\nMonitoring error: {e}")
                break
        
        print("\n" + "="*60)
    
    def _clear_screen(self):
        """Clear terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def _print_banner(self):
        """Print application banner"""
        banner = """
        ╔══════════════════════════════════════════════════════════╗
        ║     🚀 TWITCH FOLLOW BOT v3.0 - EVENT LOOP SAFE         ║
        ║            NO MORE "EVENT LOOP IS CLOSED" ERRORS!       ║
        ╠══════════════════════════════════════════════════════════╣
        ║  ✅ Fixed event loop lifecycle management               ║
        ║  ✅ Thread-safe async operations                        ║
        ║  ✅ Proper session cleanup                              ║
        ║  ✅ Graceful shutdown handling                          ║
        ╚══════════════════════════════════════════════════════════╝
        """
        print(banner)
    
    def _check_requirements(self):
        """Check if all requirements are met"""
        requirements = [
            ("tokens.txt", os.path.exists("tokens.txt"), "Contains OAuth tokens"),
            ("Python 3.7+", sys.version_info >= (3, 7), "Required for asyncio features"),
            ("aiohttp", self._check_module("aiohttp"), "HTTP client library"),
        ]
        
        print("🔍 System Check:")
        print("-" * 50)
        
        all_ok = True
        for name, check, desc in requirements:
            status = "✅" if check else "❌"
            print(f"{status} {name:20} - {desc}")
            if not check:
                all_ok = False
        
        print("-" * 50)
        
        if not all_ok:
            print("\n⚠️  Some requirements are missing:")
            if not os.path.exists("tokens.txt"):
                print("   - Create tokens.txt with your OAuth tokens")
                print("   - One token per line, format: oauth:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
            if not self._check_module("aiohttp"):
                print("   - Install aiohttp: pip install aiohttp")
            
            response = input("\nContinue anyway? (y/N): ").lower()
            if response != 'y':
                return False
        
        return True
    
    def _check_module(self, module_name):
        """Check if module is available"""
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False
    
    def run(self):
        """Main CLI loop"""
        self._clear_screen()
        self._print_banner()
        
        # Check requirements
        if not self._check_requirements():
            print("❌ Requirements not met. Exiting.")
            return
        
        print("\n📋 Available commands:")
        print("   start  - Start a new follow campaign")
        print("   status - Check current status")
        print("   stop   - Stop current campaign")
        print("   exit   - Exit the program")
        print("   help   - Show this help")
        print("\n" + "="*60)
        
        # Main command loop
        while True:
            try:
                command = input("\n🤖 Command: ").strip().lower()
                
                if command == "start":
                    self._start_campaign()
                elif command == "status":
                    self._show_status()
                elif command == "stop":
                    self._stop_campaign()
                elif command == "exit":
                    self._exit_program()
                    break
                elif command == "help":
                    self._print_help()
                elif command == "clear":
                    self._clear_screen()
                elif command:
                    print(f"❌ Unknown command: {command}")
                
            except KeyboardInterrupt:
                print("\n\n⚠️  Interrupted. Type 'exit' to quit.")
            except Exception as e:
                print(f"❌ Error: {e}")
                traceback.print_exc()
    
    def _start_campaign(self):
        """Start a new campaign"""
        if self.bot and self.bot.running:
            print("❌ Bot is already running. Stop it first.")
            return
        
        print("\n" + "="*60)
        print("🚀 START NEW FOLLOW CAMPAIGN")
        print("="*60)
        
        # Get target username
        username = input("Target Twitch username: ").strip().lower()
        if not username:
            print("❌ Username cannot be empty")
            return
        
        # Get follow count
        try:
            count = int(input("Number of follows to attempt: ").strip())
            if count <= 0:
                print("❌ Count must be positive")
                return
            if count > 500:
                print(f"⚠️  Warning: Large follow counts ({count}) may trigger rate limits")
                confirm = input("Continue? (y/N): ").lower()
                if confirm != 'y':
                    return
        except ValueError:
            print("❌ Invalid number")
            return
        
        # Create bot instance
        self.bot = TwitchFollowerSafe(max_concurrent=20)
        
        # Start monitor thread
        self.stop_monitor.clear()
        self.monitor_thread = threading.Thread(
            target=self._monitor_campaign,
            daemon=True
        )
        self.monitor_thread.start()
        
        # Start campaign in separate thread to keep CLI responsive
        campaign_thread = threading.Thread(
            target=self.bot.execute_follow_campaign,
            args=(username, count),
            daemon=True
        )
        campaign_thread.start()
        
        print(f"\n✅ Campaign started for @{username}")
        print("📊 Monitoring progress... (Press Ctrl+C to interrupt)")
        
        # Wait for campaign to complete
        campaign_thread.join(timeout=3600)  # 1 hour timeout
        
        if campaign_thread.is_alive():
            print("\n⚠️  Campaign is taking longer than expected...")
            print("   Type 'status' to check progress or 'stop' to cancel")
        else:
            print("\n✅ Campaign completed!")
            self.stop_monitor.set()
    
    def _show_status(self):
        """Show current status"""
        if not self.bot:
            print("❌ Bot not initialized. Start a campaign first.")
            return
        
        status = self.bot.get_status()
        
        print("\n" + "="*60)
        print("🤖 BOT STATUS")
        print("="*60)
        
        if status['running']:
            print("🟢 Status: RUNNING")
            
            if status['stats'].get('start_time'):
                elapsed = status.get('elapsed_seconds', 0)
                successful = status['stats'].get('successful', 0)
                failed = status['stats'].get('failed', 0)
                total = successful + failed
                
                print(f"⏱️  Elapsed time: {elapsed:.1f} seconds")
                print(f"✅ Successful follows: {successful}")
                print(f"❌ Failed follows: {failed}")
                print(f"📊 Total attempts: {total}")
                
                if elapsed > 0 and total > 0:
                    rate = successful / elapsed
                    print(f"🚀 Rate: {rate:.2f} follows/second")
                
                if total > 0:
                    progress = (successful / total) * 100
                    print(f"📈 Success rate: {progress:.1f}%")
        else:
            print("🔴 Status: STOPPED")
            print(f"📊 Last campaign stats:")
            print(f"   ✅ Successful follows: {status['stats'].get('successful', 0)}")
            print(f"   ❌ Failed follows: {status['stats'].get('failed', 0)}")
            print(f"   🔑 Unique tokens used: {status['unique_tokens_used']}")
        
        print("="*60)
    
    def _stop_campaign(self):
        """Stop current campaign"""
        if not self.bot:
            print("❌ Bot not running")
            return
        
        print("🛑 Stopping campaign...")
        self.bot.stop()
        self.stop_monitor.set()
        time.sleep(1)
        print("✅ Campaign stopped")
    
    def _exit_program(self):
        """Exit the program"""
        print("\n👋 Exiting...")
        
        if self.bot and self.bot.running:
            print("🛑 Stopping bot...")
            self.bot.stop()
        
        self.stop_monitor.set()
        EventLoopManager.cleanup_all()
        
        print("✅ Cleanup complete. Goodbye!")
        sys.exit(0)
    
    def _print_help(self):
        """Print help information"""
        help_text = """
        ╔══════════════════════════════════════════════════════════╗
        ║                      COMMAND REFERENCE                   ║
        ╠══════════════════════════════════════════════════════════╣
        ║  start    - Start a new follow campaign                 ║
        ║  status   - Show current bot status and statistics      ║
        ║  stop     - Stop the current campaign                   ║
        ║  clear    - Clear the terminal screen                   ║
        ║  exit     - Exit the program (with cleanup)            ║
        ║  help     - Show this help message                      ║
        ╠══════════════════════════════════════════════════════════╣
        ║                    TROUBLESHOOTING                       ║
        ╠══════════════════════════════════════════════════════════╣
        ║  ❌ "Event loop is closed" - Fixed in v3.0!             ║
        ║  ❌ Network errors - Check tokens.txt format            ║
        ║  ❌ Rate limiting - Reduce concurrent workers           ║
        ║  ✅ All operations are now thread-safe                 ║
        ╚══════════════════════════════════════════════════════════╝
        """
        print(help_text)


# ============================================================================
# MAIN ENTRY POINT WITH PROPER CLEANUP
# ============================================================================

def main():
    """Main entry point with comprehensive error handling"""
    
    print("Initializing Twitch Follow Bot v3.0...")
    
    # Register cleanup function
    import atexit
    atexit.register(EventLoopManager.cleanup_all)
    
    try:
        # Create and run CLI
        cli = SafeCLI()
        cli.run()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        EventLoopManager.cleanup_all()
        print("✅ Clean shutdown")
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        traceback.print_exc()
        
        # Attempt cleanup
        try:
            EventLoopManager.cleanup_all()
        except:
            pass
        
        print("\n💡 TROUBLESHOOTING TIPS:")
        print("1. Check tokens.txt format (one OAuth token per line)")
        print("2. Ensure you have internet connection")
        print("3. Check bot_debug.log for detailed errors")
        print("4. Restart the application")
        
        input("\nPress Enter to exit...")


if __name__ == "__main__":
    # Set up proper asyncio policy for Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Run main function
    main()
