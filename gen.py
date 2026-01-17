import os
import re
import time
import random
import string
import threading
from os import system
from os.path import isfile, join
from colorama import Fore

import curl_cffi

class stats:
    created = 0
    errors  = 0 

class MailGW:
    def __init__(self):
        self.base_url = 'https://api.mail.gw'
        self.session = curl_cffi.requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.domain = self.get_domain() 

    def get_domain(self):
        try:
            response = self.session.get(self.base_url + '/domains')
            return response.json()['hydra:member'][0]['domain']
        except:
            return "mail.gw"

    def get_email(self):
        try:
            json = {
                'address': f"{''.join(random.choices('poiuytrewqlkjhgfdsamnbvcxzPOIUYTREWQMNBVCXZLKJHGFDSA0987654321', k=12))}@{self.domain}",
                'password': ''.join(random.choices('poiuytrewqlkjhgfdsamnbvcxzPOIUYTREWQMNBVCXZLKJHGFDSA0987654321', k=14))
            }
            x = self.session.post(self.base_url + '/accounts', json=json).json()
            return (x['id'], x['address'], json['password'])
        except:
            return (None, None, None)
    
    def get_token(self, email, password):
        try:
            json = {
                'address': email,
                'password': password
            }
            response = self.session.post(self.base_url + '/token', json=json)
            return response.json()['token']
        except:
            return False
    
    def get_messages(self, token):
        try:
            max_attempts = 10
            for _ in range(max_attempts):
                time.sleep(3)
                response = self.session.get(
                    self.base_url + '/messages',
                    headers={'Authorization': f'Bearer {token}'}
                )
                if response.status_code == 200 and 'hydra:member' in response.text:
                    messages = response.json()['hydra:member']
                    if messages and 'subject' in messages[0]:
                        subject = messages[0]['subject']
                        # Extract verification code from subject
                        numbers = re.findall(r'\d{6}', subject)
                        if numbers:
                            return numbers[0]
            return False
        except:
            return False

MailGw = MailGW()

class twitch:
    def __init__(self) -> None:
        self.session = curl_cffi.requests.Session()
        self.session.headers.update({
            'Accept': 'application/vnd.twitchtv.v3+json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
        })
        
    def get_format(self) -> bool:
        pattern = r'^(?:(?P<user>[^:@]+):(?P<pass>[^:@]+)@)?(?P<host>[^:]+):(?P<port>\d+)$'
        proxies = open('data/proxies.txt', 'r').read().splitlines()
        for proxy in proxies:
            match = re.match(pattern, proxy)
            if match:
                return True
            else:
                return False

    def get_username(self) -> str:
        try:
            username = self.session.get('https://names.drycodes.com/10').json()[0]
            headers = {
                'Accept': '*/*',
                'Accept-Language': 'en-GB',
                'Client-Id': 'kimne78kx3ncx6brgo4mv6wki5h1ko',
                'Content-Type': 'text/plain;charset=UTF-8',
                'Origin': 'https://www.twitch.tv',
                'Referer': 'https://www.twitch.tv/',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
            }
            
            json_data = [{
                "operationName": "UsernameValidator_User",
                "variables": {"username": username},
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "fd1085cf8350e309b725cf8ca91cd90cac03909a3edeeedbd0872ac912f3d660"
                    }
                }
            }]
            
            response = self.session.post(
                'https://gql.twitch.tv/gql', 
                json=json_data, 
                headers=headers,
                impersonate="chrome110"
            ).json()
            
            if response[0]['data']['isUsernameAvailable']:
                return username
            else:
                return username + ''.join(random.choices('poiuytrewqlkjhgfdsaamnbvcxz', k=3))
        except:
            return ''.join(random.choices('poiuytrewqlkjhgfdsaamnbvcxz', k=10))

    def get_data(self) -> tuple:
        username = self.get_username()
        password = ''.join(random.choices('poiuytrewqlkjhgfdsamnbvcxz0987654321', k=12))
        email = ''.join(random.choices('poiuytrewqlkjhgfdsamnbvcxz0987654321', k=10)) + random.choice(['@outlook.com', '@gmail.com', '@yahoo.com'])
        
        # Read proxies and select one
        try:
            with open('data/proxies.txt', 'r') as f:
                proxies = f.read().splitlines()
            proxy = random.choice(proxies) if proxies else None
        except:
            proxy = None
            
        return (username, password, email, proxy)
    
    def get_integrity_token(self, proxy: str) -> str:
        """Get integrity token using curl_cffi for better fingerprinting"""
        try:
            # Create a new session with specific browser fingerprint
            session = curl_cffi.requests.Session()
            
            # Android mobile headers
            headers = {
                "accept": "application/vnd.twitchtv.v3+json",
                "accept-encoding": "gzip",
                "accept-language": "en-us",
                "api-consumer-type": "mobile; Android/1403020",
                "client-id": "kd1unb4b3q4t58fwlpcbzcbnm76a8fp",
                "connection": "Keep-Alive",
                "content-length": "0",
                "host": "passport.twitch.tv",
                "user-agent": "Dalvik/2.1.0 (Linux; U; Android 7.1.2; SM-G965N Build/QP1A.190711.020) tv.twitch.android.app/14.3.2/1403020",
                "x-app-version": "14.3.2",
                "x-kpsdk-v": "a-1.6.0"
            }
            
            # Set up proxy if available
            proxies = None
            if proxy:
                proxies = {
                    'http': f'http://{proxy}',
                    'https': f'http://{proxy}'
                }
            
            # Use curl_cffi with Chrome impersonation for better success rate
            response = session.post(
                'https://passport.twitch.tv/integrity',
                headers=headers,
                proxies=proxies,
                impersonate="chrome110",
                timeout=30
            )
            
            if response.status_code == 200 and "token" in response.text:
                return response.json()['token']
            else:
                print(f"{Fore.BLUE}[ {Fore.YELLOW}! {Fore.BLUE}]{Fore.RESET} Integrity token failed: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"{Fore.BLUE}[ {Fore.RED}x {Fore.BLUE}]{Fore.RESET} Integrity error: {str(e)[:50]}")
            return None

    def changeBio(self, token: str, userId: str) -> None:
        try:
            quote_response = self.session.get('https://api.quotable.io/random')
            quote = quote_response.json()['content'] if quote_response.status_code == 200 else "Just a new Twitch user!"
            
            headers = {
                "accept": "application/vnd.twitchtv.v3+json",
                "accept-encoding": "gzip",
                "accept-language": "en-us",
                "api-consumer-type": "mobile; Android/1403020",
                "authorization": f"OAuth {token}",
                "client-id": "kd1unb4b3q4t58fwlpcbzcbnm76a8fp",
                "connection": "Keep-Alive",
                "content-type": "application/json",
                "host": "gql.twitch.tv",
                "user-agent": "Dalvik/2.1.0 (Linux; U; Android 7.1.2; SM-G965N Build/QP1A.190711.020) tv.twitch.android.app/14.3.2/1403020",
                "x-apollo-operation-id": "14396482e090e2bfc15a168f4853df5ccfefaa5b51278545d2a1a81ec9795aae",
                "x-apollo-operation-name": "UpdateUserDescriptionMutation",
                "x-app-version": "14.3.2",
            }
            
            json_data = [{
                "operationName": "UpdateUserDescriptionMutation",
                "variables": {
                    "userID": userId,
                    "newDescription": quote[:200]  # Limit to 200 chars
                },
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "14396482e090e2bfc15a168f4853df5ccfefaa5b51278545d2a1a81ec9795aae"
                    }
                }
            }]
            
            response = self.session.post(
                'https://gql.twitch.tv/gql', 
                json=json_data, 
                headers=headers,
                impersonate="chrome110"
            ).json()
            
            if 'data' in response[0] and response[0]['data']['updateUser']['error'] is None:
                print(f"{Fore.BLUE}[ {Fore.GREEN}+ {Fore.BLUE}]{Fore.RESET} Updated Bio {token[:15]}*****")
            else:
                print(f"{Fore.BLUE}[ {Fore.YELLOW}! {Fore.BLUE}]{Fore.RESET} Failed to Change Bio")
        except Exception as e:
            print(f"{Fore.BLUE}[ {Fore.RED}x {Fore.BLUE}]{Fore.RESET} Bio Error: {str(e)[:30]}")

    def createUpload(self, token: str, userID: str) -> str:
        try:
            headers = {
                "accept": "application/vnd.twitchtv.v3+json",
                "accept-encoding": "gzip",
                "accept-language": "en-us",
                "api-consumer-type": "mobile; Android/1403020",
                "authorization": f"OAuth {token}",
                "client-id": "kd1unb4b3q4t58fwlpcbzcbnm76a8fp",
                "connection": "Keep-Alive",
                "content-type": "application/json",
                "host": "gql.twitch.tv",
                "user-agent": "Dalvik/2.1.0 (Linux; U; Android 7.1.2; SM-G965N Build/QP1A.190711.020) tv.twitch.android.app/14.3.2/1403020",
                "x-apollo-operation-id": "4de617743abe2fedc733c0be56f435fc2ecb6f06d34ab1d0a44e9350a232190b",
                "x-apollo-operation-name": "CreateProfileImageUploadURL",
                "x-app-version": "14.3.2",
            }
            
            json_data = [{
                "operationName": "CreateProfileImageUploadURL",
                "variables": {
                    "input": {
                        "format": "PNG",
                        "userID": userID
                    }
                },
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "4de617743abe2fedc733c0be56f435fc2ecb6f06d34ab1d0a44e9350a232190b"
                    }
                }
            }]
            
            response = self.session.post(
                'https://gql.twitch.tv/gql', 
                json=json_data, 
                headers=headers,
                impersonate="chrome110"
            )
            return response.json()[0]['data']['createProfileImageUploadURL']['uploadURL']
        except:
            return None

    def sendUpload(self, token: str, userId: str) -> None:
        try:
            upload_url = self.createUpload(token, userId)
            if not upload_url:
                return
                
            rand_pic = random.choice([f for f in os.listdir("data/avatars/") if isfile(join("data/avatars/", f))])
            with open(f'data/avatars/{rand_pic}', 'rb') as f:
                data = f.read()
            
            headers = {
                "accept": "application/vnd.twitchtv.v3+json",
                "accept-encoding": "gzip",
                "accept-language": "en-us",
                "api-consumer-type": "mobile; Android/1403020",
                "client-id": "kd1unb4b3q4t58fwlpcbzcbnm76a8fp",
                "connection": "Keep-Alive",
                "content-type": "application/octet-stream",
                "host": "twitchuploadservice-infra-prod-us-ingest4069586c-608wwzuuil7q.s3-accelerate.amazonaws.com",
                "user-agent": "Dalvik/2.1.0 (Linux; U; Android 7.1.2; SM-G965N Build/QP1A.190711.020) tv.twitch.android.app/14.3.2/1403020",
                "x-app-version": "14.3.2",
            }
            
            response = self.session.put(upload_url, data=data, headers=headers)
            if response.status_code in [200, 201]:
                print(f"{Fore.BLUE}[ {Fore.GREEN}+ {Fore.BLUE}]{Fore.RESET} Updated Profile Image")
            else:
                print(f"{Fore.BLUE}[ {Fore.YELLOW}! {Fore.BLUE}]{Fore.RESET} Profile Image update failed")
        except Exception as e:
            print(f"{Fore.BLUE}[ {Fore.YELLOW}! {Fore.BLUE}]{Fore.RESET} Avatar Error: {str(e)[:30]}")

    def verify(self, email, token, userId, code):
        try:
            deviceId = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
            headers = {
                "accept": "application/vnd.twitchtv.v3+json",
                "accept-encoding": "gzip",
                "accept-language": "en-us",
                "api-consumer-type": "mobile; Android/1403020",
                "authorization": f"OAuth {token}",
                "client-id": "kd1unb4b3q4t58fwlpcbzcbnm76a8fp",
                "connection": "Keep-Alive",
                "content-type": "application/json",
                "host": "gql.twitch.tv",
                "user-agent": "Dalvik/2.1.0 (Linux; U; Android 7.1.2; SM-G965N Build/QP1A.190711.020) tv.twitch.android.app/14.3.2/1403020",
                "x-apollo-operation-id": "72babafce68ab9862b6e4067385397b5d70caf4c2b45566970f57e5184411649",
                "x-apollo-operation-name": "ValidateVerificationCode",
                "x-app-version": "14.3.2",
                "x-device-id": deviceId
            }
            
            json_data = [{
                "operationName": "ValidateVerificationCode",
                "variables": {
                    "input": {
                        "address": email,
                        "code": code,
                        "key": userId
                    }
                },
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "72babafce68ab9862b6e4067385397b5d70caf4c2b45566970f57e5184411649"
                    }
                }
            }]
            
            response = self.session.post(
                'https://gql.twitch.tv/gql', 
                json=json_data, 
                headers=headers,
                impersonate="chrome110"
            )
            
            result = response.json()[0]
            if 'data' in result and result['data']['validateVerificationCode']['request']['status'] == 'VERIFIED':
                print(f"{Fore.BLUE}[ {Fore.GREEN}+ {Fore.BLUE}]{Fore.RESET} Email Verified")
            else:
                print(f"{Fore.BLUE}[ {Fore.YELLOW}! {Fore.BLUE}]{Fore.RESET} Failed to verify email")
        except:
            print(f"{Fore.BLUE}[ {Fore.YELLOW}! {Fore.BLUE}]{Fore.RESET} Verification failed")

    def Gen(self) -> None:
        try:
            username, password, emaill, proxy = self.get_data()
            
            # Try to get temp email, fallback to generated email
            id, email, epassword = MailGw.get_email()
            if not email:
                email = emaill
                etoken = False
            else:
                etoken = MailGw.get_token(email, epassword)
            
            # Get integrity token
            integrity = self.get_integrity_token(proxy)
            
            if not integrity:
                stats.errors += 1
                print(f"{Fore.BLUE}[ {Fore.RED}x {Fore.BLUE}]{Fore.RESET} Failed to get integrity token")
                return
            
            # Prepare registration request
            headers = {
                "accept": "application/vnd.twitchtv.v3+json",
                "accept-encoding": "gzip",
                "accept-language": "en-us",
                "api-consumer-type": "mobile; Android/1403020",
                "client-id": "kd1unb4b3q4t58fwlpcbzcbnm76a8fp",
                "connection": "Keep-Alive",
                "content-type": "application/json; charset=UTF-8",
                "host": "passport.twitch.tv",
                "user-agent": "Dalvik/2.1.0 (Linux; U; Android 7.1.2; SM-G965N Build/QP1A.190711.020) tv.twitch.android.app/14.3.2/1403020",
                "x-app-version": "14.3.2",
                "x-device-id": ''.join(random.choices(string.ascii_letters + string.digits, k=32))
            }
            
            json_data = {
                "birthday": {
                    "day": random.randint(1, 28),
                    "month": random.randint(1, 12),
                    "year": random.randint(1960, 2005)
                },
                "client_id": "kd1unb4b3q4t58fwlpcbzcbnm76a8fp",
                "email": email,
                "include_verification_code": True,
                "integrity_token": integrity,
                "password": password,
                "username": username
            }
            
            # Set up proxy if available
            proxies = None
            if proxy:
                proxies = {
                    'http': f'http://{proxy}',
                    'https': f'http://{proxy}'
                }
            
            # Create session for registration
            reg_session = curl_cffi.requests.Session()
            response = reg_session.post(
                'https://passport.twitch.tv/protected_register',
                json=json_data,
                headers=headers,
                proxies=proxies,
                impersonate="chrome110",
                timeout=30
            )
            
            if response.status_code == 200 and 'access_token' in response.text:
                stats.created += 1
                token = response.json()['access_token']
                userID = response.json()['userID']
                
                # Save results
                os.makedirs('data/Results', exist_ok=True)
                
                with open('data/Results/tokens.txt', 'a') as f:
                    f.write(f"{token}\n")
                
                with open('data/Results/accounts.txt', 'a') as f:
                    f.write(f"{email}:{username}:{password}:{token}\n")
                
                print(f"{Fore.BLUE}[ {Fore.GREEN}+ {Fore.BLUE}]{Fore.RESET} Created {username} ({stats.created})")
                
                # Optional enhancements
                try:
                    self.changeBio(token, userID)
                    self.sendUpload(token, userID)
                    
                    if etoken:
                        code = MailGw.get_messages(etoken)
                        if code:
                            self.verify(email, token, userID, code)
                except:
                    pass
                    
            else:
                stats.errors += 1
                print(f"{Fore.BLUE}[ {Fore.RED}x {Fore.BLUE}]{Fore.RESET} Registration failed: {response.status_code}")
                
        except Exception as e:
            stats.errors += 1
            print(f"{Fore.BLUE}[ {Fore.RED}x {Fore.BLUE}]{Fore.RESET} Error: {str(e)[:50]}")

# Main execution
system('cls' if os.name == 'nt' else 'clear')

# Check for required files
if not os.path.exists('data/proxies.txt'):
    print(f"{Fore.BLUE}[ {Fore.RED}x {Fore.BLUE}]{Fore.RESET} proxies.txt not found in data/ folder")
    exit(1)

if twitch().get_format() == False:
    print(f"{Fore.BLUE}[ {Fore.RED}x {Fore.BLUE}]{Fore.RESET} Invalid Proxy Format\n Use user:pass@host:port")
else:
    try:
        threads = int(input(f"{Fore.BLUE}[ {Fore.YELLOW}> {Fore.BLUE}]{Fore.RESET} Threads: "))
        
        print(f"\n{Fore.CYAN}Starting account creation...{Fore.RESET}")
        print(f"{Fore.CYAN}Using curl_cffi with browser fingerprinting{Fore.RESET}\n")
        
        for i in range(threads):
            threading.Thread(target=twitch().Gen, daemon=True).start()
            time.sleep(0.5)  # Stagger thread starts
        
        # Keep main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Stopped by user{Fore.RESET}")
        print(f"{Fore.CYAN}Total created: {stats.created}{Fore.RESET}")
        print(f"{Fore.CYAN}Total errors: {stats.errors}{Fore.RESET}")
    except ValueError:
        print(f"{Fore.RED}Please enter a valid number for threads{Fore.RESET}")
