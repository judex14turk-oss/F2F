# -*- coding: utf-8 -*-
"""
Быстрый тест регулярных выражений для номера +99 893 1917777
БЕЗ запуска Selenium (чтобы не зависало)
"""

import re
import sys

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

# Реальный номер из объявления с террасой
test_phone = "+99 893 1917777"

print("=" * 60)
print("ТЕСТ РЕГУЛЯРНЫХ ВЫРАЖЕНИЙ")
print("=" * 60)
print(f"Проверяем номер: '{test_phone}'\n")

# Регулярки из olx_parser.py (строка 436)
phone_regexes = [
    (r'\+99[\s\-]?\d{2,3}[\s\-]?\d{3,7}[\s\-]?\d{0,4}', "Основная для +99"),
    (r'\+99\s+\d{3}\s+\d+', "С пробелами +99"),
    (r'\+998[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', "+998 формат"),
]

print("Проверяем каждое регулярное выражение:")
print("-" * 60)

for regex, description in phone_regexes:
    match = re.search(regex, test_phone)
    if match:
        matched_text = match.group(0)
        # Очищаем от пробелов
        cleaned = matched_text.replace(' ', '').replace('-', '')
        print(f"[OK] {description}")
        print(f"   Regex: {regex}")
        print(f"   Найдено: '{matched_text}' -> Очищено: '{cleaned}'")
        print(f"   Длина: {len(cleaned)}")
    else:
        print(f"[FAIL] {description}")
        print(f"   Regex: {regex}")
        print(f"   НЕ СОВПАЛ!")
    print()

# Проверим, что должно работать
print("=" * 60)
print("ИСПРАВЛЕННОЕ РЕГУЛЯРНОЕ ВЫРАЖЕНИЕ:")
print("=" * 60)

# Более гибкое регулярное выражение
new_regex = r'\+99[\s\-]?\d{1,3}[\s\-]?\d{3,9}[\s\-]?\d{0,7}'
match = re.search(new_regex, test_phone)
if match:
    matched = match.group(0)
    cleaned = matched.replace(' ', '').replace('-', '')
    print(f"[OK] Новое regex: {new_regex}")
    print(f"   Найдено: '{matched}' -> Очищено: '{cleaned}'")
else:
    print(f"[FAIL] Не работает")

print("\n" + "=" * 60)
print("ГОТОВО (БЕЗ SELENIUM - БЕЗОПАСНО)")
print("=" * 60)
