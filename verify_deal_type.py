
from olx_parser import OLXParser

url = "https://www.olx.uz/d/obyavlenie/sdaetsya-2-h-kom-3-5-kvartira-ID4fHQr.html"
parser = OLXParser()

print(f"Parsing: {url}")
result = parser.parse_listing(url, get_phone=False)

print("\n--- Result ---")
print(f"Title: {result.get('title')}")
print(f"Deal Type: {result.get('deal_type')}")

if result.get('deal_type') == 'rent':
    print("\nSUCCESS: Deal type correctly identified as 'rent'")
else:
    print(f"\nFAILURE: Deal type identified as '{result.get('deal_type')}', expected 'rent'")
