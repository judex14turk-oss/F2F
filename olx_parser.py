import re
import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import json
from datetime import datetime, timedelta, timezone
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError


class OLXParser:
    BASE_URL = "https://www.olx.uz"
    
    DEAL_TYPES = {
        'sale': 'prodazha',
        'rent': 'arenda-dolgosrochnaya'
    }
    
    PROPERTY_TYPES = {
        'apartment': 'kvartiry',
        'land': 'zemelnye-uchastki',
        'house': 'doma',
        'commercial': 'kommercheskie-pomeshcheniya'
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
        'olmazor': 'Олмазорский',
        'yangihayot': 'Янгихаётский',
        'noviy_tashkent': 'Новый Ташкент'
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
        'olmazor': 16,
        'yangihayot': 26,
        'noviy_tashkent': 27
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
        import shutil
        
        try:
            import undetected_chromedriver as uc
            
            options = uc.ChromeOptions()
            options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--lang=ru-RU,ru')
            
            chromium_path = shutil.which('chromium') or shutil.which('chromium-browser')
            if chromium_path:
                options.binary_location = chromium_path
            
            driver = uc.Chrome(options=options, headless=True, use_subprocess=True)
            driver.set_page_load_timeout(20)
            driver.set_script_timeout(15)
            return driver
        except Exception as e:
            print(f"UC driver failed: {e}, trying regular Selenium")
            
        from selenium.webdriver.chrome.service import Service
        
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--lang=ru-RU,ru')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        chromium_path = shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome')
        chromedriver_path = shutil.which('chromedriver')
        
        if chromium_path:
            chrome_options.binary_location = chromium_path
        
        try:
            service = Service(executable_path=chromedriver_path) if chromedriver_path else Service()
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                '''
            })
            driver.set_page_load_timeout(20)
            driver.set_script_timeout(15)
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
        
        for page in range(1, max_pages + 1):
            if len(listings) >= max_listings:
                break
                
            url = self.build_category_url(deal_type, property_type, district, rooms, housing_type, page)
            print(f"Fetching page {page}: {url}")
            
            try:
                response = requests.get(url, headers=self.headers, timeout=30)
                if response.status_code != 200:
                    print(f"Error fetching page {page}: status {response.status_code}")
                    break
                
                soup = BeautifulSoup(response.text, 'lxml')
                
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
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"Error fetching page {page}: {e}")
                break
        
        return listings
    
    def parse_listing_with_driver(self, driver, url, get_phone=False, timeout=20):
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
        
        start_time = time.time()
        
        try:
            driver.set_page_load_timeout(15)
            try:
                driver.get(url)
            except TimeoutException:
                result['error'] = 'Page load timeout'
                return result
            except Exception as e:
                result['error'] = f'Page load error: {str(e)}'
                return result
            
            time.sleep(0.5)
            
            if get_phone:
                if time.time() - start_time > timeout:
                    result['error'] = 'Timeout before phone extraction'
                    return result
                    
                try:
                    from selenium.webdriver.support.ui import WebDriverWait
                    from selenium.webdriver.support import expected_conditions as EC
                    
                    time.sleep(1)
                    
                    try:
                        phone_btn = WebDriverWait(driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Показать')]"))
                        )
                        driver.execute_script("arguments[0].click();", phone_btn)
                        time.sleep(2)
                    except:
                        pass
                    
                    try:
                        tel_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'tel:')]")
                        for tel_link in tel_links:
                            href = tel_link.get_attribute('href')
                            if href and 'tel:' in href:
                                phone = href.replace('tel:', '').replace(' ', '').replace('-', '').strip()
                                if len(phone) >= 9:
                                    result['phone'] = phone
                                    break
                    except:
                        pass
                    
                    if not result['phone']:
                        page_text = driver.page_source
                        phone_regexes = [
                            r'tel:\+?[\d\s\-]+',
                            r'\+998\d{9}',
                            r'\+99\s?\d{3}\s?\d{7}',
                            r'998\d{9}',
                        ]
                        for regex in phone_regexes:
                            phone_match = re.search(regex, page_text)
                            if phone_match:
                                phone = phone_match.group(0).replace('tel:', '').replace(' ', '').replace('-', '')
                                if len(phone) >= 9:
                                    result['phone'] = phone if phone.startswith('+') else '+' + phone
                                    break
                        
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
            
            if not result['phone'] and result['seller_name']:
                phone_from_seller = self._extract_phone_from_text(result['seller_name'])
                if phone_from_seller:
                    result['phone'] = phone_from_seller
            
            if not result['phone'] and result['description']:
                phone_from_desc = self._extract_phone_from_text(result['description'])
                if phone_from_desc:
                    result['phone'] = phone_from_desc
            
        except Exception as e:
            result['error'] = str(e)
            
        return result
    
    def _extract_phone_from_text(self, text):
        if not text:
            return None
        phone_patterns = [
            r'\+998[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
            r'\+998\d{9}',
            r'\+99[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{4}',
            r'998[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
            r'998\d{9}',
            r'(?:^|[^\d])([89]\d{8})(?:[^\d]|$)',
            r'(?:^|[^\d])(9\d{8})(?:[^\d]|$)',
            r'\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, text)
            if match:
                phone = match.group(1) if match.lastindex else match.group(0)
                phone = phone.replace(' ', '').replace('-', '')
                if len(phone) == 9 and phone[0] in '89':
                    phone = '+998' + phone
                elif not phone.startswith('+') and not phone.startswith('998'):
                    phone = '+998' + phone
                elif phone.startswith('998') and not phone.startswith('+'):
                    phone = '+' + phone
                return phone
        return None
    
    def parse_listing_with_requests(self, url):
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
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code != 200:
                result['error'] = f'HTTP {response.status_code}'
                return result
            
            soup = BeautifulSoup(response.text, 'lxml')
            page_text = response.text
            
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
            
            phone = self._extract_phone_from_text(result['description'])
            if not phone and result['seller_name']:
                phone = self._extract_phone_from_text(result['seller_name'])
            result['phone'] = phone
            
            for district_key, district_name in self.TASHKENT_DISTRICTS.items():
                if district_name and district_name in (result['location'] or ''):
                    result['district'] = district_name
                    break
            
        except Exception as e:
            result['error'] = str(e)
            
        return result
    
    def parse_listing(self, url, get_phone=False):
        result = self.parse_listing_with_requests(url)
        
        if get_phone and not result.get('phone'):
            if result.get('seller_name'):
                phone = self._extract_phone_from_text(result['seller_name'])
                if phone:
                    result['phone'] = phone
            
            if not result.get('phone') and result.get('description'):
                phone = self._extract_phone_from_text(result['description'])
                if phone:
                    result['phone'] = phone
        
        return result
    
    def parse_listing_with_phone(self, url):
        return self.parse_listing(url, get_phone=True)
    
    def parse_generator(self, deal_type='sale', property_type='apartment', district='all',
                        rooms=None, housing_type='all', max_listings=50, 
                        get_phone=False, max_days=None):
        """
        Unified generator that yields parsed listings one by one.
        Used by both batch and streaming endpoints.
        
        Yields dict with:
            - 'event': 'start' | 'listing' | 'skip' | 'error' | 'complete'
            - 'data': parsed listing data (for 'listing' event)
            - 'skip_reason': reason for skip (for 'skip' event)
            - 'current': current index
            - 'total': total URLs found
            - 'added': number of successfully parsed listings
            - 'stats': final stats (for 'complete' event)
        """
        fetch_multiplier = 2 if max_days else 1.5
        if district and district != 'all':
            fetch_multiplier = 3
        fetch_limit = int(max_listings * fetch_multiplier)
        fetch_pages = max(25, (fetch_limit // 40) + 1)
        
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
        print(f"parse_generator: collected {total} URLs, starting parsing...")
        district_name = self.TASHKENT_DISTRICTS.get(district, '') if district else ''
        
        yield {
            'event': 'start',
            'total': total,
            'current': 0,
            'added': 0
        }
        
        driver = None
        driver_errors = 0
        max_driver_errors = 3
        
        if get_phone:
            driver = self.get_driver()
            if not driver:
                print("Warning: Could not initialize browser, falling back to requests")
        
        results = []
        skipped_old = 0
        skipped_district = 0
        skipped_error = 0
        
        try:
            print(f"parse_generator: starting loop, max_listings={max_listings}")
            for i, url in enumerate(listing_urls):
                if i == 0:
                    print(f"parse_generator: processing first URL: {url}")
                if len(results) >= max_listings:
                    print(f"parse_generator: reached max_listings limit ({max_listings})")
                    break
                
                try:
                    if get_phone and driver:
                        try:
                            with ThreadPoolExecutor(max_workers=1) as executor:
                                future = executor.submit(self.parse_listing_with_driver, driver, url, True, 15)
                                data = future.result(timeout=25)
                        except FuturesTimeoutError:
                            print(f"Hard timeout for URL: {url}")
                            data = {'url': url, 'error': 'Hard timeout'}
                            driver_errors += 1
                        except Exception as parse_err:
                            print(f"Parse error: {parse_err}")
                            data = {'url': url, 'error': str(parse_err)}
                            driver_errors += 1
                        
                        if data.get('error'):
                            driver_errors += 1
                            print(f"Driver error ({driver_errors}/{max_driver_errors}): {data.get('error')}")
                            
                            if driver_errors >= max_driver_errors:
                                print("Too many errors, restarting driver...")
                                try:
                                    driver.quit()
                                except:
                                    pass
                                time.sleep(1)
                                driver = self.get_driver()
                                driver_errors = 0
                                if not driver:
                                    print("Failed to restart driver, falling back to requests")
                        else:
                            driver_errors = 0
                    else:
                        data = self.parse_listing_with_requests(url)
                    
                    # Filter by date
                    if max_days and not self.is_listing_fresh(data.get('published_date'), max_days):
                        skipped_old += 1
                        yield {
                            'event': 'skip',
                            'skip_reason': 'old',
                            'current': i + 1,
                            'total': total,
                            'added': len(results),
                            'skipped_old': skipped_old
                        }
                        continue
                    
                    # Filter by district
                    if district and district != 'all' and district_name:
                        location = data.get('location', '') or ''
                        parsed_district = data.get('district', '') or ''
                        if district_name not in location and district_name not in parsed_district:
                            skipped_district += 1
                            yield {
                                'event': 'skip',
                                'skip_reason': 'district',
                                'current': i + 1,
                                'total': total,
                                'added': len(results),
                                'skipped_district': skipped_district
                            }
                            continue
                    
                    results.append(data)
                    
                    yield {
                        'event': 'listing',
                        'data': data,
                        'current': i + 1,
                        'total': total,
                        'added': len(results),
                        'skipped_old': skipped_old,
                        'skipped_district': skipped_district
                    }
                    
                    if not get_phone:
                        time.sleep(0.3)
                    
                except Exception as e:
                    yield {
                        'event': 'error',
                        'error': str(e),
                        'url': url,
                        'current': i + 1,
                        'total': total,
                        'added': len(results)
                    }
        finally:
            if driver:
                driver.quit()
        
        yield {
            'event': 'complete',
            'total': total,
            'parsed': len(results),
            'skipped_old': skipped_old,
            'skipped_district': skipped_district,
            'listings': results,
            'filters': {
                'deal_type': deal_type,
                'property_type': property_type,
                'district': district,
                'rooms': rooms,
                'housing_type': housing_type,
                'max_days': max_days
            }
        }
    
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
        
        driver = None
        if get_phone:
            driver = self.get_driver()
            if not driver:
                print("Warning: Could not initialize browser, falling back to requests")
        
        try:
            for i, url in enumerate(listing_urls):
                if len(results) >= max_listings:
                    break
                    
                if progress_callback:
                    progress_callback(i + 1, total, url)
                
                try:
                    if get_phone and driver:
                        data = self.parse_listing_with_driver(driver, url, get_phone=True)
                    else:
                        data = self.parse_listing_with_requests(url)
                    
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
                    
                    if not get_phone:
                        time.sleep(0.3)
                    
                except Exception as e:
                    print(f"Error parsing {url}: {e}")
                    results.append({
                        'url': url,
                        'error': str(e)
                    })
        finally:
            if driver:
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
                    'Тип строения', 'Ремонт', 'Год постройки', 'Высота потолков', 'В квартире есть',
                    'В помещении есть', 'Наличие парковки', 'Тип помещения', 'Коммуникации', 'Цоколь']
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
