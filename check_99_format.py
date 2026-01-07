# -*- coding: utf-8 -*-
"""
Проверка номера 99 890 6867777 (без плюса)
"""

import sys
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from olx_parser import OLXParser
import re

print("=" * 70)
print("ДЕТАЛЬНАЯ ПРОВЕРКА: 99 890 6867777")
print("=" * 70)

parser = OLXParser()

# Тест через функцию
text_with_phone = "Контакт: 99 890 6867777"
result = parser._extract_phone_from_text(text_with_phone)
print(f"\nРезультат parser._extract_phone_from_text():")
print(f"  Входной текст: '{text_with_phone}'")
print(f"  Результат: {result}")

# Проверяем каждый паттерн отдельно
print("\n" + "=" * 70)
print("ПРОВЕРКА КАЖДОГО ПАТТЕРНА:")
print("=" * 70)

phone_patterns = [
    (r'\+998[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', "+998 формат"),
    (r'\+998\d{9}', "+998 слитно"),
    (r'\+99[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{4}', "+99 гибкий"),
    (r'998[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', "998 формат"),
    (r'998\d{9}', "998 слитно"),
    (r'(?:^|[^\d])([89]\d{8})(?:[^\d]|$)', "8/9 + 8 цифр"),
    (r'(?:^|[^\d])(9\d{8})(?:[^\d]|$)', "9 + 8 цифр"),
    (r'\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', "2-3-2-2 формат"),
    (r'\d{3}[\s\-]\d{3}[\s\-]\d{3}', "3-3-3 формат"),
]

for pattern, description in phone_patterns:
    match = re.search(pattern, text_with_phone)
    if match:
        matched = match.group(1) if match.lastindex else match.group(0)
        cleaned = matched.replace(' ', '').replace('-', '')
        print(f"\n[НАЙДЕНО] {description}")
        print(f"  Паттерн: {pattern}")
        print(f"  Совпадение: '{matched}'")
        print(f"  После очистки: '{cleaned}' (длина: {len(cleaned)})")
        
        # Применяем логику нормализации
        phone = cleaned
        if len(phone) == 9:
            normalized = '+998' + phone
        elif len(phone) == 12 and phone.startswith('998'):
            normalized = '+' + phone
        elif not phone.startswith('+'):
            normalized = '+' + phone
        else:
            normalized = phone
        print(f"  Нормализовано: '{normalized}'")

print("\n" + "=" * 70)
print("ВЫВОД:")
print("=" * 70)
if result:
    print(f"✅ Номер извлечён: {result}")
else:
    print("❌ Номер НЕ извлечён")
    print("\nПРИЧИНА: Формат '99 890 6867777' (без +) не соответствует паттернам")
    print("РЕШЕНИЕ: На OLX обычно номера отображаются в href как 'tel:998...'")
    print("          что парсер обработает корректно → +998906867777")
