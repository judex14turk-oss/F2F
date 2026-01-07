# -*- coding: utf-8 -*-
"""
Тестирование нормализации 9-значных номеров
Проверяет, что 935 411 505 превращается в +998935411505
"""

import sys
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from olx_parser import OLXParser

print("=" * 70)
print("ТЕСТИРОВАНИЕ НОРМАЛИЗАЦИИ ТЕЛЕФОНОВ")
print("=" * 70)

parser = OLXParser()

test_cases = [
    ("935 411 505", "+998935411505"),
    ("93 541 15 05", "+998935411505"),
    ("935411505", "+998935411505"),
    ("+998 93 541 15 05", "+998935411505"),
    ("998 93 541 15 05", "+998935411505"),
    ("99 893 541 15 05", "+998935411505"), # С пробелом после 99
]

print(f"{'ВХОДНОЙ ТЕКСТ':<25} | {'ОЖИДАЕМЫЙ':<15} | {'ФАКТИЧЕСКИЙ':<15} | {'ИТОГ':<5}")
print("-" * 75)

for text, expected in test_cases:
    result = parser._extract_phone_from_text(f"звоните {text} жду")
    
    status = "OK" if result == expected else "FAIL"
    print(f"{text:<25} | {expected:<15} | {str(result):<15} | {status}")

print("-" * 75)
print("ГОТОВО")
