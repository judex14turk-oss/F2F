import re
import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import json
import os


class OLXParser:
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
            return driver
        except Exception as e:
            print(f"Error creating driver: {e}")
            return None
    
    def parse_listing(self, url):
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
            'seller_name': None,
            'olx_id': None,
            'published_date': None,
            'error': None
        }
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            
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
            
        except Exception as e:
            result['error'] = str(e)
            
        return result
    
    def parse_listing_with_phone(self, url):
        result = self.parse_listing(url)
        
        driver = self.get_driver()
        if not driver:
            result['error'] = 'Failed to initialize browser'
            return result
            
        try:
            driver.get(url)
            time.sleep(3)
            
            try:
                phone_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Показать телефон') or contains(text(), 'показать')]"))
                )
                phone_button.click()
                time.sleep(2)
                
                phone_elements = driver.find_elements(By.XPATH, "//a[starts-with(@href, 'tel:')]")
                if phone_elements:
                    phone_href = phone_elements[0].get_attribute('href')
                    result['phone'] = phone_href.replace('tel:', '').strip()
                else:
                    phone_text = driver.find_element(By.XPATH, "//div[contains(@class, 'css-')]//a[contains(@href, 'tel:')]").text
                    result['phone'] = phone_text.strip()
                    
            except TimeoutException:
                all_links = driver.find_elements(By.XPATH, "//a[starts-with(@href, 'tel:')]")
                if all_links:
                    result['phone'] = all_links[0].get_attribute('href').replace('tel:', '')
                    
            except Exception as e:
                result['phone_error'] = str(e)
                
        except Exception as e:
            result['error'] = str(e)
        finally:
            driver.quit()
            
        return result
    
    def _extract_title(self, soup):
        title_el = soup.find('h1') or soup.find('h4')
        return title_el.get_text(strip=True) if title_el else None
    
    def _extract_price(self, soup):
        price_el = soup.find('h3')
        if price_el:
            price_text = price_el.get_text(strip=True)
            numbers = re.findall(r'[\d\s]+', price_text)
            if numbers:
                price = numbers[0].replace(' ', '').strip()
                currency = price_text.replace(numbers[0], '').strip()
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
        
        param_items = soup.find_all(['li', 'p', 'div'])
        for item in param_items:
            text = item.get_text(strip=True)
            
            patterns = [
                (r'Тип жилья[:\s]+(.+)', 'Тип жилья'),
                (r'Количество комнат[:\s]+(\d+)', 'Количество комнат'),
                (r'Общая площадь[:\s]+(\d+)', 'Общая площадь'),
                (r'Этаж[:\s]+(\d+)', 'Этаж'),
                (r'Этажность дома[:\s]+(\d+)', 'Этажность дома'),
                (r'Планировка[:\s]+(.+)', 'Планировка'),
                (r'Санузел[:\s]+(.+)', 'Санузел'),
                (r'Меблирована[:\s]+(.+)', 'Меблирована'),
                (r'Рядом есть[:\s]+(.+)', 'Рядом есть'),
                (r'Комиссионные[:\s]+(.+)', 'Комиссионные'),
            ]
            
            for pattern, key in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    params[key] = match.group(1).strip()
        
        all_text = soup.get_text()
        for pattern, key in [
            (r'Тип жилья:\s*([^\n]+)', 'Тип жилья'),
            (r'Количество комнат:\s*(\d+)', 'Количество комнат'),
            (r'Общая площадь:\s*(\d+)', 'Общая площадь'),
            (r'Этаж:\s*(\d+)', 'Этаж'),
            (r'Этажность дома:\s*(\d+)', 'Этажность дома'),
            (r'Планировка:\s*([^\n]+)', 'Планировка'),
            (r'Санузел:\s*([^\n]+)', 'Санузел'),
            (r'Меблирована:\s*([^\n]+)', 'Меблирована'),
        ]:
            if key not in params:
                match = re.search(pattern, all_text, re.IGNORECASE)
                if match:
                    params[key] = match.group(1).strip()
                    
        return params
    
    def _extract_description(self, soup):
        desc_section = soup.find('div', {'data-cy': 'ad_description'})
        if desc_section:
            return desc_section.get_text(strip=True)
        
        for header in soup.find_all(['h2', 'h3']):
            if 'Описание' in header.get_text():
                next_el = header.find_next_sibling()
                if next_el:
                    return next_el.get_text(strip=True)
        
        return None
    
    def _extract_location(self, soup):
        location_el = soup.find('a', {'href': lambda x: x and '/d/tashkent/' in x if x else False})
        if location_el:
            return location_el.get_text(strip=True)
        
        text = soup.get_text()
        match = re.search(r'(Ташкент[^\n]+район)', text)
        if match:
            return match.group(1)
            
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
            r'(\d{1,2}\s+\w+\s+\d{4})',
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
        
        text = soup.get_text()
        match = re.search(r'ID[:\s]+(\d+)', text)
        if match:
            return match.group(1)
            
        return None
    
    def parse_category_page(self, category_url, max_pages=1):
        listings = []
        
        for page in range(1, max_pages + 1):
            page_url = f"{category_url}?page={page}" if page > 1 else category_url
            
            try:
                response = requests.get(page_url, headers=self.headers, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'lxml')
                
                links = soup.find_all('a', href=lambda x: x and '/d/obyavlenie/' in x if x else False)
                for link in links:
                    href = link.get('href', '')
                    if href.startswith('/'):
                        href = 'https://www.olx.uz' + href
                    if href not in listings:
                        listings.append(href)
                        
            except Exception as e:
                print(f"Error parsing page {page}: {e}")
                break
                
        return listings


def test_parser():
    parser = OLXParser()
    
    test_url = "https://www.olx.uz/d/obyavlenie/prodam-2-v-3-h-komnatnuyu-mirabadskiy-rayon-kuylyuk-1-ID4e6lN.html"
    
    print("Parsing listing without phone...")
    result = parser.parse_listing(test_url)
    
    print(f"\nTitle: {result['title']}")
    print(f"Price: {result['price']} {result['currency']}")
    print(f"Rooms: {result['rooms']}")
    print(f"Area: {result['total_area']} m2")
    print(f"Floor: {result['floor']} / {result['total_floors']}")
    print(f"Type: {result['property_type']}")
    print(f"Layout: {result['layout']}")
    print(f"Bathroom: {result['bathroom']}")
    print(f"Furnished: {result['furnished']}")
    print(f"Location: {result['location']}")
    print(f"Seller: {result['seller_name']}")
    print(f"Photos: {len(result['photos'])} found")
    print(f"OLX ID: {result['olx_id']}")
    
    return result


if __name__ == '__main__':
    test_parser()
