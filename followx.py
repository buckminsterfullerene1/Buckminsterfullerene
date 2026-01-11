#!/usr/bin/env python3
"""
TWITCH FOLLOW BOT v3.0 - PROXYLESS MASTER EDITION
Optimized for speed, reliability, and stealth
"""

import json
import os
import random
import asyncio
import aiohttp
import threading
import time
import sys
from typing import List, Dict, Set, Optional
from dataclasses import dataclass
from datetime import datetime
import colorama
from colorama import Fore, Style, Back

# Initialize colorama for cross-platform colors
colorama.init(autoreset=True)

# ============================================================================
# DATA STRUCTURES & CONFIGURATION
# ============================================================================

@dataclass
class BotStats:
    """Comprehensive statistics tracker"""
    follows_sent: int = 0
    follows_failed: int = 0
    tokens_used: Set[str] = None
    start_time: datetime = None
    active_workers: int = 0
    
    def __post_init__(self):
        self.tokens_used = set()
        self.start_time = datetime.now()
    
    @property
    def success_rate(self) -> float:
        if self.follows_sent + self.follows_failed == 0:
            return 0.0
        return (self.follows_sent / (self.follows_sent + self.follows_failed)) * 100
    
    @property
    def elapsed_time(self) -> str:
        if not self.start_time:
            return "0:00:00"
        delta = datetime.now() - self.start_time
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

# ============================================================================
# CORE BOT CLASS
# ============================================================================

class TwitchFollowBot:
    """
    High-performance Twitch follow bot without proxy dependency
    Uses modern aiohttp with proper connection pooling and rate limiting
    """
    
    # Twitch API Constants
    TWITCH_GQL_URL = "https://gql.twitch.tv/gql"
    CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # Public Twitch web client ID
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # GQL Operation Hashes (Updated as of 2024)
    GQL_OPERATIONS = {
        "get_user_id": {
            "hash": "94e82a7b1e3c21e186daa73ee2afc4b8f23bade1fbbff6fe8ac133f50a2f58ca",
            "operation": "GetIDFromLogin"
        },
        "follow_user": {
            "hash": "cd112d9483ede85fa0da514a5657141c24396efbc7bac0ea3623e839206573b8",
            "operation": "FollowUserMutation"
        },
        "unfollow_user": {
            "hash": "f7dae976ebf41c755ae2d758546bfd176b4eeb856656098bb40e0a672ca0d880",
            "operation": "FollowButton_UnfollowUser"
        }
    }
    
    def __init__(self, verbose: bool = True):
        """
        Initialize the bot
        
        Args:
            verbose: Enable detailed logging
        """
        self.verbose = verbose
        self.stats = BotStats()
        self.running = False
        self._lock = threading.Lock()
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limit_delay = 0.1  # Base delay between requests
        self._max_concurrent = 50     # Maximum concurrent requests
        self._semaphore: Optional[asyncio.Semaphore] = None
        
    # ============================================================================
    # LOGGING UTILITIES
    # ============================================================================
    
    def _log(self, message: str, level: str = "INFO"):
        """Enhanced logging with colors and timestamps"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        color_map = {
            "INFO": Fore.CYAN,
            "SUCCESS": Fore.GREEN + Style.BRIGHT,
            "WARNING": Fore.YELLOW + Style.BRIGHT,
            "ERROR": Fore.RED + Style.BRIGHT,
            "DEBUG": Fore.MAGENTA,
            "STATUS": Fore.BLUE + Style.BRIGHT
        }
        
        color = color_map.get(level, Fore.WHITE)
        level_display = f"[{level}]"
        
        if level == "SUCCESS":
            symbol = "✅"
        elif level == "ERROR":
            symbol = "❌"
        elif level == "WARNING":
            symbol = "⚠️"
        else:
            symbol = "📝"
        
        formatted_message = f"{Fore.WHITE}[{timestamp}]{color} {symbol} {level_display:10} {message}{Style.RESET_ALL}"
        
        if self.verbose or level in ["ERROR", "SUCCESS", "STATUS"]:
            print(formatted_message)
            
            # Update console title with stats
            if sys.platform == "win32":
                os.system(f"title TwitchBot :: Sent: {self.stats.follows_sent} | Failed: {self.stats.follows_failed} | Rate: {self.stats.success_rate:.1f}%")
    
    # ============================================================================
    # TOKEN MANAGEMENT
    # ============================================================================
    
    def load_tokens(self, filepath: str = "tokens.txt") -> List[str]:
        """
        Load OAuth tokens from file with validation
        
        Args:
            filepath: Path to tokens file
            
        Returns:
            List of valid tokens
        """
        tokens = []
        
        if not os.path.exists(filepath):
            self._log(f"Tokens file not found: {filepath}", "ERROR")
            return tokens
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    # Basic token validation
                    if len(line) < 30:
                        self._log(f"Invalid token on line {line_num} (too short)", "WARNING")
                        continue
                    
                    tokens.append(line)
                    
        except Exception as e:
            self._log(f"Failed to load tokens: {e}", "ERROR")
            
        self._log(f"Loaded {len(tokens)} valid tokens from {filepath}", "SUCCESS")
        return tokens
    
    def save_failed_tokens(self, tokens: List[str], filepath: str = "failed_tokens.txt"):
        """Save failed tokens for later analysis"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                for token in tokens:
                    f.write(f"{token}\n")
            self._log(f"Saved {len(tokens)} failed tokens to {filepath}", "WARNING")
        except Exception as e:
            self._log(f"Failed to save failed tokens: {e}", "ERROR")
    
    # ============================================================================
    # TWITCH API COMMUNICATION
    # ============================================================================
    
    async def _create_session(self):
        """Create a shared aiohttp session with optimal settings"""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=self._max_concurrent,
                ttl_dns_cache=300,
                force_close=False,
                enable_cleanup_closed=True
            )
            
            timeout = aiohttp.ClientTimeout(
                total=30,
                connect=10,
                sock_read=20
            )
            
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    'User-Agent': self.USER_AGENT,
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                }
            )
            
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
    
    async def _make_gql_request(self, operation: str, variables: Dict, token: str = None) -> Dict:
        """
        Make a GraphQL request to Twitch API
        
        Args:
            operation: GQL operation name
            variables: Variables for the operation
            token: Optional OAuth token for authenticated requests
            
        Returns:
            JSON response from Twitch
        """
        await self._create_session()
        
        async with self._semaphore:
            # Build headers
            headers = {
                'Client-ID': self.CLIENT_ID,
                'Content-Type': 'application/json',
                'User-Agent': self.USER_AGENT,
            }
            
            if token:
                headers['Authorization'] = f'OAuth {token}'
            
            # Build payload
            op_config = self.GQL_OPERATIONS.get(operation)
            if not op_config:
                raise ValueError(f"Unknown operation: {operation}")
            
            payload = [{
                "operationName": op_config["operation"],
                "variables": variables,
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": op_config["hash"]
                    }
                }
            }]
            
            # Add jitter to avoid rate limiting
            await asyncio.sleep(random.uniform(0.05, 0.15))
            
            try:
                async with self._session.post(
                    self.TWITCH_GQL_URL,
                    json=payload,
                    headers=headers,
                    ssl=False
                ) as response:
                    
                    response_text = await response.text()
                    
                    if response.status == 200:
                        try:
                            data = json.loads(response_text)
                            return data
                        except json.JSONDecodeError:
                            self._log(f"JSON decode error: {response_text[:100]}", "ERROR")
                            return {"errors": ["Invalid JSON response"]}
                    elif response.status == 429:
                        self._log("Rate limited! Increasing delay...", "WARNING")
                        self._rate_limit_delay = min(self._rate_limit_delay * 1.5, 2.0)
                        await asyncio.sleep(random.uniform(1.0, 3.0))
                        return {"errors": ["Rate limited"]}
                    else:
                        self._log(f"HTTP {response.status}: {response_text[:200]}", "ERROR")
                        return {"errors": [f"HTTP {response.status}"]}
                        
            except aiohttp.ClientError as e:
                self._log(f"Network error: {e}", "ERROR")
                return {"errors": [str(e)]}
            except Exception as e:
                self._log(f"Unexpected error: {e}", "ERROR")
                return {"errors": [str(e)]}
    
    async def get_user_id(self, username: str) -> Optional[str]:
        """
        Get Twitch user ID from username
        
        Args:
            username: Twitch username
            
        Returns:
            User ID or None if not found
        """
        self._log(f"Fetching ID for user: {username}", "INFO")
        
        response = await self._make_gql_request(
            operation="get_user_id",
            variables={"login": username.lower().strip()}
        )
        
        if response and isinstance(response, list):
            user_data = response[0].get("data", {}).get("user", {})
            user_id = user_data.get("id")
            
            if user_id:
                self._log(f"Found ID for {username}: {user_id}", "SUCCESS")
                return user_id
            else:
                self._log(f"User not found: {username}", "ERROR")
                return None
        
        self._log(f"Failed to get ID for {username}", "ERROR")
        return None
    
    async def follow_user(self, target_id: str, token: str) -> bool:
        """
        Follow a user using provided token
        
        Args:
            target_id: Twitch user ID to follow
            token: OAuth token
            
        Returns:
            Success status
        """
        response = await self._make_gql_request(
            operation="follow_user",
            variables={
                "targetId": target_id,
                "disableNotifications": False
            },
            token=token
        )
        
        if response and isinstance(response, list):
            data = response[0]
            
            # Check for errors
            if data.get("errors"):
                error_msg = data["errors"][0].get("message", "Unknown error")
                self._log(f"Follow failed: {error_msg}", "ERROR")
                return False
            
            # Check for success indicators
            follow_result = data.get("data", {}).get("followUser", {})
            if follow_result.get("follow") or follow_result.get("id"):
                return True
            
            # Alternative success check
            if "error" not in str(data).lower():
                return True
        
        return False
    
    async def unfollow_user(self, target_id: str, token: str) -> bool:
        """
        Unfollow a user using provided token
        
        Args:
            target_id: Twitch user ID to unfollow
            token: OAuth token
            
        Returns:
            Success status
        """
        response = await self._make_gql_request(
            operation="unfollow_user",
            variables={"input": {"targetID": target_id}},
            token=token
        )
        
        if response and isinstance(response, list):
            data = response[0]
            
            if data.get("errors"):
                return False
            
            unfollow_result = data.get("data", {}).get("unfollowUser", {})
            if unfollow_result:
                return True
            
            if "error" not in str(data).lower():
                return True
        
        return False
    
    # ============================================================================
    # WORKER SYSTEM
    # ============================================================================
    
    async def _follow_worker(self, 
                           target_id: str, 
                           tokens: List[str], 
                           target_username: str,
                           max_follows: int,
                           action: str = "follow") -> None:
        """
        Worker coroutine that processes follow/unfollow requests
        
        Args:
            target_id: User ID to target
            tokens: List of tokens to use
            target_username: Target username for logging
            max_follows: Maximum number of actions to perform
            action: "follow" or "unfollow"
        """
        worker_id = threading.current_thread().ident % 1000
        
        with self._lock:
            self.stats.active_workers += 1
        
        self._log(f"Worker {worker_id} started for {action} action", "DEBUG")
        
        token_index = 0
        processed_tokens = set()
        
        while self.running and self.stats.follows_sent < max_follows:
            # Select token
            if token_index >= len(tokens):
                token_index = 0
                if len(processed_tokens) == len(tokens):
                    # All tokens used
                    break
            
            token = tokens[token_index]
            token_index += 1
            
            # Skip if token already processed in this session
            if token in processed_tokens:
                await asyncio.sleep(0.05)
                continue
            
            # Perform action
            success = False
            if action == "follow":
                success = await self.follow_user(target_id, token)
            else:
                success = await self.unfollow_user(target_id, token)
            
            # Update stats
            with self._lock:
                if success:
                    self.stats.follows_sent += 1
                    processed_tokens.add(token)
                    self.stats.tokens_used.add(token)
                    
                    # Status update
                    current = self.stats.follows_sent
                    if current % 10 == 0 or current == max_follows:
                        self._log(
                            f"{action.capitalize()} {current}/{max_follows} "
                            f"({self.stats.success_rate:.1f}% success) | "
                            f"Elapsed: {self.stats.elapsed_time}",
                            "STATUS"
                        )
                else:
                    self.stats.follows_failed += 1
            
            # Adaptive delay based on success rate
            current_rate = self.stats.success_rate
            if current_rate < 50:
                delay = random.uniform(0.5, 1.5)
            elif current_rate < 80:
                delay = random.uniform(0.2, 0.5)
            else:
                delay = random.uniform(0.05, 0.2)
            
            await asyncio.sleep(delay)
        
        with self._lock:
            self.stats.active_workers -= 1
        
        self._log(f"Worker {worker_id} finished", "DEBUG")
    
    # ============================================================================
    # MAIN CONTROL METHODS
    # ============================================================================
    
    async def run_async(self, 
                       username: str, 
                       count: int, 
                       action: str = "follow",
                       max_workers: int = 20) -> None:
        """
        Main async entry point
        
        Args:
            username: Target Twitch username
            count: Number of actions to perform
            action: "follow" or "unfollow"
            max_workers: Maximum concurrent workers
        """
        if self.running:
            self._log("Bot is already running!", "WARNING")
            return
        
        self.running = True
        self.stats = BotStats()  # Reset stats
        
        # Display banner
        self._show_banner(username, count, action)
        
        # Load tokens
        tokens = self.load_tokens()
        if not tokens:
            self._log("No valid tokens found. Operation aborted.", "ERROR")
            self.running = False
            return
        
        # Get user ID
        self._log(f"Resolving user ID for '{username}'...", "INFO")
        user_id = await self.get_user_id(username)
        
        if not user_id:
            self._log(f"Failed to resolve user '{username}'. Check spelling.", "ERROR")
            self.running = False
            return
        
        # Calculate optimal worker count
        worker_count = min(max_workers, count, len(tokens))
        actions_per_worker = max(1, count // worker_count)
        
        self._log(f"Starting {worker_count} workers for {action} operation", "INFO")
        self._log(f"Target: {username} (ID: {user_id})", "INFO")
        self._log(f"Goal: {count} {action}s | Tokens: {len(tokens)}", "INFO")
        
        # Create worker tasks
        tasks = []
        for i in range(worker_count):
            task = asyncio.create_task(
                self._follow_worker(
                    target_id=user_id,
                    tokens=tokens,
                    target_username=username,
                    max_follows=actions_per_worker,
                    action=action
                )
            )
            tasks.append(task)
            await asyncio.sleep(0.01)  # Stagger startup
        
        # Wait for completion or interrupt
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            self._log("Operation cancelled", "WARNING")
        finally:
            self.running = False
        
        # Final statistics
        self._show_final_stats()
    
    def run(self, username: str, count: int, action: str = "follow") -> None:
        """
        Synchronous wrapper for running the bot
        
        Args:
            username: Target Twitch username
            count: Number of actions to perform
            action: "follow" or "unfollow"
        """
        try:
            asyncio.run(self.run_async(username, count, action))
        except KeyboardInterrupt:
            self._log("\nBot stopped by user", "WARNING")
            self.running = False
        except Exception as e:
            self._log(f"Fatal error: {e}", "ERROR")
            import traceback
            traceback.print_exc()
    
    # ============================================================================
    # UI & DISPLAY METHODS
    # ============================================================================
    
    def _show_banner(self, username: str, count: int, action: str):
        """Display fancy banner"""
        banner = f"""
        {Fore.CYAN}{Style.BRIGHT}
        ╔══════════════════════════════════════════════════════════╗
        ║                                                          ║
        ║                {Fore.MAGENTA}TWITCH BOT v3.0 - PROXYLESS MODE{Fore.CYAN}           ║
        ║                                                          ║
        ║    {Fore.YELLOW}Target:    {Fore.WHITE}{username:<45}{Fore.CYAN} ║
        ║    {Fore.YELLOW}Action:    {Fore.WHITE}{action.upper():<45}{Fore.CYAN} ║
        ║    {Fore.YELLOW}Quantity:  {Fore.WHITE}{count:<45}{Fore.CYAN} ║
        ║    {Fore.YELLOW}Mode:      {Fore.WHITE}DIRECT API (No Proxies){Fore.CYAN}           ║
        ║                                                          ║
        ╚══════════════════════════════════════════════════════════╝
        {Style.RESET_ALL}
        """
        print(banner)
    
    def _show_final_stats(self):
        """Display final statistics"""
        stats = self.stats
        total = stats.follows_sent + stats.follows_failed
        
        if total == 0:
            self._log("No actions performed", "WARNING")
            return
        
        report = f"""
        {Fore.GREEN}{Style.BRIGHT}
        ╔══════════════════════════════════════════════════════════╗
        ║                     OPERATION COMPLETE                   ║
        ╠══════════════════════════════════════════════════════════╣
        ║                                                          ║
        ║    {Fore.CYAN}Total Attempts:{Fore.WHITE} {total:>36}          {Fore.GREEN}║
        ║    {Fore.CYAN}Successful:{Fore.WHITE} {stats.follows_sent:>39}          {Fore.GREEN}║
        ║    {Fore.CYAN}Failed:{Fore.WHITE} {stats.follows_failed:>42}          {Fore.GREEN}║
        ║    {Fore.CYAN}Success Rate:{Fore.WHITE} {stats.success_rate:>7.2f}%{Fore.GREEN}                 ║
        ║    {Fore.CYAN}Tokens Used:{Fore.WHITE} {len(stats.tokens_used):>38}          {Fore.GREEN}║
        ║    {Fore.CYAN}Elapsed Time:{Fore.WHITE} {stats.elapsed_time:>36}          {Fore.GREEN}║
        ║                                                          ║
        ╚══════════════════════════════════════════════════════════╝
        {Style.RESET_ALL}
        """
        print(report)
        
        # Save session report
        self._save_session_report()

    def _save_session_report(self):
        """Save detailed session report to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"session_report_{timestamp}.txt"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write("TWITCH BOT SESSION REPORT\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"Session Time: {datetime.now()}\n")
                f.write(f"Total Actions: {self.stats.follows_sent + self.stats.follows_failed}\n")
                f.write(f"Successful: {self.stats.follows_sent}\n")
                f.write(f"Failed: {self.stats.follows_failed}\n")
                f.write(f"Success Rate: {self.stats.success_rate:.2f}%\n")
                f.write(f"Tokens Used: {len(self.stats.tokens_used)}\n")
                f.write(f"Elapsed Time: {self.stats.elapsed_time}\n")
                f.write("\n" + "=" * 60 + "\n")
            
            self._log(f"Session report saved to {filename}", "INFO")
        except Exception as e:
            self._log(f"Failed to save report: {e}", "ERROR")

# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def interactive_menu():
    """Interactive command-line interface"""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}╔══════════════════════════════════════════════════╗")
    print(f"║         TWITCH FOLLOW BOT v3.0 - MENU           ║")
    print(f"╚══════════════════════════════════════════════════╝{Style.RESET_ALL}\n")
    
    print(f"{Fore.YELLOW}[1]{Fore.WHITE} Follow User")
    print(f"{Fore.YELLOW}[2]{Fore.WHITE} Unfollow User")
    print(f"{Fore.YELLOW}[3]{Fore.WHITE} Validate Tokens")
    print(f"{Fore.YELLOW}[4]{Fore.WHITE} Check User ID")
    print(f"{Fore.YELLOW}[5]{Fore.WHITE} Exit\n")
    
    try:
        choice = input(f"{Fore.GREEN}Select option {Fore.YELLOW}(1-5){Fore.GREEN}: {Style.RESET_ALL}").strip()
        
        if choice == "1":
            username = input(f"{Fore.CYAN}Target username: {Style.RESET_ALL}").strip()
            count = input(f"{Fore.CYAN}Number of follows: {Style.RESET_ALL}").strip()
            
            try:
                count = int(count)
                if count <= 0:
                    raise ValueError
            except ValueError:
                print(f"{Fore.RED}Invalid number! Using default: 10{Style.RESET_ALL}")
                count = 10
            
            bot = TwitchFollowBot(verbose=True)
            bot.run(username, count, "follow")
            
        elif choice == "2":
            username = input(f"{Fore.CYAN}Target username: {Style.RESET_ALL}").strip()
            count = input(f"{Fore.CYAN}Number of unfollows: {Style.RESET_ALL}").strip()
            
            try:
                count = int(count)
            except ValueError:
                print(f"{Fore.RED}Invalid number!{Style.RESET_ALL}")
                return
            
            bot = TwitchFollowBot(verbose=True)
            bot.run(username, count, "unfollow")
            
        elif choice == "3":
            bot = TwitchFollowBot(verbose=True)
            tokens = bot.load_tokens()
            print(f"{Fore.GREEN}Loaded {len(tokens)} tokens{Style.RESET_ALL}")
            
        elif choice == "4":
            username = input(f"{Fore.CYAN}Username to check: {Style.RESET_ALL}").strip()
            
            async def check_id():
                bot = TwitchFollowBot(verbose=True)
                user_id = await bot.get_user_id(username)
                if user_id:
                    print(f"{Fore.GREEN}User ID for {username}: {user_id}{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}User not found{Style.RESET_ALL}")
            
            asyncio.run(check_id())
            
        elif choice == "5":
            print(f"{Fore.YELLOW}Goodbye!{Style.RESET_ALL}")
            return
            
        else:
            print(f"{Fore.RED}Invalid choice!{Style.RESET_ALL}")
            
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Operation cancelled by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point with argument parsing"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Twitch Follow Bot v3.0")
    parser.add_argument("--username", "-u", help="Target username")
    parser.add_argument("--count", "-c", type=int, default=10, help="Number of actions")
    parser.add_argument("--action", "-a", choices=["follow", "unfollow"], default="follow", help="Action to perform")
    parser.add_argument("--workers", "-w", type=int, default=20, help="Max concurrent workers")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode (less output)")
    
    args = parser.parse_args()
    
    if args.interactive or (not args.username and not args.quiet):
        interactive_menu()
        return
    
    if not args.username:
        print(f"{Fore.RED}Error: Username is required!{Style.RESET_ALL}")
        parser.print_help()
        return
    
    # Run in automated mode
    bot = TwitchFollowBot(verbose=not args.quiet)
    
    if args.quiet:
        # Minimal output for scripting
        print(f"Starting {args.action} operation for {args.username}...")
    
    try:
        asyncio.run(bot.run_async(
            username=args.username,
            count=args.count,
            action=args.action,
            max_workers=args.workers
        ))
    except KeyboardInterrupt:
        if not args.quiet:
            print(f"\n{Fore.YELLOW}Bot stopped{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
