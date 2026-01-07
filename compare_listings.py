# -*- coding: utf-8 -*-
"""
Тест для сравнения двух объявлений - рабочего и нерабочего
"""

import sys
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from olx_parser import OLXParser

print("=" * 70)
print("СРАВНЕНИЕ РАБОЧЕГО И НЕРАБОЧЕГО ОБЪЯВЛЕНИЯ")
print("=" * 70)

parser = OLXParser()

urls = {
    "РАБОЧЕЕ": "https://www.olx.uz/d/obyavlenie/prodaetsya-3-h-komnatnaya-kvartira-v-sergeli-6-ID4c7w3.html",
    "НЕРАБОЧЕЕ": "https://www.olx.uz/d/obyavlenie/prodayu-kvartiru-novza-ID45tOy.html"
}

for label, url in urls.items():
    print(f"\n{'='*70}")
    print(f"{label}: {url[:50]}...")
    print(f"{'='*70}")
    
    # Сначала попробуем через requests (без Selenium)
    print("\\n[1] Парсинг через requests (без телефона):")
    try:
        result_req = parser.parse_listing_with_requests(url)
        print(f"  ✓ Заголовок: {result_req.get('title', 'N/A')[:50]}")
        print(f"  ✓ Цена: {result_req.get('price', 'N/A')}")
        print(f"  ✓ OLX ID: {result_req.get('olx_id', 'N/A')}")
        print(f"  ✓ Продавец: {result_req.get('seller_name', 'N/A')}")
        print(f"  ✓ Телефон: {result_req.get('phone', 'НЕТ')}")
    except Exception as e:
        print(f"  ✗ Ошибка: {e}")
    
    # Теперь через полный парсинг с телефоном
    print("\\n[2] Полный парсинг С телефоном (Selenium):")
    try:
        result_full = parser.parse_listing(url, get_phone=True)
        print(f"  ✓ Заголовок: {result_full.get('title', 'N/A')[:50]}")
        print(f"  ✓ Телефон: {result_full.get('phone', 'НЕТ')}")
        if result_full.get('phone_error'):
            print(f"  ⚠ Ошибка телефона: {result_full.get('phone_error')}")
        if result_full.get('error'):
            print(f"  ✗ Общая ошибка: {result_full.get('error')}")
    except Exception as e:
        print(f"  ✗ Ошибка: {e}")

print("\\n" + "=" * 70)
print("ТЕСТ ЗАВЕРШЕН")
print("=" * 70)
