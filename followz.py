import json
import os
import random
import threading
import time
import aiohttp
import asyncio

class TwitchFollower:
    def __init__(self, log_callback=print):
        self.log_callback = log_callback
        self.followed_records = {}
        self.lock = threading.Lock()
        self.running = False
        # Removed proxy loading completely

    def _log(self, message):
        self.log_callback(message)

    def _load_tokens(self):
        tokens = []
        if os.path.exists("tokens.txt"):
            with open("tokens.txt", "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.isspace():
                        tokens.append(line)
        return tokens

    def get_user_id(self, user):
        headers = {
            "Client-Id": "kimne78kx3ncx6brgo4mv6wki5h1ko",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        payload = json.dumps([{
            "operationName": "GetIDFromLogin",
            "variables": {"login": user},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "94e82a7b1e3c21e186daa73ee2afc4b8f23bade1fbbff6fe8ac133f50a2f58ca"
                }
            }
        }])

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            id_result = loop.run_until_complete(self._fetch_user_id_async(headers, payload))
            loop.close()
            return id_result
        except Exception as e:
            self._log(f"Error getting user ID for {user}: {e}")
            return False

    async def _fetch_user_id_async(self, headers, payload):
        try:
            connector = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            ) as session:
                async with session.post(
                    "https://gql.twitch.tv/gql",
                    headers=headers,
                    data=payload
                    # proxy parameter completely removed
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data and len(data) > 0 and "data" in data[0]:
                            return data[0]["data"]["user"]["id"]
                    return False
        except Exception as e:
            self._log(f"Network error getting ID: {e}")
            return False

    async def _execute_follow_request(self, target_id, token, target_username):
        try:
            headers = {
                "Accept": "application/json",
                "Accept-Language": "en-US",
                "Authorization": f"OAuth {token}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            payload = json.dumps([{
                "operationName": "FollowUserMutation",
                "variables": {
                    "targetId": str(target_id),
                    "disableNotifications": False
                },
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "cd112d9483ede85fa0da514a5657141c24396efbc7bac0ea3623e839206573b8"
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
                    headers=headers
                    # proxy removed
                ) as response:
                    
                    result_text = await response.text()
                    
                    if response.status in (200, 204):
                        if "errors" not in result_text.lower():
                            return True
                    
                    self._log(f"Follow failed | Status: {response.status} | {result_text[:120]}...")
                    return False
                    
        except Exception as e:
            self._log(f"Request failed with error: {e}")
            return False

    async def _follow_worker(self, target_id, tokens_list, target_username, max_follows, stats):
        while self.running and stats["completed"] < max_follows:
            available_token = None
            
            with self.lock:
                unused_tokens = [
                    token for token in tokens_list 
                    if token not in self.followed_records or target_id not in self.followed_records[token]
                ]
                
                if unused_tokens:
                    available_token = random.choice(unused_tokens)
                else:
                    break
            
            if not available_token:
                await asyncio.sleep(0.5)
                continue
            
            success = await self._execute_follow_request(target_id, available_token, target_username)
            
            if success:
                with self.lock:
                    stats["completed"] += 1
                    current_count = stats["completed"]
                    
                    if available_token not in self.followed_records:
                        self.followed_records[available_token] = []
                    self.followed_records[available_token].append(target_id)
                
                self._log(f"Follow {current_count}/{max_follows} - {target_username}")
            
            # Very small delay between requests from same IP
            await asyncio.sleep(random.uniform(0.35, 0.9))

    def execute_follows(self, target_id, follow_count, tokens_data, target_username):
        completion_event = threading.Event()
        
        def run_async_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def main_async():
                stats = {"completed": 0}
                tasks = []
                
                # Much more conservative number of concurrent requests
                num_workers = min(6, follow_count, len(tokens_data))
                
                self._log(f"Starting {num_workers} concurrent follow workers (no proxies)")
                
                for _ in range(num_workers):
                    task = asyncio.create_task(
                        self._follow_worker(target_id, tokens_data, target_username, follow_count, stats)
                    )
                    tasks.append(task)
                
                await asyncio.gather(*tasks, return_exceptions=True)
                completion_event.set()
            
            try:
                loop.run_until_complete(main_async())
            except Exception as e:
                self._log(f"Error in async loop: {e}")
            finally:
                loop.close()
        
        threading.Thread(target=run_async_loop, daemon=True).start()
        return completion_event

    def start(self, username, count):
        if self.running:
            self._log("Follower is already running.")
            return

        self.running = True
        self._log(f"Starting follow operation for: {username}")
        self._log(f"Target follows: {count}")
        
        threading.Thread(target=self._run_operation, args=(username, count), daemon=True).start()

    def _run_operation(self, username, count):
        self._log(f"Fetching ID for {username}...")
        user_id = self.get_user_id(username)
        
        if not user_id:
            self._log(f"Failed to get ID for {username}")
            self.running = False
            return
        
        self._log(f"User ID: {user_id}")
        
        tokens = self._load_tokens()
        if not tokens:
            self._log("No valid tokens found in tokens.txt")
            self.running = False
            return
        
        self._log(f"Loaded {len(tokens)} tokens")
        self._log("IMPORTANT: Running WITHOUT proxies → very high risk of ban!")
        
        self._log("Starting follow process...")
        completion = self.execute_follows(user_id, count, tokens, username)
        
        completion.wait()
        self.running = False
        self._log("Follow operation finished.")

    def stop(self):
        self.running = False
        self._log("Stopping follow operation...")

if __name__ == "__main__":
    bot = TwitchFollower(print)
    
    print("Twitch Follower Bot (NO PROXIES version)")
    print("----------------------------------------")
    print("WARNING: Very high risk of account ban without proxies!\n")
    
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
