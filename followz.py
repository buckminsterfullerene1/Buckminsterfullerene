import json
import os
import random
import threading
import time
import aiohttp
import asyncio
from typing import Optional, Dict, Tuple

class TwitchFollower:
    def __init__(self, log_callback=print):
        self.log_callback = log_callback
        self.followed_records = {}
        # Cache for integrity tokens: {oauth_token: (integrity_token, expiry_timestamp)}
        self.integrity_cache = {}
        self.lock = threading.Lock()
        self.running = False
        self.proxies = self._load_proxies()

    # ... (_log, _load_proxies, _load_tokens, get_user_id, _fetch_user_id_async remain the same) ...

    async def _fetch_integrity_token(self, oauth_token: str, proxy_url: Optional[str] = None) -> Optional[Dict]:
        """
        Fetches an integrity token from Twitch's integrity endpoint for a given OAuth token.
        Returns a dict with 'token' and 'expires_in' if successful.
        """
        headers = {
            "Client-Id": "kimne78kx3ncx6brgo4mv6wki5h1ko",
            "Authorization": f"OAuth {oauth_token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        try:
            connector = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=30)

            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            ) as session:
                async with session.post(
                    "https://gql.twitch.tv/integrity",
                    headers=headers,
                    proxy=proxy_url
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        # Expected response format: {"token": "v4.public...", "expires_in": 3600}
                        if data.get("token"):
                            # Calculate expiry time (current time + expires_in seconds)
                            expiry_time = time.time() + data.get("expires_in", 3600)
                            return {
                                "token": data["token"],
                                "expires_in": data.get("expires_in", 3600),
                                "expiry_time": expiry_time
                            }
                    else:
                        self._log(f"Integrity token fetch failed for token {oauth_token[:10]}...: Status {response.status}")
                        return None
                        
        except Exception as e:
            self._log(f"Error fetching integrity token for {oauth_token[:10]}...: {e}")
            return None

    async def _get_valid_integrity_token(self, oauth_token: str, proxy_url: Optional[str] = None) -> Optional[str]:
        """
        Retrieves a valid integrity token from cache or fetches a new one.
        Returns the integrity token string if successful.
        """
        current_time = time.time()
        
        # Check cache for valid token
        if oauth_token in self.integrity_cache:
            cached_data = self.integrity_cache[oauth_token]
            # Check if token is still valid (with 60-second buffer)
            if current_time < cached_data["expiry_time"] - 60:
                return cached_data["token"]
        
        # Fetch new token
        integrity_data = await self._fetch_integrity_token(oauth_token, proxy_url)
        if integrity_data:
            self.integrity_cache[oauth_token] = integrity_data
            return integrity_data["token"]
        
        return None

    async def _execute_follow_request(self, target_id, token, target_username):
        try:
            # Get proxy URL first (needed for integrity token fetch)
            proxy_url = None
            if self.proxies:
                proxy_url = random.choice(self.proxies)
                self._log(f"Using proxy: {proxy_url} for token: {token[:10]}...")

            # Get integrity token
            integrity_token = await self._get_valid_integrity_token(token, proxy_url)
            if not integrity_token:
                self._log(f"Failed to get integrity token for {token[:10]}...")
                return False

            headers = {
                "Accept": "application/json",
                "Accept-Language": "en-US",
                "Authorization": f"OAuth {token}",
                "Client-Integrity": integrity_token,  # REQUIRED: Integrity token header[citation:1][citation:4]
                "Client-Id": "kimne78kx3ncx6brgo4mv6wki5h1ko",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            payload = json.dumps([{
                "operationName": "FollowButton_FollowUser",  # Updated operation name
                "variables": {
                    "input": {
                        "targetID": str(target_id),
                        "disableNotifications": False
                    }
                },
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "51956f0c469f54e60211ea4e6a34b597d45c1c37b9664d4b62096a1ac03be9e6"  # Updated hash[citation:1]
                    }
                }
            }])

            connector = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            ) as session:
                async with session.post(
                    "https://gql.twitch.tv/gql",
                    data=payload,
                    headers=headers,
                    proxy=proxy_url
                ) as response:
                    
                    result_text = await response.text()
                    
                    if response.status in (200, 204):
                        if "errors" not in result_text.lower():
                            return True
                    
                    self._log(f"Follow request failed for {token[:10]}...: Status {response.status}, Response: {result_text[:200]}")
                    return False
                    
        except Exception as e:
            self._log(f"Request failed with error: {e}")
            return False

    # ... (_follow_worker, execute_follows, start, _run_operation, stop remain the same) ...

if __name__ == "__main__":
    bot = TwitchFollower(print)
    
    print("Twitch Follower Bot (Updated with Integrity Endpoint)")
    print("----------------------------------------------------")
    
    username = input("Target username: ").strip()
    
    try:
        count = int(input("Number of follows: ").strip())
    except ValueError:
        print("Invalid number. Using default: 10")
        count = 10
    
    bot.start(username, count)
    
    print("\nFollow operation started. Press Ctrl+C to stop.")
    
    try:
        while bot.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        bot.stop()
        time.sleep(2)
    
    print("Bot stopped.")
