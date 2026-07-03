import time
import json
import os
import requests
from bs4 import BeautifulSoup

def fetch_accepted(handle, after_id=None):
    """
    Fetches all accepted submissions for the given Codeforces handle.
    Filters by verdict == "OK" and id > after_id.
    Returns the submissions sorted by ID in ascending order (oldest first).
    """
    url = f"https://codeforces.com/api/user.status?handle={handle}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch user status from Codeforces API. Status code: {response.status_code}")
        
    data = response.json()
    if data.get("status") != "OK":
        raise Exception(f"Codeforces API error: {data.get('comment', 'Unknown error')}")
        
    submissions = data.get("result", [])
    accepted = []
    
    for sub in submissions:
        if sub.get("verdict") == "OK":
            sub_id = sub.get("id")
            if after_id is None or sub_id > after_id:
                accepted.append(sub)
                
    # Sort oldest first (ascending order of submission ID)
    accepted.sort(key=lambda s: s["id"])
    return accepted

class CodeforcesScraper:
    """
    Handles stealth browser automation to authenticate and scrape Codeforces submission source codes.
    Reuses a single Chrome instance with cookies to speed up scraping.
    """
    def __init__(self, cookies_path):
        self.cookies_path = cookies_path
        self.driver = None

    def start(self):
        import undetected_chromedriver as uc
        print("[cf_fetcher] Starting stealth Chrome browser...")
        options = uc.ChromeOptions()
        # headful is safer for Cloudflare Turnstile, minimize window to keep it unobtrusive
        options.add_argument('--window-size=900,700')
        
        self.driver = uc.Chrome(options=options, version_main=149)
        self.driver.get("https://codeforces.com")
        time.sleep(2)
        
        # Load and set cookies if they exist
        if os.path.exists(self.cookies_path):
            print("[cf_fetcher] Loading saved login cookies...")
            with open(self.cookies_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            for cookie in cookies:
                self.driver.add_cookie(cookie)
            # Reload to authenticate
            self.driver.get("https://codeforces.com")
            time.sleep(2)
        else:
            self.login_manually()

    def login_manually(self):
        print("\n*** ACTION REQUIRED ***")
        print("Please log in to your Codeforces account in the browser window.")
        print("Press Enter in the console once you are logged in successfully and see the home page...")
        self.driver.get("https://codeforces.com/enter")
        input()
        
        # Capture and save cookies
        cookies = self.driver.get_cookies()
        os.makedirs(os.path.dirname(self.cookies_path), exist_ok=True)
        with open(self.cookies_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f)
        print("[cf_fetcher] Login cookies captured and saved.")

    def get_code(self, contest_id, submission_id):
        url = f"https://codeforces.com/contest/{contest_id}/submission/{submission_id}"
        self.driver.get(url)
        time.sleep(3.5) # Wait for page load and Cloudflare bypass
        
        html = self.driver.page_source
        
        # Check if we were redirected to login page or home page
        if "program-source" not in html:
            if "enter" in self.driver.current_url or "login" in html.lower() or self.driver.current_url == "https://codeforces.com/":
                print("[cf_fetcher] Session expired or invalid. Re-authenticating...")
                self.login_manually()
                # Retry loading the page
                self.driver.get(url)
                time.sleep(4)
                html = self.driver.page_source

        # Extract code from the page
        if "program-source" in html:
            soup = BeautifulSoup(html, "html.parser")
            code_elem = soup.find("pre", class_="program-source")
            if code_elem:
                return code_elem.text
                
        raise Exception(f"Could not retrieve source code for submission {submission_id} from {url}")

    def stop(self):
        if self.driver:
            print("[cf_fetcher] Closing Chrome browser...")
            try:
                self.driver.quit()
            except Exception:
                pass
