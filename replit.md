# Real Estate Bot

## Overview

This is a Telegram-based real estate marketplace platform designed for the Tashkent market. The application functions as a "Tinder for real estate" - buyers can swipe through property listings while sellers (owners, realtors, developers) can list properties and proactively find potential buyers.

The platform has two main user interfaces:
1. **Telegram Bot** - Primary interface for buyers (swipe-based property discovery) and sellers (property management)
2. **Web Admin/CRM Panel** - Flask-based dashboard for sellers to manage listings and track deals, plus admin functionality for platform management

## Recent Changes (December 29, 2025)

- **Подробный поиск для искателей**: добавлена расширенная функция поиска с дополнительными фильтрами
  - Новая кнопка "🔍 Подробный поиск" в меню покупателя
  - Фильтр по площади (минимум-максимум м²)
  - Фильтр по типу дома (кирпичный, монолитный, панельный, блочный)
  - Фильтр по ремонту (новый, средний, требует ремонта, чистовая)
  - Фильтр по мебели (с мебелью / без мебели)
  - Фильтр по санузлу (раздельный / совмещенный)
  - Отображение текущих активных фильтров
  - Кнопки сброса и применения фильтров
  - Полная поддержка русского и узбекского языков
  - Новые поля в модели User: search_area_min, search_area_max, search_building_type, search_renovation, search_furniture, search_bathroom

## Previous Changes (December 22, 2025)

- **Система оплаты тарифов**: добавлена полная система оплаты через страницу тарифов
  - Кнопки "Оплатить" на карточках Про и Премиум
  - Страница оплаты (`/webapp/payment`) с вводом промокода и динамическим расчётом скидки
  - При нажатии "Оплатить" создаётся заявка в админ-панели и пользователь перенаправляется к случайному администратору
  - При подтверждении заявки устанавливается тариф и срок действия 30 дней

- **Бонусы от промокодов**: исправлена система применения бонусов
  - Добавлены поля `bonus_properties` и `bonus_likes` в модель User
  - При подтверждении промокода бонусные объявления и лайки применяются к пользователю
  - Бонусные слоты списываются при создании объявлений сверх базового лимита

- **Мультиязычность бота**: добавлена полная поддержка узбекского языка
  - При первой регистрации пользователю предлагается выбор языка (🇷🇺 Русский / 🇺🇿 O'zbekcha)
  - Создан файл translations.py со всеми переводами на оба языка
  - Добавлено поле `language` в модель User (миграция БД выполнена)
  - Все основные кнопки и меню переведены на узбекский
  - Кнопка "🌍 Сменить язык / Tilni o'zgartirish" добавлена в профиль покупателя и продавца
  - После смены языка пользователь возвращается в главное меню с новым языком

## Previous Changes (December 17, 2025)

- **Рекламная система**: добавлена полноценная система рекламы в боте
  - Модель Advertisement в базе данных (title, description, media, media_type, views_count)
  - Админ-панель для управления рекламой (добавление, редактирование, удаление)
  - Лимит 30 рекламных постов
  - Показ случайной рекламы каждые 10 объявлений для покупателей
  - Поддержка фото и видео (до 10 файлов)
  - Счётчик показов для каждого поста
  - Права доступа can_manage_ads для Super Admin и Admin
  - Раздел "Реклама" на странице тарифов с ценой 100,000 сум/мес
  - Информация о 25,000+ пользователях бота

## Previous Changes (December 15, 2025)

- **Унифицированный парсер OLX**: создан единый `parse_generator()` в olx_parser.py
  - Вся логика парсинга (фильтрация по дате, району, обход страниц) теперь в одном месте
  - Stream endpoint в app.py использует этот генератор
  - Исправления парсера теперь применяются ко всем режимам автоматически
- **Property Lifecycle**: добавлена система таймеров для объявлений
  - Активные объявления автоматически архивируются через 30 дней
  - Архивные объявления удаляются через 30 дней
  - Таймеры отображаются в "Мои объекты" и админ-панели
  - Реактивация сбрасывает таймер

## Previous Changes (December 14, 2025)

- Initial project setup with full functionality
- Created Telegram bot with aiogram 3.x
- Implemented buyer/seller registration flows
- Added property listing and swipe-based discovery
- Created matching and offer systems
- Built admin panel and seller CRM web interface
- Configured PostgreSQL database with all required tables
- Improved "Сделки" section with detailed contact cards showing client info
- Added WebView tariffs page with modern minimalist design
- Updated tariff system: Бесплатный (2 объявления, 1 лайк), Про (50/10), Премиум (100/30 + приоритет)
- Added three-tier admin role system (Super Admin, Admin, Operator) with granular permissions
- Admin panel accessible via WebApp in Telegram bot
- Separate page for managing administrators (only visible to Super Admin and Admin roles)
- **OLX Parser module** - массовый парсинг объявлений недвижимости с OLX.uz
  - Доступен для Super Admin и Admin
  - Фильтры: тип сделки (продажа/аренда), тип недвижимости (квартира/дом/участок), район Ташкента, комнаты, тип жилья
  - **Фильтр по дате публикации**: за сегодня, 3 дня, неделю, 2 недели, все даты
  - **Увеличенный лимит**: до 1000 объявлений (10, 20, 50, 100, 200, 500, 1000)
  - **Автосохранение в БД**: все спарсенные объявления автоматически добавляются в базу
  - Сбор данных: фото, цена, параметры, описание, телефон, дата публикации
  - **Телефон из объявления**: при парсинге телефон сохраняется в поле `phone` объекта Property (из объявления OLX), а не от администратора
  - Телефоны сразу доступны клиентам без необходимости лайков
  - Проверка дублей по olx_id
  - **Фильтр по району**: использует district_id OLX (yunusabad=25, chilanzar=17, etc.)
  - **Временная зона Ташкента**: все даты обрабатываются с учётом UTC+5
  - **Selenium**: парсер использует браузер для обхода капчи OLX
  - **Оптимизация скорости**: один браузер для всех объявлений (вместо нового для каждого)
  - Файл парсера: `olx_parser.py`

## User Preferences

- Admin username: InvictumMurad
- Preferred communication style: Simple, everyday language (Russian)

## System Architecture

### Application Structure
- **Dual-process architecture**: Flask web server and Telegram bot run as separate workflows
- **Bot file**: `bot.py` - Telegram bot with aiogram 3.x
- **Web file**: `app.py` - Flask web application on port 5000
- **Models**: `models.py` - SQLAlchemy ORM models
- **Templates**: `templates/` - Jinja2 HTML templates

### User Roles and Flow
- **Buyers**: Swipe-based property discovery with filters (rooms, district, budget, payment method)
- **Sellers**: Three types - Owner, Realtor, Developer - each with tariff-based feature limits
- **Admins**: Full platform management through web interface

### Tariff System (Promo pricing)
- **Бесплатный**: 2 properties, 1 like per day
- **Про** (300,000 sum/month - promo): 50 properties, 10 likes per day
- **Премиум** (500,000 sum/month - promo): 100 properties, 30 likes per day, priority display

### Key Features
- Property listing with moderation workflow (Active/Moderation/Archive statuses)
- Matching system: Buyers like properties -> Sellers accept -> Contact exchange
- "Demand hunting": Sellers can browse anonymous buyer profiles and proactively offer properties
- CRM for sellers to track matches and deals with notes
- Admin dashboard with statistics and user management

### Property Lifecycle / Таймеры объявлений
- **Активное объявление**: после добавления объявление активно 1 месяц
- **Архивирование**: через 1 месяц после добавления объявление автоматически переходит в архив
- **Удаление**: через 1 месяц после попадания в архив (если не активировано снова) объявление удаляется навсегда
- **Реактивация пользователем**: владелец может активировать своё объявление через "Мои объекты" в профиле
- **Реактивация админом**: администраторы видят таймеры всех объявлений и могут активировать любое объявление любого пользователя через админ-панель

### Database Schema
Core entities:
- **User**: Telegram users with role, tariff, preferences, contact info
- **Property**: Listings with type (sale/rent), location, parameters, photos, status
- **District/ResidentialComplex**: Location reference data (pre-populated with Tashkent districts)
- **Like**: Buyer interest tracking
- **Match**: Successful buyer-seller connections
- **Offer**: Proactive property offers from sellers to buyers

### Authentication
- Web login via Telegram ID
- Admin access determined by `is_admin` flag and `ADMIN_USERNAME` environment variable
- Session-based auth with decorators (`@login_required`, `@admin_required`)

## External Dependencies

### Services
- **Telegram Bot API**: Primary user interface via aiogram library
- **PostgreSQL**: Database backend via SQLAlchemy ORM

### Environment Variables
- `TELEGRAM_BOT_TOKEN`: Bot authentication token (configured)
- `DATABASE_URL`: PostgreSQL connection string (auto-configured)
- `ADMIN_USERNAME`: InvictumMurad

### Python Dependencies
- Flask: Web framework
- aiogram: Telegram bot framework (async)
- SQLAlchemy: ORM and database toolkit
- Bootstrap 5 (CDN): Frontend styling

## File Structure

```
/
├── bot.py              # Telegram bot with all handlers
├── app.py              # Flask web application
├── models.py           # SQLAlchemy database models
├── main.py             # Entry point (can run both services)
├── templates/
│   ├── base.html       # Base template with Bootstrap
│   ├── index.html      # Landing page
│   ├── login.html      # Login page
│   ├── admin/          # Admin panel templates
│   │   ├── dashboard.html
│   │   ├── users.html
│   │   ├── user_detail.html
│   │   ├── properties.html
│   │   ├── matches.html
│   │   └── stats.html
│   └── seller/         # Seller CRM templates
│       ├── dashboard.html
│       ├── properties.html
│       └── crm.html
└── static/             # Static files (CSS, JS)
```
