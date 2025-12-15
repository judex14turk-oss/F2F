import re
import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import json
from datetime import datetime, timedelta, timezone


class OLXParser:
    BASE_URL = "https://www.olx.uz"
    
    DEAL_TYPES = {
        'sale': 'prodazha',
        'rent': 'dolgosrochnaya-arenda'
    }
    
    PROPERTY_TYPES = {
        'apartment': 'kvartiry',
        'land': 'zemelnye-uchastki',
        'house': 'doma'
    }
    
    TASHKENT_DISTRICTS = {
        'all': '',
        'bektemir': 'Бектемирский',
        'chilanzar': 'Чиланзарский',
        'yakkasaray': 'Яккасарайский',
        'yunusabad': 'Юнусабадский',
        'mirzo_ulugbek': 'Мирзо-Улугбекский',
        'mirabad': 'Мирабадский',
        'sergeli': 'Сергелийский',
        'shaykhantakhur': 'Шайхантахурский',
        'uchtepa': 'Учтепинский',
        'yashnabad': 'Яшнабадский',
        'olmazor': 'Олмазорский'
    }
    
    DISTRICT_IDS = {
        'all': None,
        'bektemir': 15,
        'chilanzar': 17,
        'yakkasaray': 24,
        'yunusabad': 25,
        'mirzo_ulugbek': 19,
        'mirabad': 18,
        'sergeli': 20,
        'shaykhantakhur': 21,
        'uchtepa': 22,
        'yashnabad': 23,
        'olmazor': 16
    }
    
    ROOMS = {
        '1': '1',
        '2': '2',
        '3': '3',
        '4': '4',
        '5+': '5'
    }

    HOUSING_TYPES = {
        'all': '',
        'new': 'Новостройка',
        'secondary': 'Вторичный рынок'
    }
    
    RUSSIAN_MONTHS = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
        'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
        'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
    }
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        }
        
    def get_driver(self):
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument(f'user-agent={self.headers["User-Agent"]}')
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(15)
            return driver
        except Exception as e:
            print(f"Error creating driver: {e}")
            return None
    
    def build_category_url(self, deal_type='sale', property_type='apartment', district='all', rooms=None, housing_type='all', page=1):
        deal = self.DEAL_TYPES.get(deal_type, 'prodazha')
        prop = self.PROPERTY_TYPES.get(property_type, 'kvartiry')
        
        url = f"{self.BASE_URL}/nedvizhimost/{prop}/{deal}/tashkent/"
        
        params = []
        
        if district and district != 'all':
            district_id = self.DISTRICT_IDS.get(district)
            if district_id:
                params.append(f"search[district_id]={district_id}")
        
        if rooms and property_type == 'apartment':
            params.append(f"search[filter_float_number_of_rooms:from]={rooms}")
            params.append(f"search[filter_float_number_of_rooms:to]={rooms}")
        
        if housing_type and housing_type != 'all' and property_type == 'apartment':
            housing = self.HOUSING_TYPES.get(housing_type, '')
            if housing:
                params.append(f"search[filter_enum_flat_type][0]={housing_type}")
        
        if page > 1:
            params.append(f"page={page}")
        
        if params:
            url += "?" + "&".join(params)
        
        return url
    
    def filter_by_district(self, listings, district):
        if not district or district == 'all':
            return listings
        
        district_name = self.TASHKENT_DISTRICTS.get(district, '')
        if not district_name:
            return listings
        
        filtered = []
        for listing in listings:
            location = listing.get('location', '') or ''
            parsed_district = listing.get('district', '') or ''
            if district_name in location or district_name in parsed_district:
                filtered.append(listing)
        
        return filtered
    
    def get_listings_from_category(self, deal_type='sale', property_type='apartment', 
                                    district='all', rooms=None, housing_type='all', 
                                    max_pages=3, max_listings=50):
        listings = []
        seen_urls = set()
        
        driver = self.get_driver()
        if not driver:
            print("Failed to initialize browser for category listing")
            return listings
        
        try:
            for page in range(1, max_pages + 1):
                if len(listings) >= max_listings:
                    break
                    
                url = self.build_category_url(deal_type, property_type, district, rooms, housing_type, page)
                print(f"Fetching page {page}: {url}")
                
                try:
                    driver.get(url)
                    time.sleep(3)
                    
                    for _ in range(3):
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1)
                    
                    page_source = driver.page_source
                    soup = BeautifulSoup(page_source, 'lxml')
                    
                    listing_links = soup.find_all('a', href=lambda x: x and '/d/obyavlenie/' in x if x else False)
                    
                    page_count = 0
                    for link in listing_links:
                        href = link.get('href', '')
                        if href.startswith('/'):
                            href = self.BASE_URL + href
                        
                        if href not in seen_urls and '/d/obyavlenie/' in href:
                            seen_urls.add(href)
                            if len(listings) < max_listings:
                                listings.append(href)
                                page_count += 1
                    
                    print(f"Page {page}: found {page_count} new listings, total: {len(listings)}")
                    
                    if page_count == 0:
                        print(f"No listings found on page {page}, stopping")
                        break
                    
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"Error fetching page {page}: {e}")
                    break
        finally:
            driver.quit()
        
        return listings
    
    def parse_listing_with_driver(self, driver, url, get_phone=False):
        result = {
            'url': url,
            'title': None,
            'price': None,
            'currency': None,
            'phone': None,
            'photos': [],
            'property_type': None,
            'rooms': None,
            'total_area': None,
            'floor': None,
            'total_floors': None,
            'layout': None,
            'bathroom': None,
            'furnished': None,
            'nearby': [],
            'commission': None,
            'description': None,
            'location': None,
            'district': None,
            'seller_name': None,
            'olx_id': None,
            'published_date': None,
            'error': None
        }
        
        try:
            try:
                driver.get(url)
            except TimeoutException:
                result['error'] = 'Page load timeout'
                return result
            time.sleep(1)
            
            if get_phone:
                try:
                    phone_buttons = driver.find_elements(By.XPATH, 
                        "//button[contains(text(), 'Показать') or contains(text(), 'показать') or contains(text(), 'телефон')]")
                    
                    for btn in phone_buttons:
                        try:
                            btn.click()
                            time.sleep(1.5)
                            break
                        except:
                            continue
                    
                    phone_elements = driver.find_elements(By.XPATH, "//a[starts-with(@href, 'tel:')]")
                    if phone_elements:
                        phone_href = phone_elements[0].get_attribute('href')
                        result['phone'] = phone_href.replace('tel:', '').strip()
                        
                except Exception as e:
                    result['phone_error'] = str(e)
            
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'lxml')
            
            result['title'] = self._extract_title(soup)
            result['price'], result['currency'] = self._extract_price(soup)
            result['photos'] = self._extract_photos(soup)
            result['olx_id'] = self._extract_olx_id(soup, url)
            result['description'] = self._extract_description(soup)
            result['location'] = self._extract_location(soup)
            result['seller_name'] = self._extract_seller(soup)
            result['published_date'] = self._extract_date(soup)
            
            params = self._extract_parameters(soup)
            result['property_type'] = params.get('Тип жилья')
            result['rooms'] = params.get('Количество комнат')
            result['total_area'] = params.get('Общая площадь')
            result['floor'] = params.get('Этаж')
            result['total_floors'] = params.get('Этажность дома')
            result['layout'] = params.get('Планировка')
            result['bathroom'] = params.get('Санузел')
            result['furnished'] = params.get('Меблирована')
            result['nearby'] = params.get('Рядом есть', '').split(', ') if params.get('Рядом есть') else []
            result['commission'] = params.get('Комиссионные')
            result['building_type'] = params.get('Тип строения')
            result['renovation'] = params.get('Ремонт')
            
            for district_key, district_name in self.TASHKENT_DISTRICTS.items():
                if district_name and district_name in (result['location'] or ''):
                    result['district'] = district_name
                    break
            
        except Exception as e:
            result['error'] = str(e)
            
        return result
    
    def parse_listing(self, url, get_phone=False):
        driver = self.get_driver()
        if not driver:
            return {'url': url, 'error': 'Failed to initialize browser'}
        
        try:
            return self.parse_listing_with_driver(driver, url, get_phone)
        finally:
            driver.quit()
    
    def parse_listing_with_phone(self, url):
        return self.parse_listing(url, get_phone=True)
    
    def bulk_parse(self, deal_type='sale', property_type='apartment', district='all',
                   rooms=None, housing_type='all', max_pages=2, max_listings=20, 
                   get_phone=False, progress_callback=None, max_days=None):
        
        results = []
        skipped_old = 0
        skipped_district = 0
        
        fetch_multiplier = 2 if max_days else 1.5
        if district and district != 'all':
            fetch_multiplier = 3
        fetch_limit = int(max_listings * fetch_multiplier)
        fetch_pages = max(max_pages, (fetch_limit // 40) + 1)
        
        listing_urls = self.get_listings_from_category(
            deal_type=deal_type,
            property_type=property_type,
            district=district,
            rooms=rooms,
            housing_type=housing_type,
            max_pages=fetch_pages,
            max_listings=fetch_limit
        )
        
        total = len(listing_urls)
        district_name = self.TASHKENT_DISTRICTS.get(district, '') if district else ''
        
        driver = self.get_driver()
        if not driver:
            return {
                'total_found': total,
                'parsed': 0,
                'skipped_old': 0,
                'skipped_district': 0,
                'filters': {
                    'deal_type': deal_type,
                    'property_type': property_type,
                    'district': district,
                    'rooms': rooms,
                    'housing_type': housing_type,
                    'max_days': max_days
                },
                'listings': [],
                'error': 'Failed to initialize browser'
            }
        
        try:
            for i, url in enumerate(listing_urls):
                if len(results) >= max_listings:
                    break
                    
                if progress_callback:
                    progress_callback(i + 1, total, url)
                
                try:
                    data = self.parse_listing_with_driver(driver, url, get_phone)
                    
                    if max_days and not self.is_listing_fresh(data.get('published_date'), max_days):
                        skipped_old += 1
                        continue
                    
                    if district and district != 'all' and district_name:
                        location = data.get('location', '') or ''
                        parsed_district = data.get('district', '') or ''
                        if district_name not in location and district_name not in parsed_district:
                            skipped_district += 1
                            continue
                    
                    results.append(data)
                    
                    time.sleep(0.3)
                    
                except Exception as e:
                    results.append({
                        'url': url,
                        'error': str(e)
                    })
        finally:
            driver.quit()
        
        return {
            'total_found': total,
            'parsed': len(results),
            'skipped_old': skipped_old,
            'skipped_district': skipped_district,
            'filters': {
                'deal_type': deal_type,
                'property_type': property_type,
                'district': district,
                'rooms': rooms,
                'housing_type': housing_type,
                'max_days': max_days
            },
            'listings': results
        }
    
    def _extract_title(self, soup):
        title_el = soup.find('h1') or soup.find('h4')
        return title_el.get_text(strip=True) if title_el else None
    
    def _extract_price(self, soup):
        # Ищем цену в JSON-LD данных (самый надёжный способ)
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    # Проверяем offers.price
                    if 'offers' in data:
                        offers = data['offers']
                        if isinstance(offers, dict) and 'price' in offers:
                            price = str(offers['price'])
                            currency = offers.get('priceCurrency', 'у.е.')
                            if price and price != '0':
                                return price, currency
                    # Проверяем прямое поле price
                    if 'price' in data:
                        price = str(data['price'])
                        if price and price != '0':
                            return price, data.get('priceCurrency', 'у.е.')
            except:
                pass
        
        # Ищем в data-testid элементах
        price_container = soup.find(attrs={'data-testid': 'ad-price-container'})
        if price_container:
            price_text = price_container.get_text(strip=True)
            numbers = re.findall(r'[\d\s]+', price_text)
            if numbers:
                price = numbers[0].replace(' ', '').strip()
                if price and len(price) > 1:  # Игнорируем однозначные числа
                    currency = price_text.replace(numbers[0], '').strip()
                    return price, currency
        
        # Ищем h3 с ценой (проверяем что это действительно цена)
        for h3 in soup.find_all('h3'):
            price_text = h3.get_text(strip=True)
            # Проверяем что это похоже на цену (содержит валюту или большое число)
            if any(curr in price_text for curr in ['у.е.', '$', 'USD', 'сум', 'UZS']):
                numbers = re.findall(r'[\d\s]+', price_text)
                if numbers:
                    price = numbers[0].replace(' ', '').strip()
                    if price and len(price) > 1:
                        currency = price_text.replace(numbers[0], '').strip()
                        return price, currency
            # Или если число достаточно большое (более 3 цифр)
            numbers = re.findall(r'[\d\s]+', price_text)
            if numbers:
                price = numbers[0].replace(' ', '').strip()
                if price and len(price) >= 3:
                    currency = price_text.replace(numbers[0], '').strip() or 'у.е.'
                    return price, currency
        
        return None, None
    
    def _extract_photos(self, soup):
        photos = []
        img_tags = soup.find_all('img')
        for img in img_tags:
            src = img.get('src', '')
            if 'apollo.olxcdn.com' in src or 'olxcdn.com' in src:
                high_res = re.sub(r';s=\d+x\d+', ';s=1920x1080', src)
                if high_res not in photos:
                    photos.append(high_res)
        
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and 'image' in data:
                    images = data['image'] if isinstance(data['image'], list) else [data['image']]
                    for img in images:
                        if img and img not in photos:
                            photos.append(img)
            except:
                pass
                
        return photos
    
    def _extract_parameters(self, soup):
        params = {}
        all_text = soup.get_text()
        
        keywords = ['Тип жилья', 'Количество комнат', 'Общая площадь', 'Этаж', 'Этажность дома',
                    'Планировка', 'Санузел', 'Меблирована', 'Рядом есть', 'Комиссионные',
                    'Тип строения', 'Ремонт', 'Год постройки', 'Высота потолков', 'В квартире есть']
        keyword_pattern = '|'.join(keywords)
        
        patterns = [
            (rf'Тип жилья[:\s]+(.+?)(?={keyword_pattern}|$)', 'Тип жилья'),
            (r'Количество комнат[:\s]+(\d+)', 'Количество комнат'),
            (r'Общая площадь[:\s]+(\d+)', 'Общая площадь'),
            (r'Этаж[:\s]+(\d+)', 'Этаж'),
            (r'Этажность дома[:\s]+(\d+)', 'Этажность дома'),
            (rf'Планировка[:\s]+(.+?)(?={keyword_pattern}|$)', 'Планировка'),
            (rf'Санузел[:\s]+(.+?)(?={keyword_pattern}|$)', 'Санузел'),
            (r'Меблирована[:\s]+(Да|Нет)', 'Меблирована'),
            (rf'Рядом есть[:\s]+(.+?)(?={keyword_pattern}|$)', 'Рядом есть'),
            (r'Комиссионные[:\s]+(Да|Нет)', 'Комиссионные'),
            (rf'Тип строения[:\s]+(.+?)(?={keyword_pattern}|$)', 'Тип строения'),
            (rf'Ремонт[:\s]+(.+?)(?={keyword_pattern}|$)', 'Ремонт'),
        ]
        
        for pattern, key in patterns:
            match = re.search(pattern, all_text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if len(value) < 100:
                    params[key] = value
                    
        return params
    
    def _extract_description(self, soup):
        desc_section = soup.find('div', {'data-cy': 'ad_description'})
        if desc_section:
            text = desc_section.get_text(separator='\n', strip=True)
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            return '\n'.join(lines)
        
        for header in soup.find_all(['h2', 'h3']):
            if 'Описание' in header.get_text():
                next_el = header.find_next_sibling()
                if next_el:
                    text = next_el.get_text(separator='\n', strip=True)
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    return '\n'.join(lines)
        
        return None
    
    def _extract_location(self, soup):
        text = soup.get_text()
        match = re.search(r'(Ташкент[,\s]+[^\n]+район)', text)
        if match:
            return match.group(1).strip()
        return None
    
    def _extract_seller(self, soup):
        seller_links = soup.find_all('a', href=lambda x: x and '/list/user/' in x if x else False)
        for link in seller_links:
            name = link.find('h4') or link.find('span') or link
            text = name.get_text(strip=True)
            if text and len(text) > 1:
                return text
        return None
    
    def _extract_date(self, soup):
        text = soup.get_text()
        patterns = [
            r'Опубликовано\s+(.+?)(?:\n|$)',
            r'(Сегодня в \d{2}:\d{2})',
            r'(Вчера в \d{2}:\d{2})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return None
    
    def _extract_olx_id(self, soup, url):
        match = re.search(r'ID(\w+)\.html', url)
        if match:
            return match.group(1)
        return None
    
    def get_tashkent_now(self):
        tashkent_tz = timezone(timedelta(hours=5))
        return datetime.now(tashkent_tz)
    
    def parse_date_string(self, date_str):
        if not date_str:
            return None
        
        tashkent_now = self.get_tashkent_now()
        today = tashkent_now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        
        if 'Сегодня' in date_str:
            return today
        
        if 'Вчера' in date_str:
            return today - timedelta(days=1)
        
        for month_name, month_num in self.RUSSIAN_MONTHS.items():
            if month_name in date_str.lower():
                match = re.search(r'(\d{1,2})\s+' + month_name + r'\s+(\d{4})', date_str.lower())
                if match:
                    day = int(match.group(1))
                    year = int(match.group(2))
                    try:
                        return datetime(year, month_num, day)
                    except:
                        pass
        
        return None
    
    def is_listing_fresh(self, date_str, max_days):
        if max_days is None or max_days == 0:
            return True
        
        parsed_date = self.parse_date_string(date_str)
        if not parsed_date:
            return True
        
        tashkent_now = self.get_tashkent_now()
        today = tashkent_now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        age_days = (today - parsed_date).days
        
        return age_days <= max_days


def test_bulk_parser():
    parser = OLXParser()
    
    def progress(current, total, url):
        print(f"[{current}/{total}] Parsing: {url[:60]}...")
    
    results = parser.bulk_parse(
        deal_type='sale',
        property_type='apartment',
        district='mirabad',
        rooms='2',
        max_pages=1,
        max_listings=3,
        get_phone=False,
        progress_callback=progress
    )
    
    print(f"\nFound: {results['total_found']} listings")
    print(f"Parsed: {results['parsed']} listings")
    
    for listing in results['listings']:
        print(f"\n--- {listing.get('title', 'No title')} ---")
        print(f"Price: {listing.get('price')} {listing.get('currency')}")
        print(f"Rooms: {listing.get('rooms')}")
        print(f"Area: {listing.get('total_area')} m2")
        print(f"Photos: {len(listing.get('photos', []))}")


if __name__ == '__main__':
    test_bulk_parser()
