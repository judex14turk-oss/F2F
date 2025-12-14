# Real Estate Bot

## Overview

This is a Telegram-based real estate marketplace platform designed for the Tashkent market. The application functions as a "Tinder for real estate" - buyers can swipe through property listings while sellers (owners, realtors, developers) can list properties and proactively find potential buyers.

The platform has two main user interfaces:
1. **Telegram Bot** - Primary interface for buyers (swipe-based property discovery) and sellers (property management)
2. **Web Admin/CRM Panel** - Flask-based dashboard for sellers to manage listings and track deals, plus admin functionality for platform management

## Recent Changes (December 14, 2025)

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
  - Доступен только для Super Admin
  - Фильтры: тип сделки (продажа/аренда), тип недвижимости (квартира/дом/участок), район Ташкента, комнаты, тип жилья
  - **Фильтр по дате публикации**: за сегодня, 3 дня, неделю, 2 недели, все даты
  - **Увеличенный лимит**: до 1000 объявлений (10, 20, 50, 100, 200, 500, 1000)
  - Сбор данных: фото, цена, параметры, описание, телефон, дата публикации
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
