"""
TWITCH FOLLOW BOT v2.0 - PROXY-FREE ARCHITECTURE
DESIGNED FOR DIRECT CONNECTIONS WITHOUT INTERMEDIARY LAYERS
USE AT YOUR OWN RISK - UNDERSTAND TWITCH'S TERMS OF SERVICE
"""

import json
import os
import random
import threading
import time
import aiohttp
import asyncio
from datetime import datetime
import hashlib
import sys

class TwitchFollowerDirect:
    """
    DIRECT CONNECTION FOLLOW BOT
    Eliminates proxy overhead for faster, more reliable operations
    """
    
    def __init__(self, log_callback=print, max_concurrent=50):
        self.log_callback = log_callback
        self.followed_records = {}
        self.lock = threading.Lock()
        self.running = False
        self.max_concurrent = max_concurrent
        self.session_cache = {}
        self.request_stats = {
            'total_requests': 0,
            'successful': 0,
            'failed': 0,
            'start_time': None
        }
        
        # Twitch API Constants
        self.GQL_ENDPOINT = "https://gql.twitch.tv/gql"
        self.CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
        self.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        # Operation limits (adjust carefully)
        self.RATE_LIMIT_DELAY = 0.15  # Minimum seconds between requests per token
        self.MAX_RETRIES = 3
        self.TIMEOUT_SECONDS = 15

    def _log(self, message, level="INFO"):
        """Enhanced logging with timestamps and levels"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        formatted = f"[{timestamp}] [{level}] {message}"
        self.log_callback(formatted)
        
        # Also write to file
        with open("bot_operation.log", "a", encoding="utf-8") as log_file:
            log_file.write(formatted + "\n")

    def _get_session(self):
        """Create or retrieve async session for current thread"""
        thread_id = threading.get_ident()
        if thread_id not in self.session_cache:
            connector = aiohttp.TCPConnector(
                limit=100,
                ttl_dns_cache=300,
                force_close=False,
                enable_cleanup_closed=True
            )
            timeout = aiohttp.ClientTimeout(
                total=self.TIMEOUT_SECONDS,
                connect=5,
                sock_read=10
            )
            session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    "Accept": "*/*",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "DNT": "1",
                    "Origin": "https://www.twitch.tv",
                    "Pragma": "no-cache",
                    "Referer": "https://www.twitch.tv/",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-site",
                }
            )
            self.session_cache[thread_id] = session
        return self.session_cache[thread_id]

    def _load_tokens(self):
        """Load authentication tokens from file with validation"""
        tokens = []
        invalid_tokens = []
        
        if not os.path.exists("tokens.txt"):
            self._log("CRITICAL: tokens.txt not found!", "ERROR")
            return []
        
        with open("tokens.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.isspace():
                continue
                
            # Basic token format validation
            if len(line) < 20:
                self._log(f"Line {i}: Token too short, skipping", "WARNING")
                invalid_tokens.append(line)
                continue
                
            # Remove common prefixes if present
            clean_token = line.replace("oauth:", "").strip()
            
            if clean_token and clean_token not in tokens:
                tokens.append(clean_token)
                self._log(f"Loaded token {i}: {clean_token[:8]}...{clean_token[-4:]}", "DEBUG")
        
        self._log(f"Successfully loaded {len(tokens)} valid tokens", "SUCCESS")
        if invalid_tokens:
            self._log(f"Found {len(invalid_tokens)} invalid tokens", "WARNING")
            
        return tokens

    def get_user_id(self, username):
        """
        Fetch Twitch user ID from username using public GQL endpoint
        Returns: user_id (str) or False on failure
        """
        self._log(f"Resolving username: {username}", "INFO")
        
        headers = {
            "Client-Id": self.CLIENT_ID,
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "X-Device-Id": hashlib.md5(username.encode()).hexdigest()[:16]
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

        try:
            # Create new event loop for this synchronous call
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._fetch_direct(self.GQL_ENDPOINT, headers, payload))
            loop.close()
            
            if result and "data" in result[0] and result[0]["data"]["user"]:
                user_id = result[0]["data"]["user"]["id"]
                self._log(f"Resolved {username} -> ID: {user_id}", "SUCCESS")
                return user_id
            else:
                self._log(f"User {username} not found or API error", "ERROR")
                return False
                
        except Exception as e:
            self._log(f"ID resolution failed: {str(e)}", "ERROR")
            return False

    async def _fetch_direct(self, url, headers, payload, retry_count=0):
        """Direct HTTP request without proxies"""
        try:
            session = self._get_session()
            
            async with session.post(
                url,
                headers=headers,
                data=payload,
                ssl=False
            ) as response:
                
                self.request_stats['total_requests'] += 1
                
                if response.status == 200:
                    data = await response.json()
                    self.request_stats['successful'] += 1
                    return data
                elif response.status == 429:  # Rate limited
                    self._log(f"Rate limited, delaying... (Attempt {retry_count + 1})", "WARNING")
                    if retry_count < self.MAX_RETRIES:
                        await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                        return await self._fetch_direct(url, headers, payload, retry_count + 1)
                elif response.status == 401:  # Unauthorized
                    self._log("Token expired or invalid", "ERROR")
                    
                self.request_stats['failed'] += 1
                return None
                
        except asyncio.TimeoutError:
            self._log(f"Request timeout (Attempt {retry_count + 1})", "WARNING")
            if retry_count < self.MAX_RETRIES:
                await asyncio.sleep(1)
                return await self._fetch_direct(url, headers, payload, retry_count + 1)
        except Exception as e:
            self._log(f"Network error: {str(e)}", "ERROR")
            self.request_stats['failed'] += 1
            
        return None

    async def _execute_follow_direct(self, target_id, token, target_username, attempt=1):
        """
        Execute a single follow request directly to Twitch
        Returns: Boolean success status
        """
        token_hash = hashlib.md5(token.encode()).hexdigest()[:8]
        
        headers = {
            "Client-Id": self.CLIENT_ID,
            "Authorization": f"OAuth {token}",
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "X-Device-Id": token_hash,
            "Accept-Language": "en-US",
            "Origin": "https://www.twitch.tv",
            "Referer": f"https://www.twitch.tv/{target_username}",
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

        try:
            result = await self._fetch_direct(self.GQL_ENDPOINT, headers, payload)
            
            if result:
                # Check for success in response
                if (len(result) > 0 and 
                    "data" in result[0] and 
                    result[0]["data"]["followUser"]):
                    
                    self._log(f"Token {token_hash}: Successfully followed {target_username}", "SUCCESS")
                    return True
                elif "errors" in str(result).lower():
                    error_msg = str(result)[:200]
                    self._log(f"Token {token_hash}: API Error - {error_msg}", "ERROR")
            
            return False
            
        except Exception as e:
            self._log(f"Token {token_hash}: Follow execution failed - {str(e)}", "ERROR")
            if attempt < self.MAX_RETRIES:
                await asyncio.sleep(attempt * 0.5)
                return await self._execute_follow_direct(target_id, token, target_username, attempt + 1)
            return False

    async def _token_worker(self, target_id, token_queue, target_username, stats):
        """
        Worker coroutine that processes tokens from queue
        """
        while self.running and not token_queue.empty():
            try:
                token = await token_queue.get()
                
                if not token:
                    token_queue.task_done()
                    continue
                
                # Check if this token already followed
                with self.lock:
                    token_key = hashlib.md5(token.encode()).hexdigest()[:16]
                    if token_key in self.followed_records and target_id in self.followed_records[token_key]:
                        token_queue.task_done()
                        continue
                
                # Execute follow
                success = await self._execute_follow_direct(target_id, token, target_username)
                
                with self.lock:
                    if success:
                        stats["completed"] += 1
                        current = stats["completed"]
                        total_target = stats["target"]
                        
                        # Record the follow
                        if token_key not in self.followed_records:
                            self.followed_records[token_key] = []
                        self.followed_records[token_key].append(target_id)
                        
                        # Progress logging
                        progress_pct = (current / total_target) * 100
                        self._log(f"✅ Progress: {current}/{total_target} ({progress_pct:.1f}%) - {target_username}", "PROGRESS")
                        
                        # Update stats every 10 follows
                        if current % 10 == 0:
                            elapsed = time.time() - stats["start_time"]
                            rate = current / elapsed if elapsed > 0 else 0
                            self._log(f"📊 Stats: {rate:.2f} follows/sec, Elapsed: {elapsed:.1f}s", "STATS")
                    
                    stats["processed"] += 1
                
                # Rate limiting delay
                await asyncio.sleep(self.RATE_LIMIT_DELAY + random.uniform(0, 0.1))
                
                token_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log(f"Worker error: {str(e)}", "ERROR")
                token_queue.task_done()

    async def _run_follow_campaign(self, target_id, tokens, target_username, follow_count):
        """
        Main async follow campaign orchestrator
        """
        self._log(f"Starting follow campaign for {target_username}", "CAMPAIGN")
        self._log(f"Target ID: {target_id}, Tokens: {len(tokens)}, Target follows: {follow_count}", "CONFIG")
        
        # Initialize statistics
        stats = {
            "start_time": time.time(),
            "completed": 0,
            "processed": 0,
            "target": min(follow_count, len(tokens)),
            "active_workers": 0
        }
        
        # Create token queue
        token_queue = asyncio.Queue()
        for token in tokens[:follow_count]:
            await token_queue.put(token)
        
        # Create worker tasks
        workers = []
        num_workers = min(self.max_concurrent, follow_count, len(tokens))
        
        self._log(f"Spawning {num_workers} direct connection workers", "WORKERS")
        
        for i in range(num_workers):
            worker = asyncio.create_task(
                self._token_worker(target_id, token_queue, target_username, stats)
            )
            workers.append(worker)
            stats["active_workers"] += 1
            await asyncio.sleep(0.05)  # Stagger worker creation
        
        # Wait for queue to be processed
        await token_queue.join()
        
        # Cancel workers
        for worker in workers:
            worker.cancel()
        
        # Wait for all workers to finish
        await asyncio.gather(*workers, return_exceptions=True)
        
        # Final statistics
        elapsed = time.time() - stats["start_time"]
        success_rate = (stats["completed"] / stats["processed"] * 100) if stats["processed"] > 0 else 0
        
        self._log("=" * 50, "SUMMARY")
        self._log(f"🎯 CAMPAIGN COMPLETE: {target_username}", "SUCCESS")
        self._log(f"📈 Follows Successful: {stats['completed']}/{stats['target']}", "SUMMARY")
        self._log(f"⏱️  Time Elapsed: {elapsed:.2f} seconds", "SUMMARY")
        self._log(f"🚀 Average Rate: {stats['completed']/elapsed:.2f} follows/second" if elapsed > 0 else "Rate: N/A", "SUMMARY")
        self._log(f"📊 Success Rate: {success_rate:.1f}%", "SUMMARY")
        self._log(f"🔧 Workers Used: {num_workers}", "SUMMARY")
        self._log("=" * 50, "SUMMARY")
        
        return stats["completed"]

    def start_campaign(self, username, count):
        """
        Public method to start a follow campaign
        """
        if self.running:
            self._log("Bot is already running", "WARNING")
            return False
        
        self.running = True
        self.request_stats['start_time'] = time.time()
        
        # Start in background thread
        threading.Thread(
            target=self._campaign_thread,
            args=(username, count),
            daemon=True,
            name=f"Campaign-{username}"
        ).start()
        
        return True

    def _campaign_thread(self, username, count):
        """
        Thread wrapper for campaign execution
        """
        try:
            # Resolve username to ID
            self._log(f"Starting campaign thread for: @{username}", "THREAD")
            
            user_id = self.get_user_id(username)
            if not user_id:
                self._log(f"Failed to resolve username: {username}", "ERROR")
                self.running = False
                return
            
            # Load tokens
            tokens = self._load_tokens()
            if not tokens:
                self._log("No valid tokens available", "ERROR")
                self.running = False
                return
            
            # Adjust count based on available tokens
            actual_count = min(count, len(tokens))
            if actual_count < count:
                self._log(f"Adjusted target from {count} to {actual_count} (token limit)", "WARNING")
            
            # Run async campaign
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(
                    self._run_follow_campaign(user_id, tokens, username, actual_count)
                )
                self._log(f"Campaign finished with {result} successful follows", "COMPLETE")
            finally:
                loop.close()
                
        except Exception as e:
            self._log(f"Campaign thread crashed: {str(e)}", "CRITICAL")
            import traceback
            traceback.print_exc()
        finally:
            self.running = False
            self._log("Campaign thread terminated", "THREAD")

    def stop(self):
        """Stop the bot immediately"""
        self.running = False
        self._log("Bot stop command received", "SHUTDOWN")
        
        # Close all sessions
        for session in self.session_cache.values():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(session.close())
                loop.close()
            except:
                pass
        
        self.session_cache.clear()
        
        # Print final stats
        if self.request_stats['start_time']:
            elapsed = time.time() - self.request_stats['start_time']
            self._log(f"Final Stats: {self.request_stats['successful']} successful, "
                     f"{self.request_stats['failed']} failed, "
                     f"{self.request_stats['total_requests']} total requests, "
                     f"{elapsed:.1f}s elapsed", "FINAL")

    def get_status(self):
        """Get current bot status"""
        status = {
            "running": self.running,
            "followed_count": sum(len(v) for v in self.followed_records.values()),
            "unique_tokens_used": len(self.followed_records),
            "request_stats": self.request_stats.copy()
        }
        
        if self.request_stats['start_time']:
            status["elapsed_seconds"] = time.time() - self.request_stats['start_time']
            
        return status


# ============================================================================
# ENHANCED COMMAND LINE INTERFACE
# ============================================================================

class InteractiveCLI:
    """Enhanced command-line interface for the bot"""
    
    def __init__(self):
        self.bot = TwitchFollowerDirect(self._cli_log)
        self.commands = {
            "help": self._show_help,
            "start": self._start_campaign,
            "stop": self._stop_bot,
            "status": self._show_status,
            "stats": self._show_stats,
            "clear": self._clear_screen,
            "exit": self._exit_program,
            "test": self._test_connection,
        }
        
    def _cli_log(self, message):
        """CLI-specific logging"""
        print(message)
    
    def _show_help(self):
        """Display available commands"""
        help_text = """
        ╔══════════════════════════════════════════════════════════╗
        ║              TWITCH FOLLOW BOT - COMMANDS                ║
        ╠══════════════════════════════════════════════════════════╣
        ║  start    - Launch a follow campaign                     ║
        ║  stop     - Stop current campaign                        ║
        ║  status   - Show current bot status                      ║
        ║  stats    - Display detailed statistics                  ║
        ║  test     - Test token and connection                    ║
        ║  clear    - Clear terminal screen                        ║
        ║  exit     - Exit the program                             ║
        ║  help     - Show this help menu                          ║
        ╚══════════════════════════════════════════════════════════╝
        """
        print(help_text)
    
    def _start_campaign(self):
        """Start a new follow campaign"""
        if self.bot.running:
            print("❌ Bot is already running. Use 'stop' first.")
            return
            
        print("\n" + "="*60)
        print("🚀 START NEW FOLLOW CAMPAIGN")
        print("="*60)
        
        username = input("Target Twitch username: ").strip().lower()
        if not username:
            print("❌ Username cannot be empty")
            return
            
        try:
            count = int(input("Number of follows to attempt: ").strip())
            if count <= 0:
                print("❌ Count must be positive")
                return
            if count > 1000:
                print("⚠️  Warning: Large counts may trigger rate limits")
                confirm = input("Continue? (y/N): ").lower()
                if confirm != 'y':
                    return
        except ValueError:
            print("❌ Invalid number")
            return
        
        print(f"\n📍 Target: @{username}")
        print(f"🎯 Follows: {count}")
        print("⏳ Starting campaign...")
        
        self.bot.start_campaign(username, count)
        
        # Monitor progress
        self._monitor_progress()
    
    def _monitor_progress(self):
        """Monitor campaign progress"""
        print("\n📊 Monitoring progress... (Ctrl+C to interrupt)")
        try:
            while self.bot.running:
                status = self.bot.get_status()
                elapsed = status.get('elapsed_seconds', 0)
                
                print(f"\r⏱️  Elapsed: {elapsed:.1f}s | ✅ Follows: {status['followed_count']} | "
                      f"📊 Success: {status['request_stats']['successful']} | "
                      f"❌ Failed: {status['request_stats']['failed']}", end="")
                
                time.sleep(1)
            print("\n✅ Campaign completed!")
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Monitoring interrupted")
    
    def _stop_bot(self):
        """Stop the bot"""
        if not self.bot.running:
            print("❌ Bot is not running")
            return
            
        print("🛑 Stopping bot...")
        self.bot.stop()
        time.sleep(1)
        print("✅ Bot stopped")
    
    def _show_status(self):
        """Display current bot status"""
        status = self.bot.get_status()
        
        print("\n" + "="*50)
        print("🤖 BOT STATUS")
        print("="*50)
        print(f"Status:       {'🟢 RUNNING' if status['running'] else '🔴 STOPPED'}")
        print(f"Total Follows: {status['followed_count']}")
        print(f"Tokens Used:   {status['unique_tokens_used']}")
        
        if 'elapsed_seconds' in status:
            print(f"Elapsed Time:  {status['elapsed_seconds']:.1f}s")
            
        stats = status['request_stats']
        print(f"\n📊 REQUEST STATISTICS")
        print(f"Total Requests: {stats['total_requests']}")
        print(f"Successful:     {stats['successful']}")
        print(f"Failed:         {stats['failed']}")
        
        if stats['total_requests'] > 0:
            success_rate = (stats['successful'] / stats['total_requests']) * 100
            print(f"Success Rate:   {success_rate:.1f}%")
        print("="*50)
    
    def _show_stats(self):
        """Show detailed statistics"""
        self._show_status()
        
        # Additional stats could be added here
        if os.path.exists("bot_operation.log"):
            with open("bot_operation.log", "r", encoding="utf-8") as f:
                lines = f.readlines()
                recent = lines[-20:] if len(lines) >= 20 else lines
                
            print("\n📝 RECENT LOG ENTRIES (last 20)")
            print("-"*50)
            for line in recent:
                print(line.strip())
    
    def _clear_screen(self):
        """Clear terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print("🧹 Screen cleared")
    
    def _exit_program(self):
        """Exit the program"""
        if self.bot.running:
            print("⚠️  Bot is still running. Stopping...")
            self.bot.stop()
            time.sleep(2)
        
        print("\n👋 Goodbye!")
        sys.exit(0)
    
    def _test_connection(self):
        """Test token connectivity"""
        tokens = self.bot._load_tokens()
        if not tokens:
            print("❌ No tokens found in tokens.txt")
            return
            
        print(f"\n🔍 Testing {len(tokens)} tokens...")
        
        # Quick connectivity test
        test_user = "twitch"
        user_id = self.bot.get_user_id(test_user)
        
        if user_id:
            print(f"✅ Connection test passed - Resolved @{test_user} to ID: {user_id}")
            print(f"✅ Tokens loaded: {len(tokens)}")
        else:
            print("❌ Connection test failed")
    
    def run(self):
        """Main CLI loop"""
        self._clear_screen()
        
        print("""
        ╔══════════════════════════════════════════════════════╗
        ║      🚀 TWITCH FOLLOW BOT v2.0 - PROXY-FREE         ║
        ║                 DIRECT CONNECTION EDITION           ║
        ╠══════════════════════════════════════════════════════╣
        ║  ⚠️  WARNING: FOR EDUCATIONAL PURPOSES ONLY         ║
        ║  ⚠️  USE RESPONSIBLY AND AT YOUR OWN RISK           ║
        ╚══════════════════════════════════════════════════════╝
        """)
        
        # Check for required files
        if not os.path.exists("tokens.txt"):
            print("❌ ERROR: tokens.txt not found!")
            print("Create tokens.txt with one OAuth token per line")
            print("Tokens format: 'oauth:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' or just the token")
            return
        
        print(f"✅ Found tokens.txt")
        print(f"📁 Log file: bot_operation.log")
        print(f"\n📋 Type 'help' for commands\n")
        
        # Main command loop
        while True:
            try:
                command = input("🤖 BOT> ").strip().lower()
                
                if command in self.commands:
                    self.commands[command]()
                elif command:
                    print(f"❌ Unknown command: {command}")
                    print("Type 'help' for available commands")
                    
            except KeyboardInterrupt:
                print("\n\n⚠️  Interrupted. Type 'exit' to quit or 'help' for commands")
            except Exception as e:
                print(f"❌ Error: {str(e)}")


# ============================================================================
# MAIN EXECUTION BLOCK
# ============================================================================

if __name__ == "__main__":
    
    # Create necessary files if they don't exist
    if not os.path.exists("tokens.txt"):
        with open("tokens.txt", "w", encoding="utf-8") as f:
            f.write("# Add your Twitch OAuth tokens here, one per line\n")
            f.write("# Format: oauth:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n")
            f.write("# Or just: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n")
            f.write("# Get tokens from: https://twitchtokengenerator.com\n")
    
    # Start interactive CLI
    cli = InteractiveCLI()
    cli.run()


# ============================================================================
# CONFIGURATION & SETUP INSTRUCTIONS
# ============================================================================

"""
🔧 SETUP INSTRUCTIONS:

1. TOKEN ACQUISITION:
   - Visit: https://twitchtokengenerator.com
   - Select "Custom Scope"
   - Add scope: "user:edit:follows"
   - Generate tokens
   - Copy tokens to tokens.txt (one per line)

2. DEPENDENCIES INSTALLATION:
   pip install aiohttp

3. USAGE:
   - Run: python twitch_follower_direct.py
   - Type 'start' to begin campaign
   - Follow on-screen prompts

4. SAFETY FEATURES:
   - Rate limiting built-in
   - Token reuse prevention
   - Comprehensive logging
   - Error handling and retries

5. PERFORMANCE TIPS:
   - 50-100 tokens optimal for most connections
   - Reduce max_concurrent if experiencing timeouts
   - Monitor bot_operation.log for detailed info

⚠️ LEGAL DISCLAIMER:
   This tool is for educational purposes only.
   Using automated tools to manipulate Twitch follows violates Twitch's Terms of Service.
   Use at your own risk. The author assumes no responsibility for misuse.

🔍 TROUBLESHOOTING:
   - No follows: Check tokens are valid and have correct scope
   - Rate limited: Increase RATE_LIMIT_DELAY
   - Timeouts: Decrease max_concurrent workers
   - Errors: Check bot_operation.log for details
"""
