import requests
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys

class TwitchTokenChecker:
    def __init__(self):
        self.valid = []
        self.invalid = []
        self.checked = 0
        self.total = 0
        self.lock = threading.Lock()
    
    def clear(self):
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def banner(self):
        print(f"""
{'='*60}
TWITCH TOKEN CHECKER (timestamp|auth_token|session format)
{'='*60}
        """)
    
    def extract_auth_part(self, token_line):
        """Extract the auth-token part (second part after split)"""
        parts = token_line.strip().split('|')
        if len(parts) >= 2:
            return parts[1]  # This is the actual auth token
        return token_line.strip()
    
    def check_token(self, auth_token):
        """Check if the auth token works with Twitch"""
        # Try multiple methods to validate
        
        # Method 1: Try as auth-token cookie
        cookies = {
            'auth-token': auth_token,
            'unique_id': 'checker123'
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        try:
            # Try to access a page that requires login
            response = requests.get(
                'https://www.twitch.tv/directory/following',
                cookies=cookies,
                headers=headers,
                timeout=10,
                allow_redirects=False
            )
            
            # Check response
            if response.status_code == 200:
                # Look for signs of being logged in
                content = response.text.lower()
                if 'following' in content and 'channels' in content:
                    return True, "Following page access"
                if 'dashboard' in content or 'user-menu' in content:
                    return True, "User dashboard access"
            
            # Try another endpoint
            response2 = requests.get(
                'https://www.twitch.tv/settings',
                cookies=cookies,
                headers=headers,
                timeout=10,
                allow_redirects=False
            )
            
            if response2.status_code == 200:
                return True, "Settings page access"
            
            return False, "No valid session found"
            
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def process_line(self, full_line):
        """Process one line from the file"""
        auth_token = self.extract_auth_part(full_line)
        
        # Skip if token looks invalid
        if not auth_token or len(auth_token) < 20:
            return full_line, False, "Token too short"
        
        is_valid, reason = self.check_token(auth_token)
        
        if is_valid:
            # Save the working auth token
            with open('working_auths.txt', 'a') as f:
                f.write(f"{auth_token}\n")
            # Save full line with timestamp
            with open('valid_tokens_full.txt', 'a') as f:
                f.write(f"{full_line}\n")
        
        return full_line, is_valid, reason
    
    def worker(self, token_batch, batch_num):
        """Worker thread to process a batch of tokens"""
        batch_results = []
        for token_line in token_batch:
            full_line, is_valid, reason = self.process_line(token_line)
            
            with self.lock:
                self.checked += 1
                if is_valid:
                    self.valid.append(full_line)
                    status = "VALID"
                    color_code = "✅"
                else:
                    self.invalid.append(full_line)
                    status = "INVALID"
                    color_code = "❌"
                
                # Show progress
                auth_part = self.extract_auth_part(full_line)
                print(f"[{self.checked}/{self.total}] {color_code} {status}: {auth_part[:20]}... ({reason[:20]})")
            
            batch_results.append((full_line, is_valid))
        
        return batch_results
    
    def load_tokens(self, filename='tokens.txt'):
        """Load tokens from file"""
        if not os.path.exists(filename):
            print(f"[ERROR] {filename} not found!")
            print(f"Make sure {filename} exists in the same folder")
            return []
        
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [line.strip() for line in f if line.strip()]
        
        # Remove duplicates
        unique_lines = list(dict.fromkeys(lines))
        self.total = len(unique_lines)
        
        print(f"[+] Loaded {self.total} unique tokens from {filename}")
        return unique_lines
    
    def run_check(self):
        """Main checking function"""
        self.clear()
        self.banner()
        
        # Load tokens
        tokens = self.load_tokens()
        if not tokens:
            input("\nPress Enter to exit...")
            return
        
        # Ask for threads
        try:
            workers = input("[?] Number of threads (1-20, default 5): ").strip()
            workers = int(workers) if workers.isdigit() else 5
            workers = max(1, min(20, workers))
        except:
            workers = 5
        
        print(f"[+] Using {workers} threads")
        print(f"[+] Starting check...\n")
        time.sleep(1)
        
        # Clear output files
        for file in ['working_auths.txt', 'valid_tokens_full.txt']:
            if os.path.exists(file):
                os.remove(file)
        
        # Split tokens into batches
        batch_size = max(1, len(tokens) // workers)
        batches = []
        for i in range(0, len(tokens), batch_size):
            batches.append(tokens[i:i + batch_size])
        
        start_time = time.time()
        
        # Process batches with thread pool
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for i, batch in enumerate(batches):
                future = executor.submit(self.worker, batch, i)
                futures.append(future)
            
            # Wait for all to complete
            for future in as_completed(futures):
                future.result()
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Show results
        self.show_results(total_time)
    
    def show_results(self, total_time):
        """Display final results"""
        print(f"\n{'='*60}")
        print("CHECK COMPLETE!")
        print(f"{'='*60}")
        print(f"Total checked: {self.total}")
        print(f"Valid tokens: {len(self.valid)}")
        print(f"Invalid tokens: {len(self.invalid)}")
        
        if self.total > 0:
            success_rate = (len(self.valid) / self.total) * 100
            print(f"Success rate: {success_rate:.2f}%")
        
        print(f"Time taken: {total_time:.2f} seconds")
        
        if len(self.valid) > 0:
            print(f"\n✅ Valid tokens saved to:")
            print(f"   - working_auths.txt (just auth tokens)")
            print(f"   - valid_tokens_full.txt (full format)")
            
            print(f"\nSample valid tokens:")
            for i, token in enumerate(self.valid[:3]):
                auth_part = self.extract_auth_part(token)
                print(f"   {i+1}. {auth_part[:30]}...")
            
            if len(self.valid) > 3:
                print(f"   ... and {len(self.valid) - 3} more")
        else:
            print(f"\n❌ No valid tokens found")
        
        print(f"{'='*60}")

# Quick and simple version
def simple_check():
    """Simple version without threads"""
    print("Simple Twitch Token Checker")
    print("="*50)
    
    if not os.path.exists('tokens.txt'):
        print("ERROR: tokens.txt not found!")
        return
    
    with open('tokens.txt', 'r') as f:
        tokens = [line.strip() for line in f if line.strip()]
    
    print(f"Loaded {len(tokens)} tokens\n")
    
    valid = []
    
    for i, token_line in enumerate(tokens, 1):
        parts = token_line.split('|')
        if len(parts) < 2:
            print(f"[{i}/{len(tokens)}] ❌ Invalid format")
            continue
        
        auth_token = parts[1]
        print(f"[{i}/{len(tokens)}] Checking: {auth_token[:20]}...")
        
        # Simple check
        cookies = {'auth-token': auth_token}
        
        try:
            response = requests.get(
                'https://www.twitch.tv/',
                cookies=cookies,
                timeout=5
            )
            
            if response.status_code == 200:
                # Quick check for login indicators
                if 'twilight-user' in response.text or 'auth-token' in response.text:
                    print(f"    ✅ VALID")
                    valid.append(token_line)
                    with open('valid.txt', 'a') as f:
                        f.write(f"{auth_token}\n")
                else:
                    print(f"    ❌ NOT LOGGED IN")
            else:
                print(f"    ❌ HTTP {response.status_code}")
                
        except Exception as e:
            print(f"    ⚠️ ERROR")
        
        time.sleep(0.2)  # Avoid rate limits
    
    print(f"\n{'='*50}")
    print(f"Valid: {len(valid)}")
    print(f"Invalid: {len(tokens) - len(valid)}")
    
    if valid:
        print(f"\n✅ Saved auth tokens to: valid.txt")

# Main
if __name__ == "__main__":
    checker = TwitchTokenChecker()
    
    try:
        checker.run_check()
    except KeyboardInterrupt:
        print("\n\n⚠️ Stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    input("\nPress Enter to exit...")
