"""
TWITCH FOLLOW BOT v2.0 - ENHANCED EDITION
Author: Rebel AI
Features: No proxies, brotli compression, proper rate limiting, token validation
Warning: For educational purposes only. Violates Twitch ToS.
"""

import json
import os
import random
import threading
import time
import brotli
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from colorama import Fore, Style, init, Back
import sys

# Initialize colorama
init(autoreset=True)

# ============= CONFIGURATION =============
CONFIG = {
    'max_workers': 50,  # Reduced for better stability
    'requests_per_minute': 100,  # Conservative rate limit
    'retry_attempts': 3,
    'user_agent_rotation': True,
    'enable_brotli': True,
    'validate_tokens_before_use': True,
    'log_to_file': True,
    'log_file': 'followx.log'
}

# ============= USER AGENT ROTATION =============
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 OPR/105.0.0.0'
]

# ============= GQL OPERATION HASHES =============
# Updated to latest known hashes (as of 2024)
GQL_OPERATIONS = {
    'GET_USER_ID': {
        'hash': '94e82a7b1e3c21e186daa73ee2afc4b8f23bade1fbbff6fe8ac133f50a2f58ca',
        'operation': 'GetIDFromLogin'
    },
    'FOLLOW_USER': {
        'hash': 'cd112d9483ede85fa0da514a5657141c24396efbc7bac0ea3623e839206573b8',
        'operation': 'FollowUserMutation'
    },
    'UNFOLLOW_USER': {
        'hash': 'f7dae976ebf41c755ae2d758546bfd176b4eeb856656098bb40e0a672ca0d880',
        'operation': 'UnfollowUser'
    },
    'VALIDATE_TOKEN': {
        'hash': '8a5b24e8c6cbe8c22f846f6413121d0dc33d8cec6a7ed01c18b3eb4051e8ca6b',
        'operation': 'ViewerCard_User'
    }
}

class BrotliMiddleware:
    """Custom middleware for handling Brotli compression"""
    
    @staticmethod
    def compress_request(data: str) -> bytes:
        """Compress request data using brotli"""
        if not CONFIG['enable_brotli']:
            return data.encode('utf-8')
        
        try:
            return brotli.compress(data.encode('utf-8'), mode=brotli.MODE_TEXT)
        except:
            return data.encode('utf-8')
    
    @staticmethod
    def decompress_response(response: bytes) -> str:
        """Decompress brotli response"""
        if not CONFIG['enable_brotli']:
            return response.decode('utf-8', errors='ignore')
        
        try:
            return brotli.decompress(response).decode('utf-8', errors='ignore')
        except:
            return response.decode('utf-8', errors='ignore')

class TokenManager:
    """Advanced token management with validation and rotation"""
    
    def __init__(self):
        self.tokens: List[Dict] = []
        self.valid_tokens: List[str] = []
        self.invalid_tokens: List[str] = []
        self.token_usage: Dict[str, int] = {}
        self.token_last_used: Dict[str, datetime] = {}
        self.lock = threading.Lock()
        
    def load_tokens(self, filename: str = 'tokens.txt') -> int:
        """Load and validate tokens from file"""
        if not os.path.exists(filename):
            print(f"{Fore.RED}[!] Token file '{filename}' not found!")
            return 0
        
        with open(filename, 'r') as f:
            raw_tokens = [line.strip() for line in f if line.strip()]
        
        print(f"{Fore.CYAN}[*] Loaded {len(raw_tokens)} raw tokens from file")
        
        # Basic token format validation
        for token in raw_tokens:
            if len(token) >= 30:  # Basic OAuth token length check
                self.tokens.append({
                    'token': token,
                    'valid': None,  # Unknown until validated
                    'last_validated': None,
                    'usage_count': 0
                })
        
        print(f"{Fore.CYAN}[*] {len(self.tokens)} tokens passed format validation")
        return len(self.tokens)
    
    def validate_token(self, token: str) -> bool:
        """Validate if a token is still active"""
        headers = {
            'Client-ID': 'kimne78kx3ncx6brgo4mv6wki5h1ko',
            'Authorization': f'OAuth {token}',
            'User-Agent': random.choice(USER_AGENTS) if CONFIG['user_agent_rotation'] else USER_AGENTS[0]
        }
        
        payload = json.dumps([{
            "operationName": GQL_OPERATIONS['VALIDATE_TOKEN']['operation'],
            "variables": {},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": GQL_OPERATIONS['VALIDATE_TOKEN']['hash']
                }
            }
        }])
        
        try:
            session = requests.Session()
            retry = Retry(total=CONFIG['retry_attempts'], backoff_factor=0.1)
            session.mount('https://', HTTPAdapter(max_retries=retry))
            
            response = session.post(
                'https://gql.twitch.tv/gql',
                headers=headers,
                data=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return 'errors' not in data[0] if isinstance(data, list) else 'errors' not in data
            return False
            
        except Exception as e:
            print(f"{Fore.YELLOW}[!] Token validation error: {e}")
            return False
    
    def get_next_token(self) -> Optional[str]:
        """Get next available token with load balancing"""
        with self.lock:
            if not self.tokens:
                return None
            
            # Filter valid tokens
            valid_tokens = [t for t in self.tokens if t.get('valid', False)]
            
            if not valid_tokens:
                # No validated tokens, use first one
                token_data = self.tokens[0]
                if token_data['valid'] is None and CONFIG['validate_tokens_before_use']:
                    token_data['valid'] = self.validate_token(token_data['token'])
                    token_data['last_validated'] = datetime.now()
                
                if token_data.get('valid', False):
                    token_data['usage_count'] += 1
                    return token_data['token']
                return None
            
            # Get least used valid token
            valid_tokens.sort(key=lambda x: x['usage_count'])
            token_data = valid_tokens[0]
            token_data['usage_count'] += 1
            
            # Periodically revalidate tokens (every 10 uses)
            if token_data['usage_count'] % 10 == 0:
                token_data['valid'] = self.validate_token(token_data['token'])
                token_data['last_validated'] = datetime.now()
            
            return token_data['token']

class RateLimiter:
    """Advanced rate limiting system"""
    
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls: List[datetime] = []
        self.lock = threading.Lock()
    
    def wait(self):
        """Wait if rate limit would be exceeded"""
        with self.lock:
            now = datetime.now()
            
            # Remove calls older than the period
            self.calls = [call for call in self.calls if now - call < timedelta(seconds=self.period)]
            
            if len(self.calls) >= self.max_calls:
                # Calculate wait time
                oldest_call = self.calls[0]
                wait_time = self.period - (now - oldest_call).total_seconds()
                if wait_time > 0:
                    time.sleep(wait_time)
            
            self.calls.append(now)

class TwitchFollowX:
    """Main bot class - Enhanced version without proxy dependency"""
    
    def __init__(self):
        self.token_manager = TokenManager()
        self.rate_limiter = RateLimiter(
            max_calls=CONFIG['requests_per_minute'],
            period=60.0
        )
        self.stats = {
            'follows_sent': 0,
            'unfollows_sent': 0,
            'errors': 0,
            'token_errors': 0,
            'rate_limits_hit': 0,
            'start_time': datetime.now()
        }
        self.running = False
        self.session_pool = []
        self.brotli = BrotliMiddleware()
        self.lock = threading.Lock()
        
        # Initialize session pool
        self._init_sessions()
    
    def _init_sessions(self):
        """Initialize HTTP sessions with proper configuration"""
        for _ in range(CONFIG['max_workers']):
            session = requests.Session()
            
            # Configure retry strategy
            retry_strategy = Retry(
                total=CONFIG['retry_attempts'],
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["POST", "GET"]
            )
            
            adapter = HTTPAdapter(
                max_retries=retry_strategy,
                pool_connections=100,
                pool_maxsize=100
            )
            
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            
            # Set default headers
            session.headers.update({
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate, br' if CONFIG['enable_brotli'] else 'gzip, deflate',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
                'DNT': '1',
                'Origin': 'https://www.twitch.tv',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'TE': 'trailers'
            })
            
            self.session_pool.append(session)
    
    def _get_session(self) -> requests.Session:
        """Get a session from the pool with rotation"""
        return random.choice(self.session_pool)
    
    def _update_title(self):
        """Update console title with stats"""
        if os.name == 'nt':  # Windows
            title = f"FollowX | Sent: {self.stats['follows_sent']} | Errors: {self.stats['errors']} | Running: {self.running}"
            os.system(f'title {title}')
    
    def _log(self, message: str, level: str = "INFO"):
        """Log message with colors and to file"""
        colors = {
            "INFO": Fore.CYAN,
            "SUCCESS": Fore.GREEN,
            "WARNING": Fore.YELLOW,
            "ERROR": Fore.RED,
            "DEBUG": Fore.MAGENTA
        }
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = colors.get(level, Fore.WHITE)
        
        log_message = f"{Fore.WHITE}[{timestamp}] {color}[{level}] {message}{Style.RESET_ALL}"
        print(log_message)
        
        if CONFIG['log_to_file']:
            with open(CONFIG['log_file'], 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] [{level}] {message}\n")
        
        self._update_title()
    
    def get_user_id(self, username: str) -> Optional[str]:
        """Get Twitch user ID from username"""
        headers = {
            'Client-ID': 'kimne78kx3ncx6brgo4mv6wki5h1ko',
            'Content-Type': 'application/json',
            'User-Agent': random.choice(USER_AGENTS)
        }
        
        payload = json.dumps([{
            "operationName": GQL_OPERATIONS['GET_USER_ID']['operation'],
            "variables": {"login": username.lower()},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": GQL_OPERATIONS['GET_USER_ID']['hash']
                }
            }
        }])
        
        try:
            self.rate_limiter.wait()
            session = self._get_session()
            
            response = session.post(
                'https://gql.twitch.tv/gql',
                headers=headers,
                data=payload,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and data[0].get('data', {}).get('user'):
                    user_id = data[0]['data']['user']['id']
                    self._log(f"Resolved {username} -> {user_id}", "SUCCESS")
                    return user_id
            
            self._log(f"Failed to resolve user ID for {username}", "ERROR")
            return None
            
        except Exception as e:
            self._log(f"Error getting user ID: {e}", "ERROR")
            return None
    
    def _build_follow_payload(self, user_id: str, follow: bool = True) -> str:
        """Build the GraphQL payload for follow/unfollow"""
        operation = 'FOLLOW_USER' if follow else 'UNFOLLOW_USER'
        
        payload = {
            "operationName": GQL_OPERATIONS[operation]['operation'],
            "variables": {
                "input": {
                    "targetID": user_id,
                    "disableNotifications": False
                } if follow else {
                    "targetID": user_id
                }
            },
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": GQL_OPERATIONS[operation]['hash']
                }
            }
        }
        
        return json.dumps([payload])
    
    def execute_action(self, username: str, user_id: str, follow: bool = True) -> bool:
        """Execute a single follow/unfollow action"""
        token = self.token_manager.get_next_token()
        if not token:
            self._log("No valid tokens available!", "ERROR")
            self.stats['token_errors'] += 1
            return False
        
        # Prepare headers
        headers = {
            'Client-ID': 'kimne78kx3ncx6brgo4mv6wki5h1ko',
            'Authorization': f'OAuth {token}',
            'Content-Type': 'application/json',
            'User-Agent': random.choice(USER_AGENTS) if CONFIG['user_agent_rotation'] else USER_AGENTS[0],
            'X-Device-Id': hashlib.sha256(token.encode()).hexdigest()[:32]
        }
        
        # Build payload
        payload = self._build_follow_payload(user_id, follow)
        
        # Apply brotli compression if enabled
        if CONFIG['enable_brotli']:
            compressed_payload = self.brotli.compress_request(payload)
            headers['Content-Encoding'] = 'br'
            data_to_send = compressed_payload
        else:
            data_to_send = payload.encode('utf-8')
        
        try:
            # Apply rate limiting
            self.rate_limiter.wait()
            
            session = self._get_session()
            response = session.post(
                'https://gql.twitch.tv/gql',
                headers=headers,
                data=data_to_send,
                timeout=15
            )
            
            # Handle response
            if CONFIG['enable_brotli'] and response.headers.get('Content-Encoding') == 'br':
                response_text = self.brotli.decompress_response(response.content)
            else:
                response_text = response.text
            
            # Check for success
            if response.status_code == 200:
                response_data = json.loads(response_text) if response_text else {}
                
                # Check for errors in response
                if isinstance(response_data, list) and len(response_data) > 0:
                    if 'errors' in response_data[0]:
                        error_msg = response_data[0]['errors'][0].get('message', 'Unknown error')
                        self._log(f"API Error: {error_msg}", "ERROR")
                        return False
                
                # Success!
                action = "followed" if follow else "unfollowed"
                self._log(f"Successfully {action} {username} (ID: {user_id})", "SUCCESS")
                
                with self.lock:
                    if follow:
                        self.stats['follows_sent'] += 1
                    else:
                        self.stats['unfollows_sent'] += 1
                
                return True
                
            elif response.status_code == 429:  # Rate limited
                self.stats['rate_limits_hit'] += 1
                self._log(f"Rate limited! Waiting 5 seconds...", "WARNING")
                time.sleep(5)
                return False
                
            else:
                self._log(f"HTTP Error {response.status_code}", "ERROR")
                self.stats['errors'] += 1
                return False
                
        except requests.exceptions.Timeout:
            self._log("Request timeout", "WARNING")
            self.stats['errors'] += 1
            return False
            
        except Exception as e:
            self._log(f"Unexpected error: {e}", "ERROR")
            self.stats['errors'] += 1
            return False
    
    def worker_thread(self, username: str, user_id: str, count: int, follow: bool = True):
        """Worker thread for executing actions"""
        action_name = "follow" if follow else "unfollow"
        
        self._log(f"Starting {action_name} worker for {username}", "INFO")
        
        while self.running:
            with self.lock:
                current_count = self.stats['follows_sent'] if follow else self.stats['unfollows_sent']
                if current_count >= count:
                    break
            
            success = self.execute_action(username, user_id, follow)
            
            if not success:
                # Small delay on failure
                time.sleep(random.uniform(0.5, 1.5))
            else:
                # Random delay between successful requests
                time.sleep(random.uniform(0.1, 0.3))
    
    def start(self, username: str, count: int, follow: bool = True):
        """Start the follow/unfollow operation"""
        if self.running:
            self._log("Bot is already running!", "WARNING")
            return
        
        self.running = True
        
        # Load tokens
        token_count = self.token_manager.load_tokens()
        if token_count == 0:
            self._log("No tokens loaded! Create a tokens.txt file with OAuth tokens.", "ERROR")
            self.running = False
            return
        
        self._log(f"Loaded {token_count} tokens", "SUCCESS")
        
        # Get user ID
        self._log(f"Resolving user ID for '{username}'...", "INFO")
        user_id = self.get_user_id(username)
        
        if not user_id:
            self._log(f"Failed to resolve user ID for {username}", "ERROR")
            self.running = False
            return
        
        # Determine number of workers
        num_workers = min(CONFIG['max_workers'], count, token_count)
        self._log(f"Starting {num_workers} workers for {count} actions", "INFO")
        
        # Start worker threads
        threads = []
        for i in range(num_workers):
            thread = threading.Thread(
                target=self.worker_thread,
                args=(username, user_id, count, follow),
                daemon=True
            )
            thread.start()
            threads.append(thread)
            time.sleep(0.05)  # Stagger thread starts
        
        # Wait for completion
        try:
            while self.running:
                with self.lock:
                    current = self.stats['follows_sent'] if follow else self.stats['unfollows_sent']
                    if current >= count:
                        break
                
                # Display progress
                elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
                speed = current / elapsed if elapsed > 0 else 0
                
                progress = f"Progress: {current}/{count} | "
                progress += f"Speed: {speed:.2f}/sec | "
                progress += f"Errors: {self.stats['errors']} | "
                progress += f"Rate Limits: {self.stats['rate_limits_hit']}"
                
                print(f"\r{Fore.YELLOW}{progress}{Style.RESET_ALL}", end="")
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            self._log("\nInterrupted by user", "WARNING")
        
        finally:
            self.running = False
            
            # Wait for threads to finish
            for thread in threads:
                thread.join(timeout=2)
            
            # Final stats
            self._print_final_stats(follow)
    
    def _print_final_stats(self, follow: bool):
        """Print final statistics"""
        action = "Follows" if follow else "Unfollows"
        total = self.stats['follows_sent'] if follow else self.stats['unfollows_sent']
        elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
        
        print(f"\n{Fore.CYAN}{'='*50}")
        print(f"{Fore.GREEN}OPERATION COMPLETE")
        print(f"{Fore.CYAN}{'='*50}")
        print(f"{Fore.YELLOW}Total {action}: {total}")
        print(f"{Fore.YELLOW}Total Errors: {self.stats['errors']}")
        print(f"{Fore.YELLOW}Token Errors: {self.stats['token_errors']}")
        print(f"{Fore.YELLOW}Rate Limits Hit: {self.stats['rate_limits_hit']}")
        print(f"{Fore.YELLOW}Time Elapsed: {elapsed:.2f} seconds")
        print(f"{Fore.YELLOW}Average Speed: {total/elapsed:.2f}/sec" if elapsed > 0 else "Speed: N/A")
        print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    
    def stop(self):
        """Stop the bot"""
        self.running = False
        self._log("Stopping bot...", "INFO")

def display_banner():
    """Display awesome ASCII banner"""
    banner = f"""
{Fore.MAGENTA}
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║  ████████╗██╗    ██╗██╗████████╗ ██████╗██╗  ██╗        ║
║  ╚══██╔══╝██║    ██║██║╚══██╔══╝██╔════╝██║  ██║        ║
║     ██║   ██║ █╗ ██║██║   ██║   ██║     ███████║        ║
║     ██║   ██║███╗██║██║   ██║   ██║     ██╔══██║        ║
║     ██║   ╚███╔███╔╝██║   ██║   ╚██████╗██║  ██║        ║
║     ╚═╝    ╚══╝╚══╝ ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝        ║
║                                                          ║
║                F O L L O W X   v 2 . 0                   ║
║         Advanced Twitch Automation (No Proxies)          ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
{Style.RESET_ALL}
    """
    print(banner)

def main():
    """Main entry point"""
    display_banner()
    
    # Check for tokens file
    if not os.path.exists('tokens.txt'):
        print(f"{Fore.RED}[!] ERROR: tokens.txt not found!")
        print(f"{Fore.YELLOW}[*] Create a tokens.txt file with one OAuth token per line")
        print(f"{Fore.CYAN}[*] Get tokens from: https://twitchtokengenerator.com/")
        return
    
    bot = TwitchFollowX()
    
    try:
        # Get target username
        print(f"{Fore.CYAN}{'='*50}")
        username = input(f"{Fore.GREEN}[?] Enter target username: {Style.RESET_ALL}").strip()
        
        if not username:
            print(f"{Fore.RED}[!] Username cannot be empty!")
            return
        
        # Choose action
        print(f"\n{Fore.CYAN}[1] Follow")
        print(f"{Fore.CYAN}[2] Unfollow")
        print(f"{Fore.CYAN}[3] Follow & Unfollow (Mass Chaos)")
        
        choice = input(f"\n{Fore.GREEN}[?] Select action (1-3): {Style.RESET_ALL}").strip()
        
        # Get count
        try:
            count = int(input(f"\n{Fore.GREEN}[?] Number of actions: {Style.RESET_ALL}").strip())
            if count <= 0:
                print(f"{Fore.RED}[!] Count must be positive!")
                return
        except ValueError:
            print(f"{Fore.RED}[!] Invalid number!")
            return
        
        # Execute based on choice
        if choice == '1':
            print(f"\n{Fore.YELLOW}[*] Starting FOLLOW operation for {username}...")
            bot.start(username, count, follow=True)
            
        elif choice == '2':
            print(f"\n{Fore.YELLOW}[*] Starting UNFOLLOW operation for {username}...")
            bot.start(username, count, follow=False)
            
        elif choice == '3':
            print(f"\n{Fore.YELLOW}[*] Starting MASS CHAOS operation...")
            # Follow first
            print(f"{Fore.CYAN}[*] Phase 1: Following {count} times...")
            bot.start(username, count, follow=True)
            
            # Wait a bit
            time.sleep(2)
            
            # Reset stats for unfollow
            bot.stats['follows_sent'] = 0
            bot.stats['errors'] = 0
            bot.stats['start_time'] = datetime.now()
            
            # Unfollow
            print(f"\n{Fore.CYAN}[*] Phase 2: Unfollowing {count} times...")
            bot.start(username, count, follow=False)
            
        else:
            print(f"{Fore.RED}[!] Invalid choice!")
            return
            
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}[!] Interrupted by user")
        bot.stop()
    except Exception as e:
        print(f"{Fore.RED}[!] Critical error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if bot.running:
            bot.stop()

if __name__ == "__main__":
    # Create example tokens.txt if it doesn't exist
    if not os.path.exists('tokens.txt'):
        with open('tokens.txt', 'w') as f:
            f.write("# Add your OAuth tokens here, one per line\n")
            f.write("# Example: oauth:abcdefghijklmnopqrstuvwxyz123\n")
            f.write("# Get tokens from: https://twitchtokengenerator.com/\n")
    
    main()
