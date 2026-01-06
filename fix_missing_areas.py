"""
Скрипт для исправления площадей в существующих объявлениях OLX
"""
import os
import sys
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Проверяем DATABASE_URL
if not os.getenv('DATABASE_URL'):
    print("ERROR: DATABASE_URL not found in environment")
    print("Please set it in .env file or run this script with proper environment")
    sys.exit(1)

from models import SessionLocal, Property
from olx_parser import OLXParser

def fix_missing_areas():
    """Находит все OLX объявления без площади и перепарсивает их"""
    db = SessionLocal()
    
    # Находим все OLX объявления где area == None или area == 0
    properties_without_area = db.query(Property).filter(
        Property.source == 'olx',
        Property.olx_url != None,
        (Property.area == None) | (Property.area == 0)
    ).all()
    
    print(f"Found {len(properties_without_area)} properties without area")
    
    if len(properties_without_area) == 0:
        print("No properties to fix!")
        db.close()
        return
    
    parser = OLXParser()
    fixed_count = 0
    failed_count = 0
    
    for prop in properties_without_area:
        print(f"\nProcessing property ID {prop.id} (OLX: {prop.olx_id})...")
        print(f"  URL: {prop.olx_url}")
        
        try:
            # Парсим заново
            result = parser.parse_listing(prop.olx_url, get_phone=False)
            
            if result.get('error'):
                print(f"  ERROR: {result.get('error')}")
                failed_count += 1
                continue
            
            # Извлекаем площадь
            total_area_str = result.get('total_area')
            if total_area_str:
                try:
                    # Remove spaces and replace comma with dot
                    clean_area = str(total_area_str).replace(' ', '').replace(',', '.')
                    # Extract just the number if there's extra text
                    import re
                    match = re.search(r'([\d.]+)', clean_area)
                    if match:
                        area_val = float(match.group(1))
                    else:
                        area_val = float(clean_area)
                        
                    prop.area = area_val
                    print(f"  ✓ Updated area: {area_val} m² (raw: {total_area_str})")
                    fixed_count += 1
                except Exception as e:
                    print(f"  ✗ Failed to convert area: '{total_area_str}' - {e}")
                    failed_count += 1
                    failed_count += 1
            else:
                print(f"  ✗ Area not found in parsed data")
                failed_count += 1
                
        except Exception as e:
            print(f"  ERROR: {e}")
            failed_count += 1
    
    # Сохраняем изменения
    if fixed_count > 0:
        db.commit()
        print(f"\n✓ Successfully fixed {fixed_count} properties")
    
    if failed_count > 0:
        print(f"✗ Failed to fix {failed_count} properties")
    
    db.close()

if __name__ == '__main__':
    print("=" * 60)
    print("OLX Properties Area Fixer")
    print("=" * 60)
    fix_missing_areas()
    print("\nDone!")
