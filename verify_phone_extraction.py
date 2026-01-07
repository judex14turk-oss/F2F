# -*- coding: utf-8 -*-
"""
Тестирование исправления парсинга телефона
URL: https://www.olx.uz/d/obyavlenie/kvartira-s-terrasoy-ot-sobstvennika-ID5pVrl.html
OLX ID: 59518212
Ожидаемый телефон: +998931917777 (или +99 893 1917777)
"""

import sys
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from olx_parser import OLXParser

URL = "https://www.olx.uz/d/obyavlenie/kvartira-s-terrasoy-ot-sobstvennika-ID5pVrl.html"

print("=" * 70)
print("ТЕСТИРОВАНИЕ ПАРСИНГА КВАРТИРЫ С ТЕРРАСОЙ")
print("=" * 70)
print(f"URL: {URL}")
print()

parser = OLXParser()

print("[1] Тест БЕЗ запроса телефона (requests only)...")
print("-" * 70)
result1 = parser.parse_listing(URL, get_phone=False)

print(f"Заголовок: {result1.get('title')}")
print(f"OLX ID: {result1.get('olx_id')}")
print(f"Цена: {result1.get('price')} {result1.get('currency')}")
print(f"Телефон: {result1.get('phone')}")
print(f"Описание (100 символов): {result1.get('description')[:100] if result1.get('description') else 'N/A'}...")
print(f"Ошибка: {result1.get('error')}")
print()

print("=" * 70)
print("[2] Тест С запросом телефона (Selenium + requests)...")
print("-" * 70)
print("ВНИМАНИЕ: Это может занять 20-30 секунд...")
print()

result2 = parser.parse_listing(URL, get_phone=True)

print(f"Заголовок: {result2.get('title')}")
print(f"OLX ID: {result2.get('olx_id')}")
print(f"Цена: {result2.get('price')} {result2.get('currency')}")
print(f"Телефон: {result2.get('phone')}")
print(f"Имя продавца: {result2.get('seller_name')}")
print(f"Ошибка: {result2.get('error')}")
print(f"Ошибка телефона: {result2.get('phone_error')}")
print()

print("=" * 70)
print("РЕЗУЛЬТАТЫ:")
print("=" * 70)

if result2.get('phone'):
    print(f"[OK] Телефон УСПЕШНО извлечён: {result2.get('phone')}")
    if result2.get('phone') in ['+998931917777', '+99 893 1917777', '+99893 1917777']:
        print("[OK] Номер соответствует ожидаемому!")
    else:
        print(f"[WARNING] Номер не соответствует ожидаемому: +998931917777")
else:
    print("[FAIL] Телефон НЕ извлечён")
    print(f"Причина: {result2.get('phone_error') or result2.get('error') or 'Неизвестно'}")

print()
print("=" * 70)
print("ГОТОВО")
print("=" * 70)
