# Real Estate Bot

## Overview
This project is a Telegram-based real estate marketplace for Tashkent, functioning as a "Tinder for real estate." Buyers can swipe through listings, while sellers (owners, realtors, developers) can list properties and proactively find buyers. The platform aims to streamline the real estate transaction process through an intuitive interface and powerful management tools.

The platform features two main interfaces:
- **Telegram Bot**: The primary interface for buyers to discover properties and for sellers to manage listings and engage with potential clients.
- **Web Admin/CRM Panel**: A Flask-based dashboard for sellers to manage their listings, track deals, and for administrators to manage the platform.

## User Preferences
- Preferred communication style: Simple, everyday language (Russian)

## System Architecture

### Application Structure
The application uses a dual-process architecture, with a Flask web server and a Telegram bot running as separate workflows.
- `bot.py`: Handles Telegram bot logic using aiogram 3.x.
- `app.py`: Manages the Flask web application.
- `models.py`: Defines SQLAlchemy ORM database models.
- `templates/`: Contains Jinja2 HTML templates for the web interface.

### User Roles and Flow
- **Buyers**: Engage in swipe-based property discovery, utilizing filters for rooms, district, budget, and payment method.
- **Sellers**: Categorized as Owner, Realtor, or Developer, with features and limits determined by their chosen tariff plan. Sellers can browse anonymous buyer profiles to proactively offer properties.
- **Admins**: Manage the entire platform through a web-based interface, with a three-tier role system (Super Admin, Admin, Operator) providing granular permissions.

### Tariff System
The platform offers a tiered tariff system with promotional pricing:
- **Free**: 2 property listings, 1 like per day.
- **Pro** (300,000 sum/month): 50 property listings, 10 likes per day.
- **Premium** (500,000 sum/month): 100 property listings, 30 likes per day, plus priority display in searches.
A payment system allows users to subscribe to these tariffs, with support for promo codes and dynamic discount calculation.

### Key Features
- **Property Listing and Moderation**: Properties go through Active, Moderation, and Archive statuses.
- **Matching System**: Facilitates connections between buyers who "like" properties and sellers who accept these interests, leading to contact exchange.
- **CRM for Sellers**: Enables sellers to track matches, manage deals, and add notes.
- **Admin Dashboard**: Provides statistics, user management, and control over platform operations.
- **Multilingual Support**: Full support for Russian and Uzbek languages in the bot interface, allowing users to select their preferred language upon registration or change it later.
- **Advertisement System**: Allows display of advertisements within the bot, with random ads shown to buyers every 10 listings. Ads are managed via an admin panel and support various media types.
- **OLX Parser**: A module for mass parsing of real estate listings from OLX.uz, available to Super Admins and Admins. It includes filters for deal type, property type, Tashkent districts, rooms, and publication date. The parser automatically saves listings to the database, handles duplicates, and extracts contact information.

### Property Lifecycle
Properties have a defined lifecycle:
- **Active**: Properties are active for 30 days post-addition.
- **Archived**: After 30 days, properties are automatically archived.
- **Deleted**: Properties are permanently deleted 30 days after being archived if not reactivated.
- **Reactivation**: Users can reactivate their properties, and administrators can reactivate any property.

### Database Schema
Key entities include:
- `User`: Stores user profiles, roles, tariffs, and preferences.
- `Property`: Details of real estate listings.
- `District`/`ResidentialComplex`: Geographical and complex-specific data.
- `Like`: Records buyer interest in properties.
- `Match`: Represents successful buyer-seller connections.
- `Offer`: Tracks proactive property offers from sellers to buyers.
- `Advertisement`: Stores details of advertisements displayed in the bot.

### Authentication
Web interface authentication uses Telegram ID. Admin access is controlled by an `is_admin` flag and `ADMIN_USERNAME` environment variable, utilizing session-based authentication with `@login_required` and `@admin_required` decorators.

## External Dependencies

### Services
- **Telegram Bot API**: Utilized for the primary bot interface.
- **PostgreSQL**: The chosen database backend, managed with SQLAlchemy ORM.

### Environment Variables
- `TELEGRAM_BOT_TOKEN`: Required for bot authentication.
- `DATABASE_URL`: Connection string for PostgreSQL.
- `ADMIN_USERNAME`: Specifies the primary admin user.

### Python Dependencies
- **Flask**: Web framework for the admin panel.
- **aiogram**: Asynchronous framework for Telegram bot development.
- **SQLAlchemy**: ORM for database interaction.
- **Selenium**: Used by the OLX parser for web scraping.

### Frontend
- **Bootstrap 5 (CDN)**: Provides styling for the web interface.