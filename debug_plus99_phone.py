# -*- coding: utf-8 -*-
"""
Тест для номера в формате +99 890 6867777
"""

import sys
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from olx_parser import OLXParser

print("=" * 70)
print("ТЕСТИРОВАНИЕ ФОРМАТА +99 890 6867777")
print("=" * 70)

parser = OLXParser()

test_cases = [
    ("+99 890 6867777", "+998906867777"),  # Пробел после 99
    ("+998 90 6867777", "+998906867777"),  # Обычный формат
    ("+998906867777", "+998906867777"),    # Без пробелов
    ("99 890 6867777", "+998906867777"),   # Без плюса
]

print(f"{'ВХОДНОЙ ТЕКСТ':<25} | {'ОЖИДАЕМЫЙ':<15} | {'ФАКТИЧЕСКИЙ':<15} | {'ИТОГ':<5}")
print("-" * 75)

for text, expected in test_cases:
    result = parser._extract_phone_from_text(f"звоните {text} ждем")
    
    status = "OK" if result == expected else "FAIL"
    actual = str(result) if result else "None"
    print(f"{text:<25} | {expected:<15} | {actual:<15} | {status}")

print("-" * 75)

# Детальная проверка проблемного номера
print("\nДетальная проверка: +99 890 6867777")
print("=" * 70)

import re

text = "Контакт: +99 890 6867777"
phone_patterns = [
    r'\+998[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
    r'\+998\d{9}',
    r'\+99[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{4}',
    r'\+99[\s\-]?\d{2,3}[\s\-]?\d{3,7}[\s\-]?\d{0,4}',
    r'\d{3}[\s\-]\d{3}[\s\-]\d{3}',
]

for i, pattern in enumerate(phone_patterns, 1):
    match = re.search(pattern, text)
    if match:
        matched = match.group(0)
        cleaned = matched.replace(' ', '').replace('-', '')
        print(f"Паттерн #{i}: НАЙДЕНО")
        print(f"  Regex: {pattern}")
        print(f"  Совпадение: '{matched}'")
        print(f"  После очистки: '{cleaned}' (длина: {len(cleaned)})")
        print()

print("ГОТОВО")
