
import requests
from bs4 import BeautifulSoup

url = "https://www.olx.uz/d/obyavlenie/sdaetsya-2-h-kom-3-5-kvartira-ID4fHQr.html"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}

try:
    response = requests.get(url, headers=headers)
    print(f"Status Code: {response.status_code}")
    
    soup = BeautifulSoup(response.text, 'lxml')
    
    # 1. Check Breadcrumbs
    breadcrumbs = soup.find_all('ol', {'data-testid': 'breadcrumbs'})
    if breadcrumbs:
        print("\n--- Breadcrumbs ---")
        print(breadcrumbs[0].get_text(separator=' > ', strip=True))
    else:
        # Try generic classes for breadcrumbs
        print("\nGeneric Breadcrumbs search:")
        for ol in soup.find_all('ol'):
            print(ol.get_text(separator=' > ', strip=True))

    # 2. Check Parameters/Attributes
    print("\n--- Parameters with 'Аренда' or 'Продажа' ---")
    text = soup.get_text()
    if 'Аренда' in text:
        print("Found 'Аренда' in page text")
    if 'Продажа' in text:
        print("Found 'Продажа' in page text")
        
    # Check specific parameter containers usually found in OLX
    # Look for 'Тип сделки'
    print("\n--- Searching for 'Тип сделки' ---")
    import re
    match = re.search(r'Тип сделки[:\s]+(.+?)(\n|$)', text)
    if match:
        print(f"Found match: {match.group(0)}")

except Exception as e:
    print(f"Error: {e}")
