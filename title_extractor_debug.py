import requests
from bs4 import BeautifulSoup
import json
import sys

def test_title_extraction(url):
    print(f"Testing URL: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        print(f"Response Encoding: {response.encoding}")
        print(f"Apparent Encoding: {response.apparent_encoding}")
        
        # Test olx_parser approach
        content_decoded = response.content.decode('utf-8', errors='ignore')
        soup = BeautifulSoup(content_decoded, 'lxml')
        
        # New logic from olx_parser.py
        print("\n--- Testing final logic ---")
        title_selectors = [
            {'data-cy': 'ad_title'},
            {'data-cy': 'offer_title'},
            {'data-testid': 'offer_title'}
        ]
        found = False
        for selector in title_selectors:
            title_el = soup.find(attrs=selector)
            if title_el:
                print(f"Matched selector: {selector}")
                h_tag = title_el.find(['h1', 'h4'])
                if h_tag:
                    text = h_tag.get_text(strip=True)
                    print(f"Result (h-tag): {text}")
                    print(f"Raw bytes: {text.encode('utf-8')}")
                else:
                    text = title_el.get_text(strip=True)
                    print(f"Result (direct): {text}")
                    print(f"Raw bytes: {text.encode('utf-8')}")
                found = True
                break
        
        if not found:
            print("Failed with new data-cy selectors")
            for h4 in soup.find_all('h4'):
                text = h4.get_text(strip=True)
                if text and len(text) > 8:
                    print(f"Fallback H4 match candidate: {text}")

        # 5. Look for specific OLX classes (like css-1juy9zj)
        print("[Classes] Searching for titles...")
        for h in soup.find_all(['h1', 'h4']):
            text = h.get_text(strip=True)
            print(f"  - Tag {h.name}, Classes: {h.get('class')}, Text: {text[:20]}...")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_url = "https://www.olx.uz/d/obyavlenie/sdaetsya-3-h-komnatnaya-kvartira-ID3RZHh.html" # Dummy URL to see common structure
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
    test_title_extraction(test_url)
