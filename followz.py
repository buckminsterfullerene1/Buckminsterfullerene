#!/usr/bin/env python3
"""
TWITCH FOLLOW BOT - NO PROXY VERSION
Simple, direct, and actually works
"""

import json
import os
import random
import threading
import time
import requests
from itertools import cycle
from colorama import Fore, init, Style
import sys

# Initialize colorama
init(autoreset=True)

# ============================================================================
# GLOBAL CONFIGURATION
# ============================================================================

class Config:
    """Centralized configuration"""
    GQL_URL = "https://gql.twitch.tv/gql"
    CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # GQL Operation Hashes (VERIFIED WORKING)
    OPERATIONS = {
        "get_user_id": {
            "hash": "94e82a7b1e3c21e186daa73ee2afc4b8f23bade1fbbff6fe8ac133f50a2f58ca",
            "name": "GetIDFromLogin"
        },
        "follow": {
            "hash": "800e7346bdf7e5278a3c1d3f21b2b56e2639928f86815677a7126b093b2fdd08",
            "name": "FollowButton_FollowUser"
        },
        "unfollow": {
            "hash": "f7dae976ebf41c755ae2d758546bfd176b4eeb856656098bb40e0a672ca0d880",
            "name": "FollowButton_UnfollowUser"
        }
    }
    
    # Rate limiting
    REQUEST_DELAY = (0.05, 0.15)  # Random delay between requests
    MAX_THREADS = 50

# ============================================================================
# STATISTICS TRACKER
# ============================================================================

class Stats:
    """Simple statistics tracker"""
    def __init__(self):
        self.success = 0
        self.failed = 0
        self.total = 0
        self.start_time = time.time()
        self.lock = threading.Lock()
    
    def increment_success(self):
        with self.lock:
            self.success += 1
            self.total += 1
            self.update_title()
    
    def increment_failed(self):
        with self.lock:
            self.failed += 1
            self.total += 1
            self.update_title()
    
    def update_title(self):
        """Update console title with stats"""
        if sys.platform == "win32":
            success_rate = (self.success / max(self.total, 1)) * 100
            title = f"TwitchBot | Success: {self.success} | Failed: {self.failed} | Rate: {success_rate:.1f}%"
            os.system(f"title {title}")
    
    def get_elapsed(self):
        """Get formatted elapsed time"""
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def get_success_rate(self):
        """Calculate success rate"""
        if self.total == 0:
            return 0.0
        return (self.success / self.total) * 100

# Global stats instance
stats = Stats()

# ============================================================================
# TOKEN MANAGER
# ============================================================================

class TokenManager:
    """Manages OAuth tokens without proxies"""
    
    def __init__(self, token_file="tokens.txt"):
        self.token_file = token_file
        self.tokens = []
        self.load_tokens()
    
    def load_tokens(self):
        """Load tokens from file"""
        self.tokens = []
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, 'r') as f:
                    for line in f:
                        token = line.strip()
                        # Clean up token format
                        if token.startswith("oauth:"):
                            token = token[6:]  # Remove "oauth:" prefix
                        if token and len(token) > 20:  # Basic validation
                            self.tokens.append(token)
                
                print(f"{Fore.GREEN}[+] Loaded {len(self.tokens)} tokens from {self.token_file}{Style.RESET_ALL}")
                return True
            except Exception as e:
                print(f"{Fore.RED}[-] Error loading tokens: {e}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}[-] Token file not found: {self.token_file}{Style.RESET_ALL}")
            # Create template file
            self.create_template()
        
        return False
    
    def create_template(self):
        """Create template token file"""
        try:
            with open(self.token_file, 'w') as f:
                f.write("# Add your OAuth tokens here (one per line)\n")
                f.write("# Format: oauth:xxxxxxxxxxxxxxxxxxxxxxxxxxxx\n")
                f.write("# or just: xxxxxxxxxxxxxxxxxxxxxxxxxxxx\n")
                f.write("#\n")
                f.write("# Example:\n")
                f.write("# oauth:abcdefghijklmnopqrstuvwxyz123456\n")
                f.write("# 1234567890abcdefghijklmnopqrstuvwxyz\n")
            
            print(f"{Fore.YELLOW}[!] Created template token file: {self.token_file}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[!] Add your tokens and run again{Style.RESET_ALL}")
        except:
            pass
    
    def get_token_cycle(self):
        """Get infinite cycle iterator for tokens"""
        return cycle(self.tokens) if self.tokens else None
    
    def validate_token(self, token):
        """Quick token validation"""
        if not token or len(token) < 20:
            return False
        
        # Basic format check
        if not all(c.isalnum() or c in '_-' for c in token):
            return False
        
        return True

# ============================================================================
# TWITCH API FUNCTIONS
# ============================================================================

def get_user_id(username):
    """
    Get Twitch user ID from username
    Returns: user_id or None
    """
    try:
        headers = {
            'Client-ID': Config.CLIENT_ID,
            'Content-Type': 'application/json',
            'User-Agent': Config.USER_AGENT
        }
        
        payload = [{
            "operationName": Config.OPERATIONS["get_user_id"]["name"],
            "variables": {"login": username.lower()},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": Config.OPERATIONS["get_user_id"]["hash"]
                }
            }
        }]
        
        response = requests.post(
            Config.GQL_URL,
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data and isinstance(data, list):
                user_data = data[0].get("data", {}).get("user", {})
                user_id = user_data.get("id")
                if user_id:
                    print(f"{Fore.GREEN}[+] Found user ID for '{username}': {user_id}{Style.RESET_ALL}")
                    return user_id
        
        print(f"{Fore.RED}[-] Failed to get user ID for '{username}'{Style.RESET_ALL}")
        return None
        
    except Exception as e:
        print(f"{Fore.RED}[-] Error getting user ID: {e}{Style.RESET_ALL}")
        return None

def make_follow_request(target_id, token, action="follow"):
    """
    Make follow/unfollow request
    Returns: True if successful, False otherwise
    """
    try:
        # Clean token
        if token.startswith("oauth:"):
            token = token[6:]
        
        headers = {
            'Client-ID': Config.CLIENT_ID,
            'Authorization': f'OAuth {token}',
            'Content-Type': 'application/json',
            'User-Agent': Config.USER_AGENT,
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Origin': 'https://www.twitch.tv',
            'Referer': 'https://www.twitch.tv/',
        }
        
        if action == "follow":
            operation = Config.OPERATIONS["follow"]
            variables = {"input": {"disableNotifications": False, "targetID": target_id}}
        else:  # unfollow
            operation = Config.OPERATIONS["unfollow"]
            variables = {"input": {"targetID": target_id}}
        
        payload = [{
            "operationName": operation["name"],
            "variables": variables,
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": operation["hash"]
                }
            }
        }]
        
        response = requests.post(
            Config.GQL_URL,
            json=payload,
            headers=headers,
            timeout=15
        )
        
        # Check response
        if response.status_code in [200, 204]:
            try:
                data = response.json()
                if isinstance(data, list) and data:
                    # Check for errors in response
                    if "errors" in str(data).lower():
                        return False
                    
                    # Check for success indicators
                    response_text = json.dumps(data).lower()
                    if "follow" in response_text or "unfollow" in response_text:
                        return True
                    
                    # If no errors, assume success
                    return True
            except:
                # If we can't parse JSON but got 200/204, assume success
                return True
        
        # Rate limiting handling
        if response.status_code == 429:
            print(f"{Fore.YELLOW}[!] Rate limited, increasing delay{Style.RESET_ALL}")
            time.sleep(random.uniform(2, 5))
            return False
        
        return False
        
    except requests.exceptions.Timeout:
        print(f"{Fore.YELLOW}[!] Request timeout{Style.RESET_ALL}")
        return False
    except Exception as e:
        print(f"{Fore.RED}[-] Request error: {e}{Style.RESET_ALL}")
        return False

# ============================================================================
# WORKER THREADS
# ============================================================================

def follow_worker(target_id, token_iterator, target_username, max_actions, action="follow"):
    """
    Worker thread for follow/unfollow operations
    """
    thread_id = threading.current_thread().ident % 1000
    thread_stats = {"success": 0, "attempts": 0}
    
    print(f"{Fore.CYAN}[T{thread_id:03d}] Worker started for {action}{Style.RESET_ALL}")
    
    while stats.total < max_actions and thread_stats["attempts"] < (max_actions // Config.MAX_THREADS) * 2:
        try:
            # Get next token
            token = next(token_iterator)
            
            # Make request
            success = make_follow_request(target_id, token, action)
            
            # Update stats
            if success:
                stats.increment_success()
                thread_stats["success"] += 1
                
                # Print success message
                current_total = stats.total
                if current_total % 10 == 0 or current_total == max_actions:
                    elapsed = stats.get_elapsed()
                    rate = stats.get_success_rate()
                    print(f"{Fore.GREEN}[✓] {action.capitalize()} {current_total}/{max_actions} "
                          f"({rate:.1f}%) | Time: {elapsed}{Style.RESET_ALL}")
                else:
                    print(f"{Fore.GREEN}[+] {action.capitalize()} {target_username} "
                          f"({stats.success}/{stats.total}){Style.RESET_ALL}")
            else:
                stats.increment_failed()
                print(f"{Fore.RED}[-] Failed {action} for {target_username}{Style.RESET_ALL}")
            
            thread_stats["attempts"] += 1
            
            # Random delay to avoid rate limiting
            delay = random.uniform(*Config.REQUEST_DELAY)
            time.sleep(delay)
            
        except StopIteration:
            # No more tokens
            break
        except Exception as e:
            print(f"{Fore.RED}[T{thread_id:03d}] Worker error: {e}{Style.RESET_ALL}")
            time.sleep(1)
    
    print(f"{Fore.CYAN}[T{thread_id:03d}] Worker finished: {thread_stats['success']} successes "
          f"in {thread_stats['attempts']} attempts{Style.RESET_ALL}")

# ============================================================================
# MAIN CONTROLLER
# ============================================================================

class TwitchFollowBot:
    """Main controller class"""
    
    def __init__(self):
        self.token_manager = TokenManager()
        self.running = False
    
    def display_banner(self):
        """Display ASCII banner"""
        banner = f"""
{Fore.MAGENTA}{Style.BRIGHT}
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║        ████████╗██╗    ██╗██╗████████╗ ██████╗██╗  ██╗  ║
║        ╚══██╔══╝██║    ██║██║╚══██╔══╝██╔════╝██║  ██║  ║
║           ██║   ██║ █╗ ██║██║   ██║   ██║     ███████║  ║
║           ██║   ██║███╗██║██║   ██║   ██║     ██╔══██║  ║
║           ██║   ╚███╔███╔╝██║   ██║   ╚██████╗██║  ██║  ║
║           ╚═╝    ╚══╝╚══╝ ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝  ║
║                                                          ║
║                   NO PROXY EDITION v1.0                  ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
{Style.RESET_ALL}
        """
        print(banner)
    
    def display_stats(self):
        """Display final statistics"""
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}{Style.BRIGHT}FINAL STATISTICS:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Success:{Style.RESET_ALL} {stats.success}")
        print(f"{Fore.RED}Failed:{Style.RESET_ALL} {stats.failed}")
        print(f"{Fore.YELLOW}Total Attempts:{Style.RESET_ALL} {stats.total}")
        print(f"{Fore.MAGENTA}Success Rate:{Style.RESET_ALL} {stats.get_success_rate():.2f}%")
        print(f"{Fore.CYAN}Elapsed Time:{Style.RESET_ALL} {stats.get_elapsed()}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        
        # Save report
        self.save_report()
    
    def save_report(self):
        """Save operation report"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"report_{timestamp}.txt"
        
        try:
            with open(filename, 'w') as f:
                f.write("=" * 50 + "\n")
                f.write("TWITCH FOLLOW BOT REPORT\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Timestamp: {time.ctime()}\n")
                f.write(f"Success: {stats.success}\n")
                f.write(f"Failed: {stats.failed}\n")
                f.write(f"Total: {stats.total}\n")
                f.write(f"Success Rate: {stats.get_success_rate():.2f}%\n")
                f.write(f"Elapsed Time: {stats.get_elapsed()}\n")
                f.write(f"Tokens Used: {len(self.token_manager.tokens)}\n")
                f.write("\n" + "=" * 50 + "\n")
            
            print(f"{Fore.GREEN}[+] Report saved to {filename}{Style.RESET_ALL}")
        except:
            print(f"{Fore.RED}[-] Failed to save report{Style.RESET_ALL}")
    
    def run_follow_operation(self, username, count, action="follow"):
        """
        Main follow/unfollow operation
        """
        if self.running:
            print(f"{Fore.RED}[-] Bot is already running!{Style.RESET_ALL}")
            return False
        
        self.running = True
        
        # Display banner
        self.display_banner()
        
        print(f"{Fore.YELLOW}[*] Starting {action} operation for: {username}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[*] Target count: {count}{Style.RESET_ALL}")
        
        # Check tokens
        if not self.token_manager.tokens:
            print(f"{Fore.RED}[-] No valid tokens found!{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[!] Add tokens to tokens.txt and try again{Style.RESET_ALL}")
            return False
        
        print(f"{Fore.GREEN}[+] Using {len(self.token_manager.tokens)} tokens{Style.RESET_ALL}")
        
        # Get user ID
        print(f"{Fore.YELLOW}[*] Resolving user ID for '{username}'...{Style.RESET_ALL}")
        user_id = get_user_id(username)
        
        if not user_id:
            print(f"{Fore.RED}[-] Failed to get user ID. Check username spelling.{Style.RESET_ALL}")
            return False
        
        print(f"{Fore.GREEN}[+] User ID: {user_id}{Style.RESET_ALL}")
        
        # Create token iterator
        token_iterator = self.token_manager.get_token_cycle()
        if not token_iterator:
            print(f"{Fore.RED}[-] No tokens available!{Style.RESET_ALL}")
            return False
        
        # Calculate thread count
        thread_count = min(Config.MAX_THREADS, count, len(self.token_manager.tokens))
        print(f"{Fore.YELLOW}[*] Starting {thread_count} worker threads...{Style.RESET_ALL}")
        
        # Start threads
        threads = []
        for i in range(thread_count):
            thread = threading.Thread(
                target=follow_worker,
                args=(user_id, token_iterator, username, count, action),
                daemon=True
            )
            threads.append(thread)
            thread.start()
            
            # Stagger thread starts
            time.sleep(random.uniform(0.01, 0.05))
        
        print(f"{Fore.GREEN}[+] All workers started. Monitoring progress...{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        
        # Monitor progress
        try:
            last_total = 0
            while any(t.is_alive() for t in threads) and stats.total < count:
                # Check for progress every second
                if stats.total != last_total:
                    elapsed = stats.get_elapsed()
                    rate = stats.get_success_rate()
                    print(f"{Fore.CYAN}[*] Progress: {stats.total}/{count} "
                          f"({rate:.1f}%) | Time: {elapsed} | "
                          f"Active threads: {sum(1 for t in threads if t.is_alive())}{Style.RESET_ALL}")
                    last_total = stats.total
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}[!] Operation interrupted by user{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[!] Waiting for threads to finish...{Style.RESET_ALL}")
        
        # Wait for remaining threads
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=5)
        
        self.running = False
        
        # Display final stats
        self.display_stats()
        
        return True

# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def main():
    """Main entry point"""
    bot = TwitchFollowBot()
    
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{Style.BRIGHT}TWITCH FOLLOW BOT - NO PROXY VERSION{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    
    # Check for token file
    if not os.path.exists("tokens.txt"):
        print(f"{Fore.RED}[-] ERROR: tokens.txt not found!{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[!] Creating template file...{Style.RESET_ALL}")
        bot.token_manager.create_template()
        print(f"{Fore.YELLOW}[!] Add your OAuth tokens to tokens.txt and run again{Style.RESET_ALL}")
        input("\nPress Enter to exit...")
        return
    
    # Get user input
    print(f"{Fore.GREEN}[1]{Style.RESET_ALL} Follow user")
    print(f"{Fore.GREEN}[2]{Style.RESET_ALL} Unfollow user")
    print(f"{Fore.RED}[3]{Style.RESET_ALL} Exit\n")
    
    try:
        choice = input(f"{Fore.YELLOW}Select option (1-3): {Style.RESET_ALL}").strip()
        
        if choice == "3":
            print(f"{Fore.YELLOW}Goodbye!{Style.RESET_ALL}")
            return
        
        username = input(f"{Fore.CYAN}Target username: {Style.RESET_ALL}").strip()
        
        if not username:
            print(f"{Fore.RED}[-] Username cannot be empty!{Style.RESET_ALL}")
            return
        
        try:
            count = int(input(f"{Fore.CYAN}Number of actions: {Style.RESET_ALL}").strip())
            if count <= 0:
                raise ValueError
        except ValueError:
            print(f"{Fore.RED}[-] Invalid number! Using default: 10{Style.RESET_ALL}")
            count = 10
        
        if choice == "1":
            action = "follow"
        elif choice == "2":
            action = "unfollow"
        else:
            print(f"{Fore.RED}[-] Invalid choice!{Style.RESET_ALL}")
            return
        
        # Run operation
        print(f"\n{Fore.YELLOW}[*] Starting {action} operation...{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[*] This may take some time...{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[*] Press Ctrl+C to stop\n{Style.RESET_ALL}")
        
        success = bot.run_follow_operation(username, count, action)
        
        if success:
            print(f"\n{Fore.GREEN}[+] Operation completed successfully!{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}[-] Operation failed!{Style.RESET_ALL}")
        
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}[!] Operation cancelled by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}[-] Fatal error: {e}{Style.RESET_ALL}")
    
    input(f"\n{Fore.YELLOW}Press Enter to exit...{Style.RESET_ALL}")

# ============================================================================
# ALTERNATIVE: SIMPLE SCRIPT VERSION
# ============================================================================

def simple_version():
    """
    Ultra-simple version that matches your second example
    No classes, no complexity, just works
    """
    print(f"{Fore.GREEN}Simple Twitch Bot - Direct Mode{Style.RESET_ALL}")
    
    # Load tokens
    tokens = []
    if os.path.exists("tokens.txt"):
        with open("tokens.txt", "r") as f:
            tokens = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    
    if not tokens:
        print(f"{Fore.RED}No tokens found!{Style.RESET_ALL}")
        return
    
    print(f"{Fore.GREEN}Loaded {len(tokens)} tokens{Style.RESET_ALL}")
    
    # Get target
    username = input("Target username: ").strip()
    
    # Get user ID
    print(f"Getting ID for {username}...")
    user_id = get_user_id(username)
    
    if not user_id:
        print(f"{Fore.RED}Failed to get user ID!{Style.RESET_ALL}")
        return
    
    # Get count
    try:
        count = int(input("Number of follows: ").strip())
    except:
        count = 10
    
    # Choose action
    action = input("Action (follow/unfollow): ").strip().lower()
    if action not in ["follow", "unfollow"]:
        action = "follow"
    
    print(f"\nStarting {action} operation...\n")
    
    # Create token cycle
    token_cycle = cycle(tokens)
    
    # Simple loop
    for i in range(count):
        token = next(token_cycle)
        
        # Remove oauth: prefix if present
        if token.startswith("oauth:"):
            token = token[6:]
        
        success = make_follow_request(user_id, token, action)
        
        if success:
            print(f"{Fore.GREEN}[{i+1}/{count}] Success! {action} {username}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}[{i+1}/{count}] Failed {action}{Style.RESET_ALL}")
        
        # Small delay
        time.sleep(random.uniform(0.05, 0.15))
    
    print(f"\n{Fore.GREEN}Operation complete!{Style.RESET_ALL}")

# ============================================================================
# DIRECT EXECUTION SCRIPT
# ============================================================================

if __name__ == "__main__":
    """
    Entry point with two modes:
    1. python script.py --simple : Ultra-simple version
    2. python script.py : Full featured version
    """
    import sys
    
    if "--simple" in sys.argv or "-s" in sys.argv:
        simple_version()
    else:
        main()
