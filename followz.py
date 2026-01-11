import json
import os
import random
import threading
import time
import aiohttp
import asyncio
import secrets

INTEGRITY_URL = "https://gql.twitch.tv/integrity"
GQL_URL = "https://gql.twitch.tv/gql"
CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

class TwitchFollower:
    def __init__(self, log_callback=print):
        self.log_callback = log_callback
        self.followed_records = {}
        self.lock = threading.Lock()
        self.running = False
        self.proxies = self._load_proxies()

    def _log(self, message):
        self.log_callback(message)

    def _load_proxies(self):
        proxies = []
        if os.path.exists("proxies.txt"):
            with open("proxies.txt", "r") as f:
                for line in f:
                    line = line.strip()
                    if line and '://' not in line:
                        line = f"http://{line}"
                    if line:
                        proxies.append(line)
        return proxies

    def _load_tokens(self):
        tokens = []
        if os.path.exists("tokens.txt"):
            with open("tokens.txt", "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        tokens.append(line)
        return tokens

    async def _get_integrity_token(self, session, payload_json):
        """
        Request an integrity token from Twitch's integrity endpoint.
        """
        device_id = secrets.token_hex(16)
        headers = {
            "Client-Id": CLIENT_ID,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-Device-Id": device_id
        }
        async with session.post(INTEGRITY_URL, headers=headers, data=payload_json) as response:
            if response.status == 200:
                data = await response.json()
                token = data.get("token")
                if token:
                    return token
        return None

    def get_user_id(self, user):
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

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(self._fetch_user_id_async(payload))
        loop.close()
        return result

    async def _fetch_user_id_async(self, payload_json):
        proxy_url = random.choice(self.proxies) if self.proxies else None
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            integrity_token = await self._get_integrity_token(session, payload_json)
            if not integrity_token:
                self._log("Failed to get integrity token")
                return False

            headers = {
                "Client-Id": CLIENT_ID,
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                "Authorization": f"OAuth {integrity_token}"
            }

            try:
                async with session.post(GQL_URL, headers=headers, data=payload_json, proxy=proxy_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data[0]["data"]["user"]["id"]
            except Exception as e:
                self._log(f"Error fetching user ID: {e}")
        return False

    async def _execute_follow_request(self, target_id, token):
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

        proxy_url = random.choice(self.proxies) if self.proxies else None
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            integrity_token = await self._get_integrity_token(session, payload)
            if not integrity_token:
                return False

            headers = {
                "Client-Id": CLIENT_ID,
                "Authorization": f"OAuth {token}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                "X-Device-Id": secrets.token_hex(16),
                "X-Integrity-Token": integrity_token
            }

            try:
                async with session.post(GQL_URL, headers=headers, data=payload, proxy=proxy_url) as response:
                    result_text = await response.text()
                    if response.status in (200, 204) and "errors" not in result_text.lower():
                        return True
            except Exception as e:
                self._log(f"Follow request failed: {e}")
        return False

    async def _follow_worker(self, target_id, tokens_list, max_follows, stats):
        while self.running and stats["completed"] < max_follows:
            with self.lock:
                unused_tokens = [
                    token for token in tokens_list
                    if token not in self.followed_records or target_id not in self.followed_records[token]
                ]
                if not unused_tokens:
                    break
                token = random.choice(unused_tokens)

            success = await self._execute_follow_request(target_id, token)
            if success:
                with self.lock:
                    stats["completed"] += 1
                    if token not in self.followed_records:
                        self.followed_records[token] = []
                    self.followed_records[token].append(target_id)
                    self._log(f"Followed {stats['completed']}/{max_follows}")
            await asyncio.sleep(random.uniform(0.1, 0.3))

    def execute_follows(self, target_id, follow_count, tokens_data):
        completion_event = threading.Event()

        def run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            stats = {"completed": 0}
            tasks = [loop.create_task(self._follow_worker(target_id, tokens_data, follow_count, stats))
                     for _ in range(min(50, follow_count, len(tokens_data)))]
            loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            completion_event.set()
            loop.close()

        threading.Thread(target=run_loop, daemon=True).start()
        return completion_event

    def start(self, username, count):
        if self.running:
            self._log("Follower already running")
            return
        self.running = True
        threading.Thread(target=self._run_operation, args=(username, count), daemon=True).start()

    def _run_operation(self, username, count):
        self._log(f"Fetching ID for {username}...")
        user_id = self.get_user_id(username)
        if not user_id:
            self._log("Failed to get user ID")
            self.running = False
            return

        tokens = self._load_tokens()
        if not tokens:
            self._log("No tokens found")
            self.running = False
            return

        self._log(f"Starting follow process for {count} follows")
        completion = self.execute_follows(user_id, count, tokens)
        completion.wait()
        self.running = False
        self._log("Follow operation finished")

    def stop(self):
        self.running = False
        self._log("Stopping operation")

if __name__ == "__main__":
    bot = TwitchFollower(print)
    username = input("Target username: ").strip()
    try:
        count = int(input("Number of follows: ").strip())
    except ValueError:
        count = 10
    bot.start(username, count)

    try:
        while bot.running:
            time.sleep(1)
    except KeyboardInterrupt:
        bot.stop()

