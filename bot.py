import asyncio
import os
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, WebAppInfo, TelegramObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from typing import Callable, Dict, Any, Awaitable

from models import SessionLocal, User, Property, Like, Match, Offer, District, ResidentialComplex, Advertisement, Setting
from models import UserRole, SellerType, TariffType, PropertyType, PropertyStatus, init_db, get_tashkent_now


def get_usd_rate():
    """Получает курс USD из настроек"""
    db = SessionLocal()
    try:
        setting = db.query(Setting).filter(Setting.key == 'usd_rate').first()
        if setting and setting.value:
            return float(setting.value)
        return 12850  # Курс по умолчанию
    finally:
        db.close()


def convert_price(price, from_currency, to_currency, usd_rate=None):
    """Конвертирует цену между валютами"""
    if from_currency == to_currency or not price:
        return price
    
    if usd_rate is None:
        usd_rate = get_usd_rate()
    
    if from_currency == 'USD' and to_currency == 'UZS':
        return int(price * usd_rate)
    elif from_currency == 'UZS' and to_currency == 'USD':
        return int(price / usd_rate)
    
    return price


def format_price_for_user(price, price_currency, user_currency, usd_rate=None):
    """Форматирует цену для отображения пользователю"""
    if not price:
        return "Не указана"
    
    if usd_rate is None:
        usd_rate = get_usd_rate()
    
    if price_currency == user_currency:
        if user_currency == 'USD':
            return f"${price:,}".replace(",", " ")
        else:
            return f"{price:,} сум".replace(",", " ")
    
    converted = convert_price(price, price_currency, user_currency, usd_rate)
    
    if user_currency == 'USD':
        return f"${converted:,}".replace(",", " ")
    else:
        return f"{converted:,} сум".replace(",", " ")
from translations import get_text, get_user_lang
import random

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'InvictumMurad')
WEBAPP_URL = os.environ.get('WEBAPP_URL', '')

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


class BlockedUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if hasattr(event, 'from_user') and event.from_user:
            user_id = event.from_user.id
        elif hasattr(event, 'message') and event.message and event.message.from_user:
            user_id = event.message.from_user.id
        
        if user_id:
            db = SessionLocal()
            user = db.query(User).filter(User.telegram_id == user_id).first()
            is_blocked = user.is_blocked if user else False
            db.close()
            
            if is_blocked:
                if hasattr(event, 'answer'):
                    await event.answer("🚫 Ваш аккаунт заблокирован. Обратитесь к администратору.")
                return
        
        return await handler(event, data)


dp.message.middleware(BlockedUserMiddleware())
dp.callback_query.middleware(BlockedUserMiddleware())


class RegistrationStates(StatesGroup):
    choosing_language = State()
    choosing_role = State()
    buyer_deal_type = State()
    buyer_rooms = State()
    buyer_housing_type = State()
    buyer_district = State()
    buyer_currency = State()
    buyer_budget = State()
    buyer_payment = State()
    buyer_phone = State()
    seller_type = State()
    seller_company = State()
    seller_manager = State()
    seller_phone = State()
    owner_name = State()


class PropertyStates(StatesGroup):
    property_type = State()
    category = State()
    district = State()
    rooms = State()
    floor = State()
    total_floors = State()
    area = State()
    building_type = State()
    renovation = State()
    has_furniture = State()
    room_type = State()
    bathroom_type = State()
    price = State()
    description = State()
    photos = State()
    confirm = State()


class DeveloperPropertyStates(StatesGroup):
    property_type = State()  # продажа/аренда
    property_category = State()  # квартира/коммерция
    housing_class = State()  # класс жилья
    rooms = State()  # количество комнат
    area = State()  # площадь квартиры
    floor = State()  # этаж
    total_floors = State()  # этажность дома
    has_balcony = State()  # есть ли балкон
    balcony_area = State()  # площадь балкона
    renovation = State()  # тип ремонта
    included_in_price = State()  # что включено в стоимость
    district = State()  # район
    metro_station = State()  # станция метро
    location = State()  # локация
    price_per_sqm = State()  # цена за м²
    down_payment_type = State()  # тип первоначального взноса
    down_payment_value = State()  # значение первоначального взноса
    has_discount = State()  # есть ли скидка
    discount_conditions = State()  # условия скидок
    add_more_discount = State()  # добавить еще скидку
    payment_methods = State()  # методы оплаты
    mortgage_details = State()  # детали ипотеки
    installment_details = State()  # детали рассрочки
    has_mixed_payment = State()  # смешанный тип оплаты
    photos = State()  # фото проекта (включая планировки)
    confirm = State()  # подтверждение


class SearchStates(StatesGroup):
    viewing_properties = State()
    current_index = State()
    viewing_ad = State()


def validate_number(text):
    cleaned = text.strip().replace(" ", "").replace(",", ".")
    if re.match(r'^[\d.]+$', cleaned):
        try:
            if '.' in cleaned:
                return float(cleaned)
            return int(cleaned)
        except:
            return None
    return None


def get_district_keyboard(selected_districts: list = None, lang: str = 'ru'):
    """Генерирует клавиатуру для выбора районов с галочками для выбранных"""
    if selected_districts is None:
        selected_districts = []
    
    db = SessionLocal()
    districts = db.query(District).all()
    db.close()
    
    keyboard_buttons = []
    row = []
    for district in districts:
        display_name = get_district_name(district.name, lang)
        if district.name in selected_districts:
            button_text = f"✅ {display_name}"
        else:
            button_text = display_name
        row.append(KeyboardButton(text=button_text))
        if len(row) == 2:
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)
    
    if selected_districts:
        keyboard_buttons.append([KeyboardButton(text=get_text('done', lang))])
    keyboard_buttons.append([KeyboardButton(text=get_text('any_district', lang))])
    keyboard_buttons.append([KeyboardButton(text=get_text('back', lang))])
    
    return ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)


def get_db():
    db = SessionLocal()
    try:
        return db
    except:
        db.close()
        raise


def get_user(telegram_id: int):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    db.close()
    return user


def get_active_buyers_count(rooms=None, district=None, budget_max=None):
    db = SessionLocal()
    query = db.query(User).filter(User.role == UserRole.BUYER)
    if rooms:
        query = query.filter(User.search_rooms.contains(str(rooms)))
    if district:
        query = query.filter(User.search_district.contains(district))
    if budget_max:
        query = query.filter(User.search_budget_max >= budget_max * 0.8)
    count = query.count()
    db.close()
    return count


def get_tariff_limits(tariff: TariffType, is_admin: bool = False):
    if is_admin:
        return {"properties": 999999, "daily_likes": 999999, "daily_offers": 999999, "priority": True}
    
    limits = {
        TariffType.FREE: {"properties": 2, "daily_likes": 1, "daily_offers": 1, "priority": False},
        TariffType.PRO: {"properties": 50, "daily_likes": 10, "daily_offers": 10, "priority": False},
        TariffType.PREMIUM: {"properties": 100, "daily_likes": 30, "daily_offers": 30, "priority": True},
        TariffType.AGENCY_START: {"properties": 50, "daily_likes": 10, "daily_offers": 10, "priority": False},
        TariffType.DEVELOPER_PRO: {"properties": 100, "daily_likes": 30, "daily_offers": 30, "priority": True},
    }
    return limits.get(tariff, limits[TariffType.FREE])


BUILDING_TYPES = {
    "brick": "Кирпичный",
    "monolith": "Монолитный",
    "panel": "Панельный",
    "block": "Блочный",
    "wood": "Деревянный"
}

RENOVATION_TYPES = {
    "new": "Новый ремонт",
    "medium": "Средний ремонт",
    "needs": "Требует ремонта",
    "rough": "Чистовая отделка",
    "shell": "Коробка"
}

ROOM_TYPES = {
    "separate": "Раздельные",
    "adjacent": "Смежные"
}

BATHROOM_TYPES = {
    "separate": "Раздельный",
    "combined": "Совмещенный"
}

DISTRICT_TRANSLATIONS = {
    "Алмазарский": "Olmazor",
    "Бектемирский": "Bektemir",
    "Мирабадский": "Mirobod",
    "Мирзо-Улугбекский": "Mirzo Ulug'bek",
    "Сергелийский": "Sergeli",
    "Учтепинский": "Uchtepa",
    "Чиланзарский": "Chilonzor",
    "Шайхантаурский": "Shayxontohur",
    "Юнусабадский": "Yunusobod",
    "Яккасарайский": "Yakkasaroy",
    "Яшнабадский": "Yashnobod",
    "Янгихаётский": "Yangihayot",
    "Новый Ташкент": "Yangi Toshkent"
}

def get_district_name(name_ru: str, lang: str) -> str:
    if lang == 'uz' and name_ru in DISTRICT_TRANSLATIONS:
        return DISTRICT_TRANSLATIONS[name_ru]
    return name_ru


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if not user:
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            is_admin=(message.from_user.username == ADMIN_USERNAME)
        )
        db.add(user)
        db.commit()
    
    db.close()
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇷🇺 Русский")],
            [KeyboardButton(text="🇺🇿 O'zbekcha")]
        ],
        resize_keyboard=True
    )
    welcome_text = "👋 Добро пожаловать в F2F! / F2F ga xush kelibsiz!\n\n🌍 Выберите язык / Tilni tanlang:"
    await message.answer(welcome_text, reply_markup=keyboard)
    await state.set_state(RegistrationStates.choosing_language)


@dp.message(RegistrationStates.choosing_language)
async def process_language_choice(message: types.Message, state: FSMContext):
    if message.text == "🇷🇺 Русский":
        lang = 'ru'
    elif message.text == "🇺🇿 O'zbekcha":
        lang = 'uz'
    else:
        return
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    is_registered = user and user.phone
    if user:
        user.language = lang
        db.commit()
        user_role = user.role
    db.close()
    
    if is_registered:
        await state.clear()
        await message.answer(get_text('language_changed', lang))
        if user_role == UserRole.SELLER:
            is_developer = user.seller_type == SellerType.DEVELOPER if user else False
            keyboard = get_seller_menu(lang, is_developer=is_developer)
        else:
            keyboard = get_buyer_menu(lang)
        await message.answer(get_text('returned_to_menu', lang), reply_markup=keyboard)
    else:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=get_text('looking_for_property', lang))],
                [KeyboardButton(text=get_text('want_to_sell', lang))]
            ],
            resize_keyboard=True
        )
        await message.answer(get_text('welcome', lang), reply_markup=keyboard)
        await state.set_state(RegistrationStates.choosing_role)


@dp.message(RegistrationStates.choosing_role)
async def process_buyer_role(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    
    if message.text in [get_text('looking_for_property', 'ru'), get_text('looking_for_property', 'uz')]:
        if user:
            user.role = UserRole.BUYER
            db.commit()
        db.close()
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=get_text('buy', lang))],
                [KeyboardButton(text=get_text('rent', lang))],
                [KeyboardButton(text=get_text('back', lang))]
            ],
            resize_keyboard=True
        )
        
        await message.answer(get_text('great_what_interests', lang), reply_markup=keyboard)
        await state.set_state(RegistrationStates.buyer_deal_type)
    
    elif message.text in [get_text('want_to_sell', 'ru'), get_text('want_to_sell', 'uz')]:
        if user:
            user.role = UserRole.SELLER
            db.commit()
        db.close()
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=get_text('owner', lang))],
                [KeyboardButton(text=get_text('realtor', lang))],
                [KeyboardButton(text=get_text('developer', lang))],
                [KeyboardButton(text=get_text('back', lang))]
            ],
            resize_keyboard=True
        )
        
        await message.answer(get_text('choose_account_type', lang), reply_markup=keyboard)
        await state.set_state(RegistrationStates.seller_type)
    else:
        db.close()


@dp.message(F.text == "⬅️ Назад", RegistrationStates.buyer_deal_type)
async def back_to_role_from_deal(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Я ищу недвижимость")],
            [KeyboardButton(text="💼 Я хочу продать/сдать")]
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите вашу роль:", reply_markup=keyboard)
    await state.set_state(RegistrationStates.choosing_role)


@dp.message(RegistrationStates.buyer_deal_type)
async def process_buyer_deal_type(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    db.close()
    
    deal_map = {"🏷 купить": "sale", "🔑 снять": "rent", "🏷 sotib olish": "sale", "🔑 ijaraga olish": "rent"}
    deal_type = deal_map.get(message.text.lower(), "sale")
    await state.update_data(deal_type=deal_type, selected_districts=[], user_lang=lang)
    
    await message.answer(
        get_text('choose_district', lang),
        reply_markup=get_district_keyboard([], lang)
    )
    await state.set_state(RegistrationStates.buyer_district)


@dp.message(F.text == "⬅️ Назад", RegistrationStates.buyer_rooms)
async def back_to_role(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Я ищу недвижимость")],
            [KeyboardButton(text="💼 Я хочу продать/сдать")]
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите вашу роль:", reply_markup=keyboard)
    await state.set_state(RegistrationStates.choosing_role)


@dp.message(RegistrationStates.buyer_rooms)
async def process_rooms(message: types.Message, state: FSMContext):
    rooms_map = {"1": "1", "2": "2", "3": "3", "4+": "4", "студия": "studio"}
    rooms = rooms_map.get(message.text.lower(), message.text)
    await state.update_data(rooms=rooms)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏗 Новостройка")],
            [KeyboardButton(text="🏠 Вторичный рынок")],
            [KeyboardButton(text="Любой тип")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "🏠 Какой тип жилья вас интересует?",
        reply_markup=keyboard
    )
    await state.set_state(RegistrationStates.buyer_housing_type)


@dp.message(F.text == "⬅️ Назад", RegistrationStates.buyer_housing_type)
async def back_to_rooms_from_housing(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2"), KeyboardButton(text="3")],
            [KeyboardButton(text="4+"), KeyboardButton(text="Студия")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🚪 Сколько комнат вам нужно?", reply_markup=keyboard)
    await state.set_state(RegistrationStates.buyer_rooms)


@dp.message(RegistrationStates.buyer_housing_type)
async def process_housing_type(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    housing_map = {
        "🏗 новостройка": "Новостройка",
        "🏠 вторичный рынок": "Вторичный рынок",
        "любой тип": "Любой",
        "🏗 yangi bino": "Новостройка",
        "🏠 ikkilamchi bozor": "Вторичный рынок",
        "istalgan tur": "Любой"
    }
    housing_type = housing_map.get(message.text.lower(), message.text)
    await state.update_data(housing_type=housing_type, selected_districts=[])
    
    await message.answer(
        get_text('choose_district', lang),
        reply_markup=get_district_keyboard([], lang)
    )
    await state.set_state(RegistrationStates.buyer_district)


@dp.message(F.text == "⬅️ Назад", RegistrationStates.buyer_district)
async def back_to_deal_type(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏷 Купить")],
            [KeyboardButton(text="🔑 Снять")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🏠 Что вас интересует?", reply_markup=keyboard)
    await state.set_state(RegistrationStates.buyer_deal_type)


@dp.message(RegistrationStates.buyer_district)
async def process_district(message: types.Message, state: FSMContext):
    data = await state.get_data()
    selected_districts = data.get('selected_districts', [])
    lang = data.get('user_lang', 'ru')
    
    if message.text in ["Любой район", "Istalgan tuman"]:
        await state.update_data(district="Любой", selected_districts=[])
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🇺🇸 USD (доллары)")],
                [KeyboardButton(text="🇺🇿 UZS (сумы)")],
                [KeyboardButton(text="⬅️ Назад")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "💱 В какой валюте показывать цены?",
            reply_markup=keyboard
        )
        await state.set_state(RegistrationStates.buyer_currency)
        return
    
    if message.text in ["✅ Готово", "✅ Tayyor"]:
        if selected_districts:
            district_str = ", ".join(selected_districts)
            await state.update_data(district=district_str)
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🇺🇸 USD (доллары)")],
                    [KeyboardButton(text="🇺🇿 UZS (сумы)")],
                    [KeyboardButton(text="⬅️ Назад")]
                ],
                resize_keyboard=True
            )
            await message.answer(
                "💱 В какой валюте показывать цены?",
                reply_markup=keyboard
            )
            await state.set_state(RegistrationStates.buyer_currency)
        return
    
    district_name = message.text.replace("✅ ", "")
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    db.close()
    
    district_name_ru = district_name
    for ru_name, uz_name in DISTRICT_TRANSLATIONS.items():
        if district_name == uz_name:
            district_name_ru = ru_name
            break
    
    if district_name_ru in selected_districts:
        selected_districts.remove(district_name_ru)
    else:
        selected_districts.append(district_name_ru)
    
    await state.update_data(selected_districts=selected_districts)
    
    selected_display = [get_district_name(d, lang) for d in selected_districts]
    selected_text = ", ".join(selected_display) if selected_display else (get_text('not_selected', lang) if lang == 'uz' else "не выбрано")
    await message.answer(
        f"{get_text('choose_district', lang)}\n\n{'Tanlangan' if lang == 'uz' else 'Выбрано'}: {selected_text}",
        reply_markup=get_district_keyboard(selected_districts, lang)
    )


@dp.message(F.text == "⬅️ Назад", RegistrationStates.buyer_currency)
async def back_to_district_from_currency(message: types.Message, state: FSMContext):
    data = await state.get_data()
    selected_districts = data.get('selected_districts', [])
    lang = data.get('user_lang', 'ru')
    
    await message.answer(
        get_text('choose_district', lang),
        reply_markup=get_district_keyboard(selected_districts, lang)
    )
    await state.set_state(RegistrationStates.buyer_district)


@dp.message(RegistrationStates.buyer_currency)
async def process_currency(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    if "USD" in message.text:
        currency = "USD"
        currency_symbol = "$"
    elif "UZS" in message.text:
        currency = "UZS"
        currency_symbol = "сум"
    else:
        await message.answer("❌ Пожалуйста, выберите валюту из списка")
        return
    
    await state.update_data(currency=currency)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('share_phone', lang), request_contact=True)],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(
        get_text('share_phone_text', lang),
        reply_markup=keyboard
    )
    await state.set_state(RegistrationStates.buyer_phone)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), RegistrationStates.buyer_budget)
async def back_to_currency(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇺🇸 USD (доллары)")],
            [KeyboardButton(text="🇺🇿 UZS (сумы)")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        "💱 В какой валюте показывать цены?",
        reply_markup=keyboard
    )
    await state.set_state(RegistrationStates.buyer_currency)


@dp.message(RegistrationStates.buyer_budget)
async def process_budget(message: types.Message, state: FSMContext):
    budget = validate_number(message.text.replace("$", ""))
    if budget is None:
        await message.answer("❌ Пожалуйста, введите число цифрами (например: 50000)")
        return
    
    await state.update_data(budget=int(budget))
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💵 Наличные")],
            [KeyboardButton(text="🏦 Ипотека")],
            [KeyboardButton(text="📄 Рассрочка")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer("💳 Способ оплаты:", reply_markup=keyboard)
    await state.set_state(RegistrationStates.buyer_payment)


@dp.message(F.text == "⬅️ Назад", RegistrationStates.buyer_payment)
async def back_to_budget(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True
    )
    await message.answer(
        "💰 Какой у вас бюджет (в USD)?\n\nВведите максимальную сумму цифрами:",
        reply_markup=keyboard
    )
    await state.set_state(RegistrationStates.buyer_budget)


@dp.message(RegistrationStates.buyer_payment)
async def process_payment(message: types.Message, state: FSMContext):
    payment_map = {
        "💵 наличные": "cash",
        "🏦 ипотека": "mortgage",
        "📄 рассрочка": "installment"
    }
    payment = payment_map.get(message.text.lower(), "cash")
    await state.update_data(payment=payment)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер", request_contact=True)],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "📞 Поделитесь номером телефона, чтобы продавцы могли с вами связаться:\n\n"
        "Это обязательно для связи с продавцами.",
        reply_markup=keyboard
    )
    await state.set_state(RegistrationStates.buyer_phone)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), RegistrationStates.buyer_phone)
async def back_to_currency_from_phone(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇺🇸 USD (доллары)")],
            [KeyboardButton(text="🇺🇿 UZS (сумы)")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        "💱 В какой валюте показывать цены?",
        reply_markup=keyboard
    )
    await state.set_state(RegistrationStates.buyer_currency)


@dp.message(F.contact, RegistrationStates.buyer_phone)
async def process_buyer_phone_contact(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number
    data = await state.get_data()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    if user:
        user.phone = phone
        user.search_district = data.get("district", "")
        user.search_deal_type = data.get("deal_type", "sale")
        user.search_currency = data.get("currency", "USD")
        user.search_rooms = None
        user.search_housing_type = None
        user.search_budget_max = None
        user.search_budget_min = None
        user.search_payment_type = None
        db.commit()
    db.close()
    
    await state.clear()
    await show_buyer_menu(message, message.from_user.id)


@dp.message(RegistrationStates.buyer_phone)
async def process_buyer_phone_text(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if not re.match(r'^[\d\+\-\s\(\)]+$', phone) or len(phone) < 7:
        await message.answer("❌ Пожалуйста, введите корректный номер телефона или нажмите кнопку 'Отправить номер'")
        return
    
    data = await state.get_data()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    if user:
        user.phone = phone
        user.search_district = data.get("district", "")
        user.search_deal_type = data.get("deal_type", "sale")
        user.search_currency = data.get("currency", "USD")
        user.search_rooms = None
        user.search_housing_type = None
        user.search_budget_max = None
        user.search_budget_min = None
        user.search_payment_type = None
        db.commit()
    db.close()
    
    await state.clear()
    await show_buyer_menu(message, message.from_user.id)


async def show_buyer_menu(message, user_id):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_id).first()
    lang = get_user_lang(user)
    properties_count = db.query(Property).filter(Property.status == PropertyStatus.ACTIVE).count()
    db.close()
    
    keyboard = get_buyer_menu(lang)
    
    await message.answer(
        get_text('registration_complete', lang, count=properties_count),
        reply_markup=keyboard
    )


def get_buyer_menu(lang='ru'):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('view_properties', lang))],
            [KeyboardButton(text=get_text('search_settings', lang))],
            [KeyboardButton(text=get_text('profile', lang))]
        ],
        resize_keyboard=True
    )


def get_buyer_profile_menu(lang='ru'):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('likes', lang)), KeyboardButton(text=get_text('messages', lang))],
            [KeyboardButton(text=get_text('my_profile', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )


WEBAPP_BASE_URL = os.environ.get('REPLIT_DEV_DOMAIN', '')
if WEBAPP_BASE_URL and not WEBAPP_BASE_URL.startswith('https://'):
    WEBAPP_BASE_URL = f"https://{WEBAPP_BASE_URL}"


@dp.message(RegistrationStates.seller_type)
async def process_seller_type(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    db.close()
    
    if message.text in [get_text('back', 'ru'), get_text('back', 'uz')]:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=get_text('looking_for_property', lang))],
                [KeyboardButton(text=get_text('want_to_sell', lang))]
            ],
            resize_keyboard=True
        )
        await message.answer(get_text('choose_role', lang), reply_markup=keyboard)
        await state.set_state(RegistrationStates.choosing_role)
        return
    
    if message.text in [get_text('owner', 'ru'), get_text('owner', 'uz')]:
        await state.update_data(seller_type=SellerType.OWNER)
    elif message.text in [get_text('realtor', 'ru'), get_text('realtor', 'uz')]:
        await state.update_data(seller_type=SellerType.REALTOR)
    elif message.text in [get_text('developer', 'ru'), get_text('developer', 'uz')]:
        await state.update_data(seller_type=SellerType.DEVELOPER)
    else:
        return
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('share_phone', lang), request_contact=True)],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    
    await message.answer(get_text('share_phone_id', lang), reply_markup=keyboard)
    await state.set_state(RegistrationStates.seller_phone)


@dp.message(F.text == "⬅️ Назад", RegistrationStates.seller_company)
async def back_to_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    seller_type = data.get("seller_type", SellerType.OWNER)
    
    type_names = {
        SellerType.OWNER: "🏠 Собственник",
        SellerType.REALTOR: "🔑 Риелтор",
        SellerType.DEVELOPER: "🏗 Застройщик"
    }
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер", request_contact=True)],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        f"Тип: {type_names.get(seller_type, 'Собственник')}\n\n"
        "📱 Поделитесь вашим номером телефона:",
        reply_markup=keyboard
    )
    await state.set_state(RegistrationStates.seller_phone)


@dp.message(RegistrationStates.seller_company)
async def process_company_name(message: types.Message, state: FSMContext):
    await state.update_data(company_name=message.text)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True
    )
    
    await message.answer("👤 Введите имя менеджера (кто будет отвечать на звонки):", reply_markup=keyboard)
    await state.set_state(RegistrationStates.seller_manager)


@dp.message(F.text == "⬅️ Назад", RegistrationStates.seller_manager)
async def back_to_company(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True
    )
    await message.answer("🏢 Введите название компании или ваше имя:", reply_markup=keyboard)
    await state.set_state(RegistrationStates.seller_company)


@dp.message(RegistrationStates.seller_manager)
async def process_manager_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if user:
        user.company_name = data.get("company_name", "")
        user.manager_name = message.text
        db.commit()
    
    buyers_count = db.query(User).filter(User.role == UserRole.BUYER).count()
    db.close()
    
    await state.clear()
    await show_seller_menu(message, message.from_user.id, buyers_count)


@dp.message(F.text == "⬅️ Назад", RegistrationStates.seller_phone)
async def back_to_seller_type_from_phone(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Собственник")],
            [KeyboardButton(text="🔑 Риелтор")],
            [KeyboardButton(text="🏗 Застройщик")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("💼 Выберите тип аккаунта:", reply_markup=keyboard)
    await state.set_state(RegistrationStates.seller_type)


@dp.message(RegistrationStates.seller_phone)
async def process_phone(message: types.Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
    else:
        phone = message.text
    
    if not phone or phone == "⬅️ Назад":
        return
    
    data = await state.get_data()
    seller_type = data.get("seller_type", SellerType.OWNER)
    
    db = SessionLocal()
    
    existing_by_phone = db.query(User).filter(User.phone == phone).first()
    
    if existing_by_phone:
        if existing_by_phone.telegram_id != message.from_user.id:
            existing_by_phone.telegram_id = message.from_user.id
            existing_by_phone.username = message.from_user.username
            existing_by_phone.first_name = message.from_user.first_name
            existing_by_phone.last_name = message.from_user.last_name
        
        existing_by_phone.role = UserRole.SELLER
        db.commit()
        
        buyers_count = db.query(User).filter(User.role == UserRole.BUYER).count()
        db.close()
        
        await state.clear()
        await show_seller_menu(message, message.from_user.id, buyers_count)
        return
    
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if user:
        user.phone = phone
        user.seller_type = seller_type
        
        if seller_type == SellerType.REALTOR:
            user.tariff = TariffType.AGENCY_START
        elif seller_type == SellerType.DEVELOPER:
            user.tariff = TariffType.DEVELOPER_PRO
        else:
            user.tariff = TariffType.FREE
        
        db.commit()
    
    db.close()
    
    await state.update_data(phone=phone)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True
    )
    
    if seller_type == SellerType.OWNER:
        await message.answer("👤 Введите ваше имя:", reply_markup=keyboard)
        await state.set_state(RegistrationStates.owner_name)
    else:
        await message.answer("🏢 Введите название компании:", reply_markup=keyboard)
        await state.set_state(RegistrationStates.seller_company)


@dp.message(F.text == "⬅️ Назад", RegistrationStates.owner_name)
async def back_to_phone_from_owner_name(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    db.close()
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('share_phone', lang), request_contact=True)],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('share_phone_id', lang), reply_markup=keyboard)
    await state.set_state(RegistrationStates.seller_phone)


@dp.message(RegistrationStates.owner_name)
async def process_owner_name(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        return
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if user:
        user.company_name = message.text
        user.manager_name = message.text
        db.commit()
    
    buyers_count = db.query(User).filter(User.role == UserRole.BUYER).count()
    db.close()
    
    await state.clear()
    await show_seller_menu(message, message.from_user.id, buyers_count)


async def show_seller_menu(message, user_id, buyers_count=None):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_id).first()
    lang = get_user_lang(user)
    
    if buyers_count is None:
        buyers_count = db.query(User).filter(User.role == UserRole.BUYER).count()
    
    properties = db.query(Property).filter(Property.owner_id == user.id).all()
    total_views = sum(p.views_count for p in properties)
    total_likes = sum(p.likes_count for p in properties)
    matches_count = db.query(Match).filter(Match.seller_id == user.id).count()
    db.close()
    
    tariff_names = {
        TariffType.FREE: get_text('tariff_free', lang),
        TariffType.PRO: get_text('tariff_pro', lang),
        TariffType.PREMIUM: get_text('tariff_premium', lang),
        TariffType.AGENCY_START: get_text('tariff_agency', lang),
        TariffType.DEVELOPER_PRO: get_text('tariff_developer', lang)
    }
    
    is_developer = user.seller_type == SellerType.DEVELOPER
    keyboard = get_seller_menu(lang, is_developer=is_developer)
    
    await message.answer(
        get_text('seller_registration_complete', lang, count=buyers_count, views=total_views, likes=total_likes, matches=matches_count, tariff=tariff_names.get(user.tariff, get_text('tariff_free', lang))),
        reply_markup=keyboard
    )


@dp.message(F.text.in_(["➕ Добавить объект", "➕ Obyekt qo'shish"]))
async def add_property_start(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if not user or user.role != UserRole.SELLER:
        if user and user.role == UserRole.BUYER:
            lang = get_user_lang(user)
            db.close()
            await message.answer(get_text('returned_to_menu', lang), reply_markup=get_buyer_menu(lang))
        else:
            db.close()
            await message.answer("Нажмите /start чтобы начать.")
        return
    
    if user.seller_type == SellerType.DEVELOPER:
        db.close()
        await dev_add_property_start(message, state)
        return
    
    limits = get_tariff_limits(user.tariff, user.is_admin)
    current_properties = db.query(Property).filter(
        Property.owner_id == user.id,
        Property.status != PropertyStatus.ARCHIVE
    ).count()
    bonus = user.bonus_properties or 0
    max_properties = limits["properties"] + bonus
    db.close()
    
    if current_properties >= max_properties:
        await message.answer(
            f"⚠️ Вы достигли лимита объектов ({max_properties}) для вашего тарифа.\n\n"
            f"Перейдите на более высокий тариф, чтобы добавить больше объектов."
        )
        return
    
    await state.update_data(photos=[])
    
    await message.answer(
        "📝 Добавление нового объекта\n\nВыберите тип сделки:",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer(
        "Выберите тип сделки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏷 Продажа", callback_data="newprop_sale")],
            [InlineKeyboardButton(text="🔑 Аренда", callback_data="newprop_rent")],
        ])
    )
    await state.set_state(PropertyStates.property_type)


@dp.callback_query(F.data.startswith("newprop_"))
async def process_new_property_type(callback: types.CallbackQuery, state: FSMContext):
    prop_type = PropertyType.SALE if callback.data == "newprop_sale" else PropertyType.RENT
    await state.update_data(property_type=prop_type)
    
    await callback.message.edit_text(
        "🏠 Выберите категорию недвижимости:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏢 Квартира", callback_data="propcat_apartment")],
            [InlineKeyboardButton(text="🏡 Дом/Участок", callback_data="propcat_house")],
            [InlineKeyboardButton(text="🏪 Коммерческая", callback_data="propcat_commercial")],
        ])
    )
    await state.set_state(PropertyStates.category)


@dp.callback_query(F.data.startswith("propcat_"))
async def process_property_category(callback: types.CallbackQuery, state: FSMContext):
    category_map = {
        "propcat_apartment": "Квартира",
        "propcat_house": "Дом/Участок",
        "propcat_commercial": "Коммерческая"
    }
    category = category_map.get(callback.data, "Квартира")
    await state.update_data(category=category)
    
    db = SessionLocal()
    districts = db.query(District).all()
    db.close()
    
    keyboard_buttons = []
    row = []
    for district in districts:
        row.append(InlineKeyboardButton(text=district.name, callback_data=f"propdistrict_{district.id}"))
        if len(row) == 2:
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)
    
    await callback.message.edit_text(
        "📍 Выберите район:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    )
    await state.set_state(PropertyStates.district)


@dp.callback_query(F.data.startswith("propdistrict_"))
async def process_prop_district(callback: types.CallbackQuery, state: FSMContext):
    district_id = int(callback.data.replace("propdistrict_", ""))
    
    db = SessionLocal()
    district = db.query(District).filter(District.id == district_id).first()
    db.close()
    
    await state.update_data(district=district.name if district else "")
    
    await callback.message.edit_text("🚪 Введите количество комнат (цифрами):")
    await state.set_state(PropertyStates.rooms)


@dp.message(PropertyStates.rooms)
async def process_prop_rooms(message: types.Message, state: FSMContext):
    rooms = validate_number(message.text)
    if rooms is None or rooms < 1 or rooms > 20:
        await message.answer("❌ Введите количество комнат цифрами (например: 3)")
        return
    
    await state.update_data(rooms=int(rooms))
    await message.answer("🏢 Введите этаж квартиры (цифрами):")
    await state.set_state(PropertyStates.floor)


@dp.message(PropertyStates.floor)
async def process_prop_floor(message: types.Message, state: FSMContext):
    floor = validate_number(message.text)
    if floor is None or floor < 1 or floor > 100:
        await message.answer("❌ Введите этаж цифрами (например: 4)")
        return
    
    await state.update_data(floor=int(floor))
    await message.answer("🏗 Введите этажность дома (цифрами):")
    await state.set_state(PropertyStates.total_floors)


@dp.message(PropertyStates.total_floors)
async def process_prop_total_floors(message: types.Message, state: FSMContext):
    total_floors = validate_number(message.text)
    if total_floors is None or total_floors < 1 or total_floors > 100:
        await message.answer("❌ Введите этажность дома цифрами (например: 9)")
        return
    
    data = await state.get_data()
    if int(total_floors) < data.get("floor", 1):
        await message.answer("❌ Этажность дома не может быть меньше этажа квартиры!")
        return
    
    await state.update_data(total_floors=int(total_floors))
    await message.answer("📐 Введите площадь квартиры в м² (цифрами):")
    await state.set_state(PropertyStates.area)


@dp.message(PropertyStates.area)
async def process_prop_area(message: types.Message, state: FSMContext):
    area = validate_number(message.text)
    if area is None or area < 5 or area > 1000:
        await message.answer("❌ Введите площадь цифрами (например: 65)")
        return
    
    await state.update_data(area=float(area))
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧱 Кирпичный", callback_data="btype_brick")],
        [InlineKeyboardButton(text="🏗 Монолитный", callback_data="btype_monolith")],
        [InlineKeyboardButton(text="📦 Панельный", callback_data="btype_panel")],
        [InlineKeyboardButton(text="🧊 Блочный", callback_data="btype_block")],
    ])
    
    await message.answer("🏠 Выберите тип строения:", reply_markup=keyboard)
    await state.set_state(PropertyStates.building_type)


@dp.callback_query(F.data.startswith("btype_"))
async def process_building_type(callback: types.CallbackQuery, state: FSMContext):
    btype = callback.data.replace("btype_", "")
    await state.update_data(building_type=BUILDING_TYPES.get(btype, btype))
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ Новый ремонт", callback_data="reno_new")],
        [InlineKeyboardButton(text="👍 Средний ремонт", callback_data="reno_medium")],
        [InlineKeyboardButton(text="🔧 Требует ремонта", callback_data="reno_needs")],
        [InlineKeyboardButton(text="🏗 Чистовая отделка", callback_data="reno_rough")],
        [InlineKeyboardButton(text="📦 Коробка", callback_data="reno_shell")],
    ])
    
    await callback.message.edit_text("🔨 Выберите состояние ремонта:", reply_markup=keyboard)
    await state.set_state(PropertyStates.renovation)


@dp.callback_query(F.data.startswith("reno_"))
async def process_renovation(callback: types.CallbackQuery, state: FSMContext):
    reno = callback.data.replace("reno_", "")
    await state.update_data(renovation=RENOVATION_TYPES.get(reno, reno))
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛋 С мебелью", callback_data="furn_yes")],
        [InlineKeyboardButton(text="📦 Без мебели", callback_data="furn_no")],
    ])
    
    await callback.message.edit_text("🛋 Есть мебель?", reply_markup=keyboard)
    await state.set_state(PropertyStates.has_furniture)


@dp.callback_query(F.data.startswith("furn_"))
async def process_furniture(callback: types.CallbackQuery, state: FSMContext):
    has_furn = callback.data == "furn_yes"
    await state.update_data(has_furniture=has_furn)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚪 Раздельные", callback_data="roomtype_separate")],
        [InlineKeyboardButton(text="🚪 Смежные", callback_data="roomtype_adjacent")],
    ])
    
    await callback.message.edit_text("🚪 Тип комнат:", reply_markup=keyboard)
    await state.set_state(PropertyStates.room_type)


@dp.callback_query(F.data.startswith("roomtype_"))
async def process_room_type(callback: types.CallbackQuery, state: FSMContext):
    room_type = callback.data.replace("roomtype_", "")
    await state.update_data(room_type=ROOM_TYPES.get(room_type, room_type))
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚿 Раздельный", callback_data="bath_separate")],
        [InlineKeyboardButton(text="🛁 Совмещенный", callback_data="bath_combined")],
    ])
    
    await callback.message.edit_text("🚿 Тип санузла:", reply_markup=keyboard)
    await state.set_state(PropertyStates.bathroom_type)


@dp.callback_query(F.data.startswith("bath_"))
async def process_bathroom_type(callback: types.CallbackQuery, state: FSMContext):
    bath_type = callback.data.replace("bath_", "")
    await state.update_data(bathroom_type=BATHROOM_TYPES.get(bath_type, bath_type))
    
    await callback.message.edit_text("💰 Введите цену в USD (цифрами):")
    await state.set_state(PropertyStates.price)


@dp.message(PropertyStates.price)
async def process_prop_price(message: types.Message, state: FSMContext):
    price = validate_number(message.text.replace("$", "").replace(" ", ""))
    if price is None or price < 100:
        await message.answer("❌ Введите цену цифрами (например: 70000)")
        return
    
    await state.update_data(price=int(price))
    
    skip_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⏭ Пропустить")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("📝 Введите описание объекта или нажмите 'Пропустить':", reply_markup=skip_keyboard)
    await state.set_state(PropertyStates.description)


@dp.message(PropertyStates.description)
async def process_prop_description(message: types.Message, state: FSMContext):
    text = message.text.lower().strip() if message.text else ""
    description = "" if text in ["пропустить", "⏭ пропустить"] else message.text
    await state.update_data(description=description)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📷 Добавить фото", callback_data="add_photos")],
        [InlineKeyboardButton(text="⏭ Пропустить фото", callback_data="skip_photos")],
    ])
    
    await message.answer(
        "📸 Теперь добавьте фотографии (до 10 штук).\n\n"
        "Отправляйте фото по одному или несколько сразу.",
        reply_markup=keyboard
    )
    await state.set_state(PropertyStates.photos)


@dp.callback_query(F.data == "add_photos", PropertyStates.photos)
async def start_adding_photos(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📸 Отправляйте фотографии (до 10 штук).\n\n"
        "Когда закончите, нажмите кнопку 'Готово'."
    )
    await callback.message.answer(
        "Отправьте фото:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="photos_done")]
        ])
    )


@dp.message(PropertyStates.photos, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    
    if len(photos) >= 10:
        await message.answer("⚠️ Достигнут лимит в 10 фотографий!")
        return
    
    photo_id = message.photo[-1].file_id
    photos.append(photo_id)
    await state.update_data(photos=photos)
    
    await message.answer(
        f"✅ Фото добавлено ({len(photos)}/10)\n\n"
        "Отправьте еще фото или нажмите 'Готово'",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="photos_done")]
        ])
    )


@dp.callback_query(F.data.in_(["photos_done", "skip_photos"]))
async def finish_photos(callback: types.CallbackQuery, state: FSMContext):
    from aiogram.types import InputMediaPhoto
    
    data = await state.get_data()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    
    photos_str = ",".join(data.get("photos", []))
    
    import random
    import string
    unique_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    current_properties = db.query(Property).filter(
        Property.owner_id == user.id,
        Property.status != PropertyStatus.ARCHIVE
    ).count()
    limits = get_tariff_limits(user.tariff, user.is_admin)
    base_limit = limits["properties"]
    
    prop = Property(
        owner_id=user.id,
        property_type=data.get("property_type", PropertyType.SALE),
        category=data.get("category", "Квартира"),
        district=data.get("district", ""),
        rooms=data.get("rooms", 1),
        floor=data.get("floor", 1),
        total_floors=data.get("total_floors", 9),
        area=data.get("area", 50),
        price=data.get("price", 0),
        description=data.get("description", ""),
        photos=photos_str,
        building_type=data.get("building_type", ""),
        renovation=data.get("renovation", ""),
        has_furniture=data.get("has_furniture", False),
        room_type=data.get("room_type", ""),
        bathroom_type=data.get("bathroom_type", ""),
        status=PropertyStatus.MODERATION
    )
    db.add(prop)
    
    if current_properties >= base_limit and user.bonus_properties and user.bonus_properties > 0:
        user.bonus_properties -= 1
    
    db.commit()
    
    prop.unique_id = f"F2F-{prop.id:05d}"
    db.commit()
    prop_id = prop.id
    db.close()
    
    type_name = "Продажа" if data.get("property_type") == PropertyType.SALE else "Аренда"
    furniture = "Да" if data.get("has_furniture") else "Нет"
    
    category_display = data.get("category", "Квартира")
    
    summary = (
        f"📝 Объявление отправлено на модерацию!\n\n"
        f"🆔 <b>ID: {prop.unique_id}</b>\n\n"
        f"📋 ХАРАКТЕРИСТИКИ:\n"
        f"🏷 Тип сделки: {type_name}\n"
        f"🏠 Категория: {category_display}\n"
        f"📍 Район: {data.get('district', '')}\n"
        f"🚪 Комнат: {data.get('rooms', '')}\n"
        f"🏢 Этаж: {data.get('floor', '')}/{data.get('total_floors', '')}\n"
        f"📐 Площадь: {data.get('area', '')} м²\n"
        f"🏠 Тип дома: {data.get('building_type', '')}\n"
        f"🔨 Ремонт: {data.get('renovation', '')}\n"
        f"🛋 Мебель: {furniture}\n"
        f"🚪 Комнаты: {data.get('room_type', '')}\n"
        f"🚿 Санузел: {data.get('bathroom_type', '')}\n"
        f"💰 Цена: {data.get('price', 0):,} сум\n"
    )
    
    if data.get("description"):
        summary += f"\n📝 Описание:\n{data.get('description')}"
    
    photos_list = data.get("photos", [])
    
    await state.clear()
    
    if photos_list:
        media_group = []
        for i, photo_id in enumerate(photos_list):
            if i == 0:
                media_group.append(InputMediaPhoto(media=photo_id, caption=summary))
            else:
                media_group.append(InputMediaPhoto(media=photo_id))
        await callback.message.delete()
        await callback.message.answer_media_group(media_group)
    else:
        await callback.message.edit_text(summary)
    
    buyers_count = get_active_buyers_count(
        rooms=data.get("rooms"),
        district=data.get("district"),
        budget_max=data.get("price")
    )
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    lang = get_user_lang(user)
    is_developer = user.seller_type == SellerType.DEVELOPER if user else False
    db.close()
    
    keyboard = get_seller_menu(lang, is_developer=is_developer)
    
    await callback.message.answer(
        f"🎯 {buyers_count} покупателей ищут похожие квартиры.\n"
        f"Ваш объект уже виден им в ленте!",
        reply_markup=keyboard
    )


import json

# =====================================================
# DEVELOPER PROPERTY FORM HANDLERS (Extended form for developers)
# =====================================================

def get_dev_back_keyboard(lang='ru'):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=get_text('dev_back', lang))]],
        resize_keyboard=True
    )

def get_dev_skip_back_keyboard(lang='ru'):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_skip', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )

async def dev_add_property_start(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if not user or user.role != UserRole.SELLER:
        db.close()
        return
    
    if user.seller_type != SellerType.DEVELOPER:
        lang = get_user_lang(user)
        db.close()
        await message.answer("Эта форма только для застройщиков. Используйте обычную форму добавления объекта.")
        return
    
    lang = get_user_lang(user)
    limits = get_tariff_limits(user.tariff, user.is_admin)
    current_properties = db.query(Property).filter(
        Property.owner_id == user.id,
        Property.status != PropertyStatus.ARCHIVE
    ).count()
    bonus = user.bonus_properties or 0
    max_properties = limits["properties"] + bonus
    db.close()
    
    if current_properties >= max_properties:
        await message.answer(
            f"⚠️ Вы достигли лимита объектов ({max_properties}) для вашего тарифа."
        )
        return
    
    await state.update_data(photos=[], discounts=[], payment_methods=[], user_lang=lang)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_sale', lang))],
            [KeyboardButton(text=get_text('dev_rent', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    
    await message.answer(get_text('dev_add_property', lang) + "\n\n" + get_text('dev_choose_deal_type', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.property_type)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.property_type)
async def dev_back_from_property_type(message: types.Message, state: FSMContext):
    await state.clear()
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    is_developer = user.seller_type == SellerType.DEVELOPER if user else False
    db.close()
    await message.answer(get_text('returned_to_menu', lang), reply_markup=get_seller_menu(lang, is_developer=is_developer))


@dp.message(DeveloperPropertyStates.property_type)
async def dev_process_property_type(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    if message.text in [get_text('dev_sale', 'ru'), get_text('dev_sale', 'uz')]:
        prop_type = PropertyType.SALE
    elif message.text in [get_text('dev_rent', 'ru'), get_text('dev_rent', 'uz')]:
        prop_type = PropertyType.RENT
    else:
        return
    
    await state.update_data(property_type=prop_type)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_cat_apartment', lang))],
            [KeyboardButton(text=get_text('dev_cat_commercial', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    
    await message.answer(get_text('dev_choose_category', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.property_category)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.property_category)
async def dev_back_to_property_type(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_sale', lang))],
            [KeyboardButton(text=get_text('dev_rent', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_choose_deal_type', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.property_type)


@dp.message(DeveloperPropertyStates.property_category)
async def dev_process_property_category(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    if message.text in [get_text('dev_cat_apartment', 'ru'), get_text('dev_cat_apartment', 'uz')]:
        await state.update_data(property_category="Квартира")
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=get_text('dev_class_comfort', lang))],
                [KeyboardButton(text=get_text('dev_class_business', lang))],
                [KeyboardButton(text=get_text('dev_class_premium', lang))],
                [KeyboardButton(text=get_text('dev_back', lang))]
            ],
            resize_keyboard=True
        )
        
        await message.answer(get_text('dev_choose_housing_class', lang), reply_markup=keyboard)
        await state.set_state(DeveloperPropertyStates.housing_class)
    elif message.text in [get_text('dev_cat_commercial', 'ru'), get_text('dev_cat_commercial', 'uz')]:
        await message.answer(get_text('dev_commercial_coming_soon', lang))


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.housing_class)
async def dev_back_to_category(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_cat_apartment', lang))],
            [KeyboardButton(text=get_text('dev_cat_commercial', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_choose_category', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.property_category)


@dp.message(DeveloperPropertyStates.housing_class)
async def dev_process_housing_class(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    class_map = {
        get_text('dev_class_comfort', 'ru'): "Комфорт",
        get_text('dev_class_comfort', 'uz'): "Комфорт",
        get_text('dev_class_business', 'ru'): "Бизнес",
        get_text('dev_class_business', 'uz'): "Бизнес",
        get_text('dev_class_premium', 'ru'): "Премиум",
        get_text('dev_class_premium', 'uz'): "Премиум",
    }
    
    if message.text not in class_map:
        return
    
    await state.update_data(housing_class=class_map[message.text])
    await message.answer(get_text('dev_enter_rooms', lang), reply_markup=get_dev_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.rooms)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.rooms)
async def dev_back_to_housing_class(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_class_comfort', lang))],
            [KeyboardButton(text=get_text('dev_class_business', lang))],
            [KeyboardButton(text=get_text('dev_class_premium', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_choose_housing_class', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.housing_class)


@dp.message(DeveloperPropertyStates.rooms)
async def dev_process_rooms(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    rooms = validate_number(message.text)
    if rooms is None or rooms < 1 or rooms > 20:
        await message.answer(get_text('dev_invalid_number', lang))
        return
    
    await state.update_data(rooms=int(rooms))
    await message.answer(get_text('dev_enter_area', lang), reply_markup=get_dev_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.area)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.area)
async def dev_back_to_rooms(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    await message.answer(get_text('dev_enter_rooms', lang), reply_markup=get_dev_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.rooms)


@dp.message(DeveloperPropertyStates.area)
async def dev_process_area(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    area = validate_number(message.text)
    if area is None or area < 5 or area > 2000:
        await message.answer(get_text('dev_invalid_number', lang))
        return
    
    await state.update_data(area=float(area))
    await message.answer(get_text('dev_enter_floor', lang), reply_markup=get_dev_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.floor)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.floor)
async def dev_back_to_area(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    await message.answer(get_text('dev_enter_area', lang), reply_markup=get_dev_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.area)


@dp.message(DeveloperPropertyStates.floor)
async def dev_process_floor(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    floor = validate_number(message.text)
    if floor is None or floor < 1 or floor > 100:
        await message.answer(get_text('dev_invalid_number', lang))
        return
    
    await state.update_data(floor=int(floor))
    await message.answer(get_text('dev_enter_total_floors', lang), reply_markup=get_dev_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.total_floors)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.total_floors)
async def dev_back_to_floor(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    await message.answer(get_text('dev_enter_floor', lang), reply_markup=get_dev_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.floor)


@dp.message(DeveloperPropertyStates.total_floors)
async def dev_process_total_floors(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    total_floors = validate_number(message.text)
    if total_floors is None or total_floors < 1 or total_floors > 100:
        await message.answer(get_text('dev_invalid_number', lang))
        return
    
    if int(total_floors) < data.get("floor", 1):
        await message.answer("❌ Этажность дома не может быть меньше этажа квартиры!")
        return
    
    await state.update_data(total_floors=int(total_floors))
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_yes', lang)), KeyboardButton(text=get_text('dev_no', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_has_balcony', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.has_balcony)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.has_balcony)
async def dev_back_to_total_floors(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    await message.answer(get_text('dev_enter_total_floors', lang), reply_markup=get_dev_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.total_floors)


@dp.message(DeveloperPropertyStates.has_balcony)
async def dev_process_has_balcony(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    if message.text in [get_text('dev_yes', 'ru'), get_text('dev_yes', 'uz')]:
        await state.update_data(has_balcony=True)
        await message.answer(get_text('dev_enter_balcony_area', lang), reply_markup=get_dev_back_keyboard(lang))
        await state.set_state(DeveloperPropertyStates.balcony_area)
    elif message.text in [get_text('dev_no', 'ru'), get_text('dev_no', 'uz')]:
        await state.update_data(has_balcony=False, balcony_area=None)
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=get_text('dev_renovation_partial', lang))],
                [KeyboardButton(text=get_text('dev_renovation_full', lang))],
                [KeyboardButton(text=get_text('dev_renovation_clean', lang))],
                [KeyboardButton(text=get_text('dev_renovation_preclean', lang))],
                [KeyboardButton(text=get_text('dev_back', lang))]
            ],
            resize_keyboard=True
        )
        await message.answer(get_text('dev_choose_renovation', lang), reply_markup=keyboard)
        await state.set_state(DeveloperPropertyStates.renovation)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.balcony_area)
async def dev_back_to_has_balcony(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_yes', lang)), KeyboardButton(text=get_text('dev_no', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_has_balcony', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.has_balcony)


@dp.message(DeveloperPropertyStates.balcony_area)
async def dev_process_balcony_area(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    area = validate_number(message.text)
    if area is None or area < 1 or area > 100:
        await message.answer(get_text('dev_invalid_number', lang))
        return
    
    await state.update_data(balcony_area=float(area))
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_renovation_partial', lang))],
            [KeyboardButton(text=get_text('dev_renovation_full', lang))],
            [KeyboardButton(text=get_text('dev_renovation_clean', lang))],
            [KeyboardButton(text=get_text('dev_renovation_preclean', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_choose_renovation', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.renovation)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.renovation)
async def dev_back_to_balcony(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    if data.get('has_balcony'):
        await message.answer(get_text('dev_enter_balcony_area', lang), reply_markup=get_dev_back_keyboard(lang))
        await state.set_state(DeveloperPropertyStates.balcony_area)
    else:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=get_text('dev_yes', lang)), KeyboardButton(text=get_text('dev_no', lang))],
                [KeyboardButton(text=get_text('dev_back', lang))]
            ],
            resize_keyboard=True
        )
        await message.answer(get_text('dev_has_balcony', lang), reply_markup=keyboard)
        await state.set_state(DeveloperPropertyStates.has_balcony)


@dp.message(DeveloperPropertyStates.renovation)
async def dev_process_renovation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    reno_map = {
        get_text('dev_renovation_partial', 'ru'): "Частичный ремонт",
        get_text('dev_renovation_partial', 'uz'): "Частичный ремонт",
        get_text('dev_renovation_full', 'ru'): "Полный ремонт",
        get_text('dev_renovation_full', 'uz'): "Полный ремонт",
        get_text('dev_renovation_clean', 'ru'): "Чистовая отделка",
        get_text('dev_renovation_clean', 'uz'): "Чистовая отделка",
        get_text('dev_renovation_preclean', 'ru'): "Предчистовая отделка",
        get_text('dev_renovation_preclean', 'uz'): "Предчистовая отделка",
    }
    
    if message.text not in reno_map:
        return
    
    await state.update_data(renovation=reno_map[message.text])
    await message.answer(get_text('dev_enter_included', lang), reply_markup=get_dev_skip_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.included_in_price)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.included_in_price)
async def dev_back_to_renovation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_renovation_partial', lang))],
            [KeyboardButton(text=get_text('dev_renovation_full', lang))],
            [KeyboardButton(text=get_text('dev_renovation_clean', lang))],
            [KeyboardButton(text=get_text('dev_renovation_preclean', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_choose_renovation', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.renovation)


@dp.message(DeveloperPropertyStates.included_in_price)
async def dev_process_included(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    if message.text not in [get_text('dev_skip', 'ru'), get_text('dev_skip', 'uz')]:
        await state.update_data(included_in_price=message.text)
    
    db = SessionLocal()
    districts = db.query(District).all()
    db.close()
    
    keyboard_buttons = []
    row = []
    for district in districts:
        row.append(KeyboardButton(text=district.name))
        if len(row) == 2:
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)
    keyboard_buttons.append([KeyboardButton(text=get_text('dev_back', lang))])
    
    keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
    await message.answer(get_text('dev_choose_district', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.district)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.district)
async def dev_back_to_included(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    await message.answer(get_text('dev_enter_included', lang), reply_markup=get_dev_skip_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.included_in_price)


@dp.message(DeveloperPropertyStates.district)
async def dev_process_district(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    db = SessionLocal()
    districts = [d.name for d in db.query(District).all()]
    db.close()
    
    if message.text in districts:
        await state.update_data(district=message.text)
        await message.answer(get_text('dev_enter_metro', lang), reply_markup=get_dev_skip_back_keyboard(lang))
        await state.set_state(DeveloperPropertyStates.metro_station)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.metro_station)
async def dev_back_to_district(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    db = SessionLocal()
    districts = db.query(District).all()
    db.close()
    
    keyboard_buttons = []
    row = []
    for district in districts:
        row.append(KeyboardButton(text=district.name))
        if len(row) == 2:
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)
    keyboard_buttons.append([KeyboardButton(text=get_text('dev_back', lang))])
    
    keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
    await message.answer(get_text('dev_choose_district', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.district)


@dp.message(DeveloperPropertyStates.metro_station)
async def dev_process_metro(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    if message.text in [get_text('dev_skip', 'ru'), get_text('dev_skip', 'uz')]:
        await state.update_data(metro_station=None)
    else:
        await state.update_data(metro_station=message.text)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_skip_location', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_send_location', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.location)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.location)
async def dev_back_to_metro(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    await message.answer(get_text('dev_enter_metro', lang), reply_markup=get_dev_skip_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.metro_station)


@dp.message(DeveloperPropertyStates.location, F.location)
async def dev_process_location_geo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    await state.update_data(
        latitude=message.location.latitude,
        longitude=message.location.longitude
    )
    await message.answer(get_text('dev_enter_price_sqm', lang), reply_markup=get_dev_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.price_per_sqm)


@dp.message(DeveloperPropertyStates.location)
async def dev_process_location_skip(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    if message.text in [get_text('dev_skip_location', 'ru'), get_text('dev_skip_location', 'uz'), get_text('dev_skip', 'ru'), get_text('dev_skip', 'uz')]:
        await state.update_data(latitude=None, longitude=None)
        await message.answer(get_text('dev_enter_price_sqm', lang), reply_markup=get_dev_back_keyboard(lang))
        await state.set_state(DeveloperPropertyStates.price_per_sqm)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.price_per_sqm)
async def dev_back_to_location(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_skip_location', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_send_location', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.location)


@dp.message(DeveloperPropertyStates.price_per_sqm)
async def dev_process_price_sqm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    price = validate_number(message.text.replace("$", "").replace(" ", ""))
    if price is None or price < 100:
        await message.answer(get_text('dev_invalid_number', lang))
        return
    
    await state.update_data(price_per_sqm=int(price))
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_dp_amount', lang))],
            [KeyboardButton(text=get_text('dev_dp_percent', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_down_payment_type', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.down_payment_type)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.down_payment_type)
async def dev_back_to_price_sqm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    await message.answer(get_text('dev_enter_price_sqm', lang), reply_markup=get_dev_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.price_per_sqm)


@dp.message(DeveloperPropertyStates.down_payment_type)
async def dev_process_dp_type(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    if message.text in [get_text('dev_dp_amount', 'ru'), get_text('dev_dp_amount', 'uz')]:
        await state.update_data(down_payment_type='amount')
        await message.answer(get_text('dev_enter_dp_amount', lang), reply_markup=get_dev_back_keyboard(lang))
    elif message.text in [get_text('dev_dp_percent', 'ru'), get_text('dev_dp_percent', 'uz')]:
        await state.update_data(down_payment_type='percent')
        await message.answer(get_text('dev_enter_dp_percent', lang), reply_markup=get_dev_back_keyboard(lang))
    else:
        return
    
    await state.set_state(DeveloperPropertyStates.down_payment_value)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.down_payment_value)
async def dev_back_to_dp_type(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_dp_amount', lang))],
            [KeyboardButton(text=get_text('dev_dp_percent', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_down_payment_type', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.down_payment_type)


@dp.message(DeveloperPropertyStates.down_payment_value)
async def dev_process_dp_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    value = validate_number(message.text.replace("%", "").replace("$", "").replace(" ", ""))
    if value is None:
        await message.answer(get_text('dev_invalid_number', lang))
        return
    
    if data.get('down_payment_type') == 'percent' and (value < 0 or value > 100):
        await message.answer(get_text('dev_invalid_percent', lang))
        return
    
    await state.update_data(down_payment_value=float(value))
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_yes', lang)), KeyboardButton(text=get_text('dev_no', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_has_discount', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.has_discount)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.has_discount)
async def dev_back_to_dp_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    if data.get('down_payment_type') == 'amount':
        await message.answer(get_text('dev_enter_dp_amount', lang), reply_markup=get_dev_back_keyboard(lang))
    else:
        await message.answer(get_text('dev_enter_dp_percent', lang), reply_markup=get_dev_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.down_payment_value)


@dp.message(DeveloperPropertyStates.has_discount)
async def dev_process_has_discount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    if message.text in [get_text('dev_yes', 'ru'), get_text('dev_yes', 'uz')]:
        await state.update_data(discounts=[])
        await message.answer(get_text('dev_enter_discount', lang), reply_markup=get_dev_back_keyboard(lang))
        await state.set_state(DeveloperPropertyStates.discount_conditions)
    elif message.text in [get_text('dev_no', 'ru'), get_text('dev_no', 'uz')]:
        await state.update_data(discounts=[])
        await dev_show_payment_methods(message, state, lang)


async def dev_show_payment_methods(message, state, lang):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_pay_full', lang))],
            [KeyboardButton(text=get_text('dev_pay_mortgage', lang))],
            [KeyboardButton(text=get_text('dev_pay_installment', lang))],
            [KeyboardButton(text=get_text('dev_pay_mixed', lang))],
            [KeyboardButton(text=get_text('dev_payment_done', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    data = await state.get_data()
    selected = data.get('payment_methods', [])
    selected_text = ", ".join(selected) if selected else "-"
    await message.answer(f"{get_text('dev_choose_payment', lang)}\n\nВыбрано: {selected_text}", reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.payment_methods)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.discount_conditions)
async def dev_back_to_has_discount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_yes', lang)), KeyboardButton(text=get_text('dev_no', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_has_discount', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.has_discount)


@dp.message(DeveloperPropertyStates.discount_conditions)
async def dev_process_discount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    discounts = data.get('discounts', [])
    discounts.append(message.text)
    await state.update_data(discounts=discounts)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_yes', lang)), KeyboardButton(text=get_text('dev_no', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_add_more_discount', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.add_more_discount)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.add_more_discount)
async def dev_back_to_discount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    await message.answer(get_text('dev_enter_discount', lang), reply_markup=get_dev_back_keyboard(lang))
    await state.set_state(DeveloperPropertyStates.discount_conditions)


@dp.message(DeveloperPropertyStates.add_more_discount)
async def dev_process_add_more_discount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    if message.text in [get_text('dev_yes', 'ru'), get_text('dev_yes', 'uz')]:
        await message.answer(get_text('dev_enter_discount', lang), reply_markup=get_dev_back_keyboard(lang))
        await state.set_state(DeveloperPropertyStates.discount_conditions)
    elif message.text in [get_text('dev_no', 'ru'), get_text('dev_no', 'uz')]:
        await dev_show_payment_methods(message, state, lang)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.payment_methods)
async def dev_back_to_discounts(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_yes', lang)), KeyboardButton(text=get_text('dev_no', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_has_discount', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.has_discount)


@dp.message(DeveloperPropertyStates.payment_methods)
async def dev_process_payment_method(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    payment_methods = data.get('payment_methods', [])
    
    method_map = {
        get_text('dev_pay_full', 'ru'): "100% оплата",
        get_text('dev_pay_full', 'uz'): "100% оплата",
        get_text('dev_pay_mortgage', 'ru'): "Ипотека",
        get_text('dev_pay_mortgage', 'uz'): "Ипотека",
        get_text('dev_pay_installment', 'ru'): "Рассрочка",
        get_text('dev_pay_installment', 'uz'): "Рассрочка",
        get_text('dev_pay_mixed', 'ru'): "Рассрочка + Ипотека",
        get_text('dev_pay_mixed', 'uz'): "Рассрочка + Ипотека",
    }
    
    if message.text in [get_text('dev_payment_done', 'ru'), get_text('dev_payment_done', 'uz')]:
        if not payment_methods:
            await message.answer("❌ Выберите хотя бы один метод оплаты!")
            return
        
        if "Ипотека" in payment_methods:
            await message.answer(get_text('dev_mortgage_dp', lang), reply_markup=get_dev_back_keyboard(lang))
            await state.set_state(DeveloperPropertyStates.mortgage_details)
        elif "Рассрочка" in payment_methods:
            await message.answer(get_text('dev_installment_dp', lang), reply_markup=get_dev_back_keyboard(lang))
            await state.set_state(DeveloperPropertyStates.installment_details)
        else:
            await dev_show_photos_step(message, state, lang)
    elif message.text in method_map:
        method = method_map[message.text]
        if method in payment_methods:
            payment_methods.remove(method)
        else:
            payment_methods.append(method)
        await state.update_data(payment_methods=payment_methods)
        await dev_show_payment_methods(message, state, lang)


async def dev_show_photos_step(message, state, lang):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_skip_photos', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('dev_add_photos', lang), reply_markup=keyboard)
    await state.set_state(DeveloperPropertyStates.photos)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.mortgage_details)
async def dev_back_to_payment_methods(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    await dev_show_payment_methods(message, state, lang)


@dp.message(DeveloperPropertyStates.mortgage_details)
async def dev_process_mortgage(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    mortgage_step = data.get('mortgage_step', 'dp')
    
    value = validate_number(message.text.replace("%", "").replace(" ", ""))
    if value is None:
        await message.answer(get_text('dev_invalid_number', lang))
        return
    
    if mortgage_step == 'dp':
        if value < 0 or value > 100:
            await message.answer(get_text('dev_invalid_percent', lang))
            return
        await state.update_data(mortgage_down_payment=float(value), mortgage_step='months')
        await message.answer(get_text('dev_mortgage_months', lang), reply_markup=get_dev_back_keyboard(lang))
    elif mortgage_step == 'months':
        await state.update_data(mortgage_months=int(value), mortgage_step='grace')
        await message.answer(get_text('dev_mortgage_grace', lang), reply_markup=get_dev_back_keyboard(lang))
    elif mortgage_step == 'grace':
        await state.update_data(mortgage_grace_period=int(value), mortgage_step='dp')
        
        payment_methods = data.get('payment_methods', [])
        if "Рассрочка" in payment_methods:
            await state.update_data(installment_step='dp')
            await message.answer(get_text('dev_installment_dp', lang), reply_markup=get_dev_back_keyboard(lang))
            await state.set_state(DeveloperPropertyStates.installment_details)
        else:
            await dev_show_photos_step(message, state, lang)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.installment_details)
async def dev_back_from_installment(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    payment_methods = data.get('payment_methods', [])
    if "Ипотека" in payment_methods:
        await state.update_data(mortgage_step='dp')
        await message.answer(get_text('dev_mortgage_dp', lang), reply_markup=get_dev_back_keyboard(lang))
        await state.set_state(DeveloperPropertyStates.mortgage_details)
    else:
        await dev_show_payment_methods(message, state, lang)


@dp.message(DeveloperPropertyStates.installment_details)
async def dev_process_installment(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    installment_step = data.get('installment_step', 'dp')
    
    value = validate_number(message.text.replace("%", "").replace(" ", ""))
    if value is None:
        await message.answer(get_text('dev_invalid_number', lang))
        return
    
    if installment_step == 'dp':
        if value < 0 or value > 100:
            await message.answer(get_text('dev_invalid_percent', lang))
            return
        await state.update_data(installment_down_payment=float(value), installment_step='months')
        await message.answer(get_text('dev_installment_months', lang), reply_markup=get_dev_back_keyboard(lang))
    elif installment_step == 'months':
        await state.update_data(installment_months=int(value), installment_step='grace')
        await message.answer(get_text('dev_installment_grace', lang), reply_markup=get_dev_back_keyboard(lang))
    elif installment_step == 'grace':
        await state.update_data(installment_grace_period=int(value), installment_step='dp')
        await dev_show_photos_step(message, state, lang)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), DeveloperPropertyStates.photos)
async def dev_back_from_photos(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    payment_methods = data.get('payment_methods', [])
    if "Рассрочка" in payment_methods:
        await state.update_data(installment_step='dp')
        await message.answer(get_text('dev_installment_dp', lang), reply_markup=get_dev_back_keyboard(lang))
        await state.set_state(DeveloperPropertyStates.installment_details)
    elif "Ипотека" in payment_methods:
        await state.update_data(mortgage_step='dp')
        await message.answer(get_text('dev_mortgage_dp', lang), reply_markup=get_dev_back_keyboard(lang))
        await state.set_state(DeveloperPropertyStates.mortgage_details)
    else:
        await dev_show_payment_methods(message, state, lang)


@dp.message(DeveloperPropertyStates.photos, F.photo)
async def dev_process_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    photos = data.get("photos", [])
    
    if len(photos) >= 10:
        await message.answer("⚠️ Достигнут лимит в 10 фотографий!")
        return
    
    photo_id = message.photo[-1].file_id
    photos.append(photo_id)
    await state.update_data(photos=photos)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dev_photos_done', lang))],
            [KeyboardButton(text=get_text('dev_back', lang))]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"✅ Фото добавлено ({len(photos)}/10)\n\nОтправьте еще фото или нажмите 'Готово'",
        reply_markup=keyboard
    )


@dp.message(DeveloperPropertyStates.photos)
async def dev_photos_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    if message.text in [get_text('dev_photos_done', 'ru'), get_text('dev_photos_done', 'uz'), 
                        get_text('dev_skip_photos', 'ru'), get_text('dev_skip_photos', 'uz')]:
        await dev_save_property(message, state, lang)


async def dev_save_property(message, state, lang):
    from aiogram.types import InputMediaPhoto
    
    data = await state.get_data()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    photos_str = ",".join(data.get("photos", []))
    
    area = data.get("area", 50)
    price_per_sqm = data.get("price_per_sqm", 1000)
    total_price = int(area * price_per_sqm)
    
    prop = Property(
        owner_id=user.id,
        property_type=data.get("property_type", PropertyType.SALE),
        category="Квартира",
        housing_class=data.get("housing_class"),
        district=data.get("district", ""),
        rooms=data.get("rooms", 1),
        floor=data.get("floor", 1),
        total_floors=data.get("total_floors", 9),
        area=area,
        price=total_price,
        price_per_sqm=price_per_sqm,
        has_balcony=data.get("has_balcony", False),
        balcony_area=data.get("balcony_area"),
        renovation=data.get("renovation", ""),
        included_in_price=data.get("included_in_price"),
        metro_station=data.get("metro_station"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        down_payment_type=data.get("down_payment_type"),
        down_payment_value=data.get("down_payment_value"),
        discounts=json.dumps(data.get("discounts", []), ensure_ascii=False) if data.get("discounts") else None,
        payment_methods=json.dumps(data.get("payment_methods", []), ensure_ascii=False) if data.get("payment_methods") else None,
        mortgage_down_payment=data.get("mortgage_down_payment"),
        mortgage_months=data.get("mortgage_months"),
        mortgage_grace_period=data.get("mortgage_grace_period"),
        installment_down_payment=data.get("installment_down_payment"),
        installment_months=data.get("installment_months"),
        installment_grace_period=data.get("installment_grace_period"),
        has_mixed_payment="Рассрочка + Ипотека" in data.get("payment_methods", []),
        photos=photos_str,
        layout_photos="",
        status=PropertyStatus.MODERATION,
        source='manual'
    )
    db.add(prop)
    db.commit()
    
    prop.unique_id = f"F2F-{prop.id:05d}"
    db.commit()
    
    unique_id = prop.unique_id
    db.close()
    
    type_name = "Продажа" if data.get("property_type") == PropertyType.SALE else "Аренда"
    balcony_text = f"Да ({data.get('balcony_area')} м²)" if data.get('has_balcony') else "Нет"
    
    dp_text = ""
    if data.get("down_payment_type") == "amount":
        dp_text = f"{int(data.get('down_payment_value', 0)):,} сум"
    elif data.get("down_payment_type") == "percent":
        dp_text = f"{data.get('down_payment_value', 0)}%"
    
    discounts_text = "\n".join(data.get("discounts", [])) if data.get("discounts") else "Нет"
    payment_text = ", ".join(data.get("payment_methods", []))
    
    summary = (
        f"📝 Объявление отправлено на модерацию!\n\n"
        f"🆔 <b>ID: {unique_id}</b>\n\n"
        f"📋 ХАРАКТЕРИСТИКИ:\n"
        f"🏷 Тип сделки: {type_name}\n"
        f"🏠 Класс жилья: {data.get('housing_class', '')}\n"
        f"📍 Район: {data.get('district', '')}\n"
        f"🚇 Метро: {data.get('metro_station', 'Не указано')}\n"
        f"🚪 Комнат: {data.get('rooms', '')}\n"
        f"🏢 Этаж: {data.get('floor', '')}/{data.get('total_floors', '')}\n"
        f"📐 Площадь: {area} м²\n"
        f"🪟 Балкон: {balcony_text}\n"
        f"🔨 Ремонт: {data.get('renovation', '')}\n"
        f"💵 Цена за м²: {price_per_sqm:,} сум\n"
        f"💰 Общая стоимость: {total_price:,} сум\n"
        f"💳 Первоначальный взнос: {dp_text}\n\n"
        f"🏷 Скидки:\n{discounts_text}\n\n"
        f"💳 Методы оплаты: {payment_text}\n"
    )
    
    if data.get("mortgage_months"):
        summary += f"🏦 Ипотека: {data.get('mortgage_down_payment', 0)}% взнос, {data.get('mortgage_months')} мес."
        if data.get("mortgage_grace_period"):
            summary += f", льготный период {data.get('mortgage_grace_period')} мес."
        summary += "\n"
    
    if data.get("installment_months"):
        summary += f"📄 Рассрочка: {data.get('installment_down_payment', 0)}% взнос, {data.get('installment_months')} мес."
        if data.get("installment_grace_period"):
            summary += f", льготный период {data.get('installment_grace_period')} мес."
        summary += "\n"
    
    if data.get("included_in_price"):
        summary += f"\n📦 В стоимость входит:\n{data.get('included_in_price')}"
    
    photos_list = data.get("photos", [])
    
    await state.clear()
    
    if photos_list:
        media_group = []
        for i, photo_id in enumerate(photos_list):
            if i == 0:
                media_group.append(InputMediaPhoto(media=photo_id, caption=summary[:1024], parse_mode="HTML"))
            else:
                media_group.append(InputMediaPhoto(media=photo_id))
        await message.answer_media_group(media_group)
    else:
        await message.answer(summary, parse_mode="HTML")
    
    buyers_count = get_active_buyers_count(
        rooms=data.get("rooms"),
        district=data.get("district"),
        budget_max=total_price
    )
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    is_developer = user.seller_type == SellerType.DEVELOPER if user else False
    db.close()
    
    keyboard = get_seller_menu(lang, is_developer=is_developer)
    
    await message.answer(
        f"🎯 {buyers_count} покупателей ищут похожие квартиры.\n"
        f"Ваш объект уже виден им в ленте!",
        reply_markup=keyboard
    )


# =====================================================
# END DEVELOPER PROPERTY FORM HANDLERS
# =====================================================


@dp.message(F.text.in_(["🏠 Смотреть квартиры", "🏠 Kvartiralarni ko'rish"]))
async def view_properties(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    liked_ids = [l.property_id for l in db.query(Like).filter(Like.user_id == user.id).all()]
    skipped_ids_data = await state.get_data()
    skipped_ids = skipped_ids_data.get("skipped_ids", [])
    
    from sqlalchemy import or_
    query = db.query(Property).filter(
        Property.status == PropertyStatus.ACTIVE,
        or_(Property.owner_id != user.id, Property.source == 'olx')
    )
    
    deal_type = user.search_deal_type or "sale"
    if deal_type in ["rent", "Аренда"]:
        query = query.filter(Property.property_type == PropertyType.RENT)
    else:
        query = query.filter(Property.property_type == PropertyType.SALE)
    
    if user.search_rooms and user.search_rooms not in ["any", "Любое", ""]:
        rooms_list = [int(r.strip()) for r in user.search_rooms.split(",") if r.strip().isdigit()]
        if rooms_list:
            query = query.filter(Property.rooms.in_(rooms_list))
    
    if user.search_housing_type and user.search_housing_type not in ["Любой", "any", "", "Квартира", "Дом", "Участок", "Коммерция", "Kvartira", "Uy", "Yer", "Tijorat"]:
        housing_base = user.search_housing_type.rstrip("аи")
        query = query.filter(Property.housing_type.ilike(f"%{housing_base}%"))
    
    if user.search_district and user.search_district not in ["Любой", ""]:
        districts = [d.strip() for d in user.search_district.split(",") if d.strip() and d.strip() != "Любой"]
        if districts:
            district_filters = []
            for d in districts:
                district_base = d.replace("ский", "").replace("ий", "")
                district_filters.append(Property.district.ilike(f"%{district_base}%"))
            query = query.filter(or_(*district_filters))
    
    if user.search_budget_max:
        query = query.filter(Property.price <= user.search_budget_max)
    
    if user.search_budget_min:
        query = query.filter(Property.price >= user.search_budget_min)
    
    if user.search_floor and user.search_floor not in ["any", "Любой", ""]:
        floor_filter = user.search_floor
        if floor_filter == "1":
            query = query.filter(Property.floor == 1)
        elif floor_filter == "2-4":
            query = query.filter(Property.floor >= 2, Property.floor <= 4)
        elif floor_filter == "5-7":
            query = query.filter(Property.floor >= 5, Property.floor <= 7)
        elif floor_filter == "8+":
            query = query.filter(Property.floor >= 8)
        elif "-" in floor_filter:
            parts = floor_filter.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                query = query.filter(Property.floor >= int(parts[0]), Property.floor <= int(parts[1]))
        elif floor_filter.isdigit():
            query = query.filter(Property.floor == int(floor_filter))
    
    if user.search_area_min:
        query = query.filter(Property.area >= user.search_area_min)
    if user.search_area_max:
        query = query.filter(Property.area <= user.search_area_max)
    
    if user.search_building_type:
        query = query.filter(or_(
            Property.building_type.ilike(f"%{user.search_building_type}%"),
            Property.building_type == None,
            Property.building_type == ""
        ))
    
    if user.search_renovation:
        query = query.filter(or_(
            Property.renovation.ilike(f"%{user.search_renovation}%"),
            Property.renovation == None,
            Property.renovation == ""
        ))
    
    if user.search_furniture:
        pass
    
    if user.search_bathroom:
        query = query.filter(or_(
            Property.bathroom_type.ilike(f"%{user.search_bathroom}%"),
            Property.bathroom_type == None,
            Property.bathroom_type == ""
        ))
    
    if liked_ids:
        query = query.filter(Property.id.notin_(liked_ids))
    if skipped_ids:
        query = query.filter(Property.id.notin_(skipped_ids))
    
    from sqlalchemy import case
    tariff_priority = case(
        (User.tariff == TariffType.PREMIUM, 1),
        (User.tariff == TariffType.DEVELOPER_PRO, 1),
        (User.tariff == TariffType.PRO, 2),
        (User.tariff == TariffType.AGENCY_START, 2),
        (User.tariff == TariffType.FREE, 3),
        else_=4
    )
    source_priority = case(
        (Property.source == 'olx', 5),
        else_=0
    )
    
    properties = query.join(User, Property.owner_id == User.id).order_by(
        source_priority.asc(),
        tariff_priority.asc(),
        Property.created_at.desc()
    ).all()
    
    db.close()
    
    if not properties:
        lang = user.language or 'ru'
        quick_actions = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📍 Изменить район" if lang == 'ru' else "📍 Tumanni o'zgartirish", callback_data="quick_change_district")],
            [InlineKeyboardButton(text="💰 Изменить бюджет" if lang == 'ru' else "💰 Byudjetni o'zgartirish", callback_data="quick_change_budget")]
        ])
        if liked_ids or skipped_ids:
            await message.answer(
                "✅ Вы просмотрели все доступные квартиры!\n\nПопробуйте позже — появятся новые объекты." if lang == 'ru' else "✅ Siz barcha mavjud kvartiralarni ko'rib chiqdingiz!\n\nKeyinroq urinib ko'ring — yangi obyektlar paydo bo'ladi.",
                reply_markup=quick_actions
            )
        else:
            await message.answer(
                "😔 Пока нет квартир по вашим критериям. Попробуйте позже!" if lang == 'ru' else "😔 Hozircha sizning mezonlaringiz bo'yicha kvartiralar yo'q. Keyinroq urinib ko'ring!",
                reply_markup=quick_actions
            )
        return
    
    await state.update_data(properties=[p.id for p in properties], current_index=0)
    await show_property_card(message, properties[0].id, state)
    await state.set_state(SearchStates.viewing_properties)


async def show_property_card(message, property_id, state=None):
    db = SessionLocal()
    prop = db.query(Property).filter(Property.id == property_id).first()
    
    if not prop:
        await message.answer("Объект не найден")
        db.close()
        return
    
    prop.views_count += 1
    db.commit()
    
    # Get user language and currency preference
    viewer = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(viewer)
    user_currency = viewer.search_currency if viewer and viewer.search_currency else 'USD'
    
    contact_phone = prop.phone if prop.phone else None
    if not contact_phone:
        owner = db.query(User).filter(User.id == prop.owner_id).first()
        contact_phone = owner.phone if owner and owner.phone else ("Не указан" if lang == 'ru' else "Ko'rsatilmagan")
    
    type_emoji = "🏷" if prop.property_type == PropertyType.SALE else "🔑"
    type_name = "ПРОДАЖА" if prop.property_type == PropertyType.SALE else "АРЕНДА"
    
    text = f"{type_emoji} <b>{type_name}</b>  •  ID: {prop.id}\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Format price based on user's currency preference
    # Properties are stored in UZS (sums)
    price_display = format_price_for_user(prop.price, 'UZS', user_currency)
    text += f"💰 <b>{price_display}</b>\n"
    
    if prop.olx_title:
        text += f"📝 {prop.olx_title}\n"
    
    text += "\n"
    
    details = []
    if prop.district:
        details.append(f"📍 {prop.district}")
    if prop.rooms:
        details.append(f"🚪 {prop.rooms} комн.")
    if prop.area:
        details.append(f"📐 {prop.area} м²")
    if prop.floor and prop.total_floors:
        details.append(f"🏢 {prop.floor}/{prop.total_floors} этаж")
    elif prop.floor:
        details.append(f"🏢 {prop.floor} этаж")
    
    if details:
        text += "\n".join(details) + "\n"
    
    extras = []
    if prop.building_type:
        extras.append(prop.building_type)
    if prop.renovation:
        extras.append(prop.renovation)
    if prop.has_furniture:
        extras.append("с мебелью")
    if prop.bathroom_type:
        extras.append(prop.bathroom_type)
    
    if extras:
        text += f"\n🏠 {' • '.join(extras)}\n"
    
    text += "\n━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📞 <b><u>Контакт: {contact_phone}</u></b>\n"
    
    if prop.description:
        max_desc_len = 500
        desc = prop.description[:max_desc_len] + "..." if len(prop.description) > max_desc_len else prop.description
        text += f"\n💬 <i>{desc}</i>"
    
    text += "\n\n🔍 @F2F_Tashkent_Bot"
    
    if len(text) > 1024:
        text = text[:1020] + "..."
    
    search_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('dislike', lang)), KeyboardButton(text=get_text('like', lang))],
            [KeyboardButton(text=get_text('back_button', lang))]
        ],
        resize_keyboard=True
    )
    
    if state:
        await state.update_data(current_property_id=prop.id)
    
    photos = [p for p in (prop.photos.split(",") if prop.photos else []) if p]
    
    db.close()
    
    if photos:
        from aiogram.types import InputMediaPhoto
        if len(photos) > 1:
            await message.answer("🏠", reply_markup=search_keyboard)
            media_group = []
            for i, photo_id in enumerate(photos[:10]):
                if i == 0:
                    media_group.append(InputMediaPhoto(media=photo_id, caption=text, parse_mode="HTML"))
                else:
                    media_group.append(InputMediaPhoto(media=photo_id))
            await message.answer_media_group(media_group)
        else:
            await message.answer_photo(photo=photos[0], caption=text, reply_markup=search_keyboard, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=search_keyboard, parse_mode="HTML")


@dp.message(F.text.in_(["❤️ Нравится", "❤️ Yoqdi"]), SearchStates.viewing_properties)
async def process_like_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    property_id = data.get("current_property_id")
    
    if not property_id:
        return
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    prop = db.query(Property).filter(Property.id == property_id).first()
    
    if user and prop:
        existing_like = db.query(Like).filter(
            Like.user_id == user.id,
            Like.property_id == property_id
        ).first()
        
        if not existing_like:
            like = Like(
                user_id=user.id,
                property_id=property_id,
                property_owner_id=prop.owner_id
            )
            db.add(like)
            prop.likes_count += 1
            db.commit()
            
            owner = db.query(User).filter(User.id == prop.owner_id).first()
            if owner:
                try:
                    await bot.send_message(
                        owner.telegram_id,
                        f"❤️ Новый лайк!\n\n"
                        f"Пользователь заинтересовался вашим объектом:\n"
                        f"📍 {prop.district}\n"
                        f"💰 {prop.price:,} сум\n\n"
                        f"Перейдите в раздел 'Меня лайкнули', чтобы открыть контакт!"
                    )
                except:
                    pass
    
    db.close()
    
    await message.answer("❤️ Лайк отправлен!")
    await show_next_property_reply(message, state)


@dp.message(F.text.in_(["❌ Не нравится", "❌ Yoqmadi"]), SearchStates.viewing_properties)
async def process_skip_reply(message: types.Message, state: FSMContext):
    await show_next_property_reply(message, state)


@dp.message(F.text.in_(["🔙 Назад", "🔙 Orqaga"]), SearchStates.viewing_properties)
async def process_back_reply(message: types.Message, state: FSMContext):
    await state.clear()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    db.close()
    
    if user and user.role == UserRole.BUYER:
        keyboard = get_buyer_menu(lang)
    else:
        is_developer = user.seller_type == SellerType.DEVELOPER if user else False
        keyboard = get_seller_menu(lang, is_developer=is_developer)
    
    await message.answer(get_text('returned_to_menu', lang), reply_markup=keyboard)


async def show_advertisement(message, ad, state):
    """Показывает рекламный пост"""
    text = "📢 <b>РЕКЛАМА</b>\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    if ad.title:
        text += f"📌 <b>{ad.title}</b>\n\n"
    
    if ad.description:
        text += f"{ad.description}\n"
    
    text += "\n━━━━━━━━━━━━━━━━━━━━"
    
    ad_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➡️ Далее")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )
    
    photos = [p.strip() for p in (ad.media.split(",") if ad.media else []) if p.strip()]
    
    if photos:
        from aiogram.types import InputMediaPhoto
        media_type = ad.media_type or 'photo'
        
        if media_type == 'video':
            try:
                await message.answer_video(video=photos[0], caption=text, reply_markup=ad_keyboard, parse_mode="HTML")
            except Exception as e:
                print(f"Video error: {e}")
                await message.answer(text, reply_markup=ad_keyboard, parse_mode="HTML")
        elif len(photos) > 1:
            await message.answer("📢", reply_markup=ad_keyboard)
            media_group = []
            for i, photo_id in enumerate(photos[:10]):
                if i == 0:
                    media_group.append(InputMediaPhoto(media=photo_id, caption=text, parse_mode="HTML"))
                else:
                    media_group.append(InputMediaPhoto(media=photo_id))
            try:
                await message.answer_media_group(media_group)
            except Exception as e:
                print(f"Media group error: {e}")
                await message.answer(text, reply_markup=ad_keyboard, parse_mode="HTML")
        else:
            try:
                await message.answer_photo(photo=photos[0], caption=text, reply_markup=ad_keyboard, parse_mode="HTML")
            except Exception as e:
                print(f"Photo error: {e}, file_id: {photos[0]}")
                await message.answer(text, reply_markup=ad_keyboard, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=ad_keyboard, parse_mode="HTML")
    
    db = SessionLocal()
    ad_to_update = db.query(Advertisement).filter(Advertisement.id == ad.id).first()
    if ad_to_update:
        ad_to_update.views_count += 1
        db.commit()
    db.close()


async def show_next_property_reply(message, state):
    data = await state.get_data()
    properties = data.get("properties", [])
    current_index = data.get("current_index", 0) + 1
    viewed_count = data.get("viewed_count", 0) + 1
    
    if current_index >= len(properties):
        db = SessionLocal()
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        lang = get_user_lang(user)
        db.close()
        
        keyboard = get_buyer_menu(lang)
        
        quick_actions = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📍 Изменить район" if lang == 'ru' else "📍 Tumanni o'zgartirish", callback_data="quick_change_district")],
            [InlineKeyboardButton(text="💰 Изменить бюджет" if lang == 'ru' else "💰 Byudjetni o'zgartirish", callback_data="quick_change_budget")]
        ])
        
        await message.answer(
            get_text('all_properties_viewed', lang),
            reply_markup=quick_actions
        )
        await message.answer("👇", reply_markup=keyboard)
        await state.clear()
        return
    
    if viewed_count > 0 and viewed_count % 5 == 0:
        db = SessionLocal()
        active_ads = db.query(Advertisement).filter(Advertisement.is_active == True).all()
        db.close()
        
        if active_ads:
            random_ad = random.choice(active_ads)
            await state.update_data(current_index=current_index, viewed_count=viewed_count, showing_ad=True)
            await show_advertisement(message, random_ad, state)
            await state.set_state(SearchStates.viewing_ad)
            return
    
    await state.update_data(current_index=current_index, viewed_count=viewed_count)
    await show_property_card(message, properties[current_index], state)


@dp.message(F.text.in_(["➡️ Далее", "➡️ Keyingi"]), SearchStates.viewing_ad)
async def continue_after_ad(message: types.Message, state: FSMContext):
    """Продолжить просмотр после рекламы"""
    data = await state.get_data()
    properties = data.get("properties", [])
    current_index = data.get("current_index", 0)
    
    if current_index >= len(properties):
        db = SessionLocal()
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        lang = get_user_lang(user)
        db.close()
        keyboard = get_buyer_menu(lang)
        await message.answer(
            get_text('all_properties_viewed', lang),
            reply_markup=keyboard
        )
        await state.clear()
        return
    
    await state.set_state(SearchStates.viewing_properties)
    await show_property_card(message, properties[current_index], state)


@dp.message(F.text.in_(["🔙 Назад", "🔙 Orqaga"]), SearchStates.viewing_ad)
async def back_from_ad(message: types.Message, state: FSMContext):
    """Вернуться в меню из рекламы"""
    await state.clear()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    db.close()
    
    if user and user.role == UserRole.BUYER:
        keyboard = get_buyer_menu(lang)
    else:
        is_developer = user.seller_type == SellerType.DEVELOPER if user else False
        keyboard = get_seller_menu(lang, is_developer=is_developer)
    
    await message.answer(get_text('returned_to_menu', lang), reply_markup=keyboard)


@dp.message(F.text.in_(["🏢 Мои объекты", "🏢 Mening obyektlarim"]))
async def my_properties(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    properties = db.query(Property).filter(Property.owner_id == user.id).order_by(Property.created_at.desc()).all()
    db.close()
    
    if not properties:
        await message.answer("У вас пока нет объектов. Нажмите '➕ Добавить объект'!")
        return
    
    status_emoji = {
        PropertyStatus.ACTIVE: "🟢",
        PropertyStatus.MODERATION: "🟡",
        PropertyStatus.ARCHIVE: "⚫"
    }
    
    status_names = {
        PropertyStatus.ACTIVE: "Активно",
        PropertyStatus.MODERATION: "На модерации",
        PropertyStatus.ARCHIVE: "В архиве"
    }
    
    now = datetime.utcnow()
    
    for prop in properties:
        emoji = status_emoji.get(prop.status, "⚪")
        status_name = status_names.get(prop.status, "")
        type_str = "Продажа" if prop.property_type == PropertyType.SALE else "Аренда"
        
        timer_info = ""
        if prop.status == PropertyStatus.ACTIVE and prop.created_at:
            days_active = (now - prop.created_at).days
            days_left = 30 - days_active
            if days_left > 0:
                timer_info = f"⏰ До архива: {days_left} дн.\n"
            else:
                timer_info = f"⏰ Скоро в архив\n"
        elif prop.status == PropertyStatus.ARCHIVE and prop.archived_at:
            days_in_archive = (now - prop.archived_at).days
            days_left = 30 - days_in_archive
            if days_left > 0:
                timer_info = f"⏰ До удаления: {days_left} дн.\n"
            else:
                timer_info = f"⏰ Скоро будет удалено\n"
        
        floor_info = ""
        if prop.floor and prop.total_floors:
            floor_info = f"🏢 Этаж: {prop.floor}/{prop.total_floors}\n"
        elif prop.floor:
            floor_info = f"🏢 Этаж: {prop.floor}\n"
        
        area_info = f"📐 Площадь: {prop.area} м²\n" if prop.area else ""
        
        building_names = {
            "brick": "Кирпичный",
            "monolith": "Монолитный", 
            "panel": "Панельный",
            "block": "Блочный",
            "wood": "Деревянный"
        }
        building_info = f"🧱 Дом: {building_names.get(prop.building_type, prop.building_type)}\n" if prop.building_type else ""
        
        renovation_names = {
            "new": "Новый ремонт",
            "medium": "Средний ремонт",
            "needs": "Требует ремонта",
            "rough": "Чистовая отделка",
            "shell": "Коробка"
        }
        renovation_info = f"🔧 Ремонт: {renovation_names.get(prop.renovation, prop.renovation)}\n" if prop.renovation else ""
        
        furniture_info = "🛋 С мебелью\n" if prop.has_furniture else ""
        
        prop_unique_id = prop.unique_id or f"F2F-{prop.id:05d}"
        
        text = (
            f"{emoji} <b>{prop.district or 'Объект'}</b> — {status_name}\n"
            f"🆔 <code>{prop_unique_id}</code>\n"
            f"{timer_info}"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 {type_str} | {prop.rooms} комн. | <b>{prop.price:,} сум</b>\n"
            f"{area_info}"
            f"{floor_info}"
            f"{building_info}"
            f"{renovation_info}"
            f"{furniture_info}"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👁 Просмотров: {prop.views_count} | ❤️ Лайков: {prop.likes_count}\n"
        )
        
        buttons = [
            [
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"prop_edit_{prop.id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"prop_delete_{prop.id}")
            ]
        ]
        
        if prop.status == PropertyStatus.ACTIVE:
            buttons.append([InlineKeyboardButton(text="📦 В архив", callback_data=f"prop_toggle_{prop.id}")])
        elif prop.status == PropertyStatus.ARCHIVE:
            buttons.append([InlineKeyboardButton(text="✅ Активировать", callback_data=f"prop_toggle_{prop.id}")])
        # For MODERATION status - no toggle button, only admin can approve
        if prop.likes_count > 0:
            buttons.append([
                InlineKeyboardButton(text=f"❤️ Кто лайкнул ({prop.likes_count})", callback_data=f"prop_likers_{prop.id}")
            ])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        photos_list = [p for p in (prop.photos.split(",") if prop.photos else []) if p]
        photos_count = len(photos_list)
        
        if photos_count > 1:
            text += f"\n📷 Фото: {photos_count} шт."
        
        if photos_list:
            try:
                from aiogram.types import InputMediaPhoto
                if len(photos_list) > 1:
                    media_group = []
                    for i, photo_id in enumerate(photos_list[:10]):
                        if i == 0:
                            media_group.append(InputMediaPhoto(media=photo_id, caption=text, parse_mode="HTML"))
                        else:
                            media_group.append(InputMediaPhoto(media=photo_id))
                    await message.answer_media_group(media_group)
                    await message.answer("⬇️ Действия:", reply_markup=keyboard)
                else:
                    await message.answer_photo(
                        photo=photos_list[0],
                        caption=text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
            except:
                await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@dp.callback_query(F.data.startswith("prop_likers_"))
async def show_property_likers(callback: types.CallbackQuery):
    prop_id = int(callback.data.replace("prop_likers_", ""))
    
    db = SessionLocal()
    prop = db.query(Property).filter(Property.id == prop_id).first()
    
    if not prop:
        await callback.answer("Объект не найден")
        db.close()
        return
    
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    if not user or prop.owner_id != user.id:
        await callback.answer("Нет доступа")
        db.close()
        return
    
    likes = db.query(Like).filter(Like.property_id == prop_id).order_by(Like.created_at.desc()).all()
    
    if not likes:
        await callback.answer("Пока нет лайков")
        db.close()
        return
    
    text = f"❤️ <b>Кто лайкнул объект в {prop.district}:</b>\n\n"
    
    for like in likes:
        liker = db.query(User).filter(User.id == like.user_id).first()
        if liker:
            time_ago = datetime.now() - like.created_at
            hours = int(time_ago.total_seconds() // 3600)
            time_str = f"{hours} ч. назад" if hours > 0 else "только что"
            
            budget_str = f"💰 Бюджет: до ${liker.search_budget_max:,}\n" if liker.search_budget_max else ""
            
            text += (
                f"👤 <b>{liker.first_name or 'Покупатель'}</b>\n"
                f"📞 {liker.phone or 'Телефон не указан'}\n"
                f"🔍 Ищет: {liker.search_rooms or 'любые'} комн. | {liker.search_district or 'любой район'}\n"
                f"{budget_str}"
                f"⏰ {time_str}\n\n"
            )
    
    db.close()
    
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


class EditPropertyStates(StatesGroup):
    choosing_field = State()
    editing_price = State()
    editing_rooms = State()
    editing_area = State()
    editing_floor = State()
    editing_description = State()
    editing_photos = State()
    editing_location = State()


@dp.callback_query(F.data.startswith("prop_toggle_"))
async def toggle_property_status(callback: types.CallbackQuery):
    prop_id = int(callback.data.replace("prop_toggle_", ""))
    
    db = SessionLocal()
    prop = db.query(Property).filter(Property.id == prop_id).first()
    
    if not prop:
        await callback.answer("Объект не найден")
        db.close()
        return
    
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    if not user or prop.owner_id != user.id:
        await callback.answer("Нет доступа")
        db.close()
        return
    
    if prop.status == PropertyStatus.ACTIVE:
        prop.status = PropertyStatus.ARCHIVE
        prop.archived_at = datetime.utcnow()
        new_status = "В архиве"
    else:
        prop.status = PropertyStatus.ACTIVE
        prop.created_at = datetime.utcnow()
        prop.archived_at = None
        new_status = "Активно (таймер сброшен)"
    
    db.commit()
    db.close()
    
    await callback.answer(f"Статус изменён: {new_status}")
    await callback.message.delete()


@dp.callback_query(F.data.startswith("prop_delete_"))
async def delete_property_confirm(callback: types.CallbackQuery):
    prop_id = int(callback.data.replace("prop_delete_", ""))
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"prop_confirm_del_{prop_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"prop_cancel_del_{prop_id}")
        ]
    ])
    
    try:
        await callback.message.edit_text(
            "⚠️ <b>Вы уверены, что хотите удалить этот объект?</b>\n\n"
            "Это действие нельзя отменить.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except:
        await callback.message.delete()
        await callback.message.answer(
            "⚠️ <b>Вы уверены, что хотите удалить этот объект?</b>\n\n"
            "Это действие нельзя отменить.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )


@dp.callback_query(F.data.startswith("prop_confirm_del_"))
async def delete_property_confirmed(callback: types.CallbackQuery):
    prop_id = int(callback.data.replace("prop_confirm_del_", ""))
    
    db = SessionLocal()
    prop = db.query(Property).filter(Property.id == prop_id).first()
    
    if not prop:
        await callback.answer("Объект не найден")
        db.close()
        return
    
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    if not user or prop.owner_id != user.id:
        await callback.answer("Нет доступа")
        db.close()
        return
    
    db.delete(prop)
    db.commit()
    db.close()
    
    try:
        await callback.message.edit_text("✅ Объект успешно удалён!")
    except:
        await callback.message.delete()
        await callback.message.answer("✅ Объект успешно удалён!")


@dp.callback_query(F.data.startswith("prop_cancel_del_"))
async def delete_property_cancelled(callback: types.CallbackQuery):
    await callback.answer("Удаление отменено")
    await callback.message.delete()


@dp.callback_query(F.data.startswith("prop_edit_"))
async def edit_property_menu(callback: types.CallbackQuery, state: FSMContext):
    prop_id = int(callback.data.replace("prop_edit_", ""))
    
    await state.update_data(editing_prop_id=prop_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Цена", callback_data=f"edit_field_price")],
        [InlineKeyboardButton(text="🚪 Комнаты", callback_data=f"edit_field_rooms")],
        [InlineKeyboardButton(text="📐 Площадь", callback_data=f"edit_field_area")],
        [InlineKeyboardButton(text="🏢 Этаж", callback_data=f"edit_field_floor")],
        [InlineKeyboardButton(text="📍 Локация", callback_data=f"edit_field_location")],
        [InlineKeyboardButton(text="📝 Описание", callback_data=f"edit_field_description")],
        [InlineKeyboardButton(text="📷 Фото", callback_data=f"edit_field_photos")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_cancel")]
    ])
    
    await callback.message.edit_text(
        "✏️ <b>Что хотите изменить?</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(EditPropertyStates.choosing_field)


@dp.callback_query(F.data == "edit_cancel")
async def edit_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Редактирование отменено.")


@dp.callback_query(F.data == "edit_field_price", EditPropertyStates.choosing_field)
async def edit_price_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💰 Введите новую цену в долларах:")
    await state.set_state(EditPropertyStates.editing_price)


@dp.callback_query(F.data == "edit_field_rooms", EditPropertyStates.choosing_field)
async def edit_rooms_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🚪 Введите количество комнат:")
    await state.set_state(EditPropertyStates.editing_rooms)


@dp.callback_query(F.data == "edit_field_area", EditPropertyStates.choosing_field)
async def edit_area_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📐 Введите площадь в м²:")
    await state.set_state(EditPropertyStates.editing_area)


@dp.callback_query(F.data == "edit_field_floor", EditPropertyStates.choosing_field)
async def edit_floor_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🏢 Введите этаж (например: 5 или 5/9):")
    await state.set_state(EditPropertyStates.editing_floor)


@dp.callback_query(F.data == "edit_field_description", EditPropertyStates.choosing_field)
async def edit_description_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 Введите новое описание:")
    await state.set_state(EditPropertyStates.editing_description)


@dp.callback_query(F.data == "edit_field_location", EditPropertyStates.choosing_field)
async def edit_location_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer(
        "📍 <b>Отправьте новую локацию объекта:</b>\n\n"
        "Нажмите на скрепку 📎 и выберите 'Геопозиция'",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(EditPropertyStates.editing_location)


@dp.message(EditPropertyStates.editing_location, F.location)
async def save_location(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prop_id = data.get("editing_prop_id")
    
    db = SessionLocal()
    prop = db.query(Property).filter(Property.id == prop_id).first()
    if prop:
        prop.latitude = message.location.latitude
        prop.longitude = message.location.longitude
        db.commit()
    db.close()
    
    await state.clear()
    await message.answer(
        f"✅ Локация обновлена!",
        reply_markup=ReplyKeyboardRemove()
    )


@dp.message(EditPropertyStates.editing_location, F.text == "❌ Отмена")
async def cancel_location_edit(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Редактирование отменено.", reply_markup=ReplyKeyboardRemove())


@dp.message(EditPropertyStates.editing_price)
async def save_price(message: types.Message, state: FSMContext):
    price = validate_number(message.text.replace("$", "").replace(" ", ""))
    if price is None or price <= 0:
        await message.answer("❌ Введите корректную цену числом")
        return
    
    data = await state.get_data()
    prop_id = data.get("editing_prop_id")
    
    db = SessionLocal()
    prop = db.query(Property).filter(Property.id == prop_id).first()
    if prop:
        prop.price = int(price)
        db.commit()
    db.close()
    
    await state.clear()
    await message.answer(f"✅ Цена изменена на {int(price):,} сум")


@dp.message(EditPropertyStates.editing_rooms)
async def save_rooms(message: types.Message, state: FSMContext):
    rooms = validate_number(message.text)
    if rooms is None or rooms < 1 or rooms > 20:
        await message.answer("❌ Введите корректное количество комнат (1-20)")
        return
    
    data = await state.get_data()
    prop_id = data.get("editing_prop_id")
    
    db = SessionLocal()
    prop = db.query(Property).filter(Property.id == prop_id).first()
    if prop:
        prop.rooms = int(rooms)
        db.commit()
    db.close()
    
    await state.clear()
    await message.answer(f"✅ Количество комнат изменено на {int(rooms)}")


@dp.message(EditPropertyStates.editing_area)
async def save_area(message: types.Message, state: FSMContext):
    area = validate_number(message.text)
    if area is None or area <= 0:
        await message.answer("❌ Введите корректную площадь")
        return
    
    data = await state.get_data()
    prop_id = data.get("editing_prop_id")
    
    db = SessionLocal()
    prop = db.query(Property).filter(Property.id == prop_id).first()
    if prop:
        prop.area = float(area)
        db.commit()
    db.close()
    
    await state.clear()
    await message.answer(f"✅ Площадь изменена на {area} м²")


@dp.message(EditPropertyStates.editing_floor)
async def save_floor(message: types.Message, state: FSMContext):
    text = message.text.strip()
    
    if "/" in text:
        parts = text.split("/")
        floor = validate_number(parts[0])
        total = validate_number(parts[1])
    else:
        floor = validate_number(text)
        total = None
    
    if floor is None or floor < 1:
        await message.answer("❌ Введите корректный этаж")
        return
    
    data = await state.get_data()
    prop_id = data.get("editing_prop_id")
    
    db = SessionLocal()
    prop = db.query(Property).filter(Property.id == prop_id).first()
    if prop:
        prop.floor = int(floor)
        if total:
            prop.total_floors = int(total)
        db.commit()
    db.close()
    
    await state.clear()
    floor_str = f"{int(floor)}/{int(total)}" if total else str(int(floor))
    await message.answer(f"✅ Этаж изменён на {floor_str}")


@dp.message(EditPropertyStates.editing_description)
async def save_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prop_id = data.get("editing_prop_id")
    
    db = SessionLocal()
    prop = db.query(Property).filter(Property.id == prop_id).first()
    if prop:
        prop.description = message.text
        db.commit()
    db.close()
    
    await state.clear()
    await message.answer("✅ Описание обновлено!")


@dp.callback_query(F.data == "edit_field_photos", EditPropertyStates.choosing_field)
async def edit_photos_start(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(edit_photos=[])
    await callback.message.edit_text(
        "📷 <b>Отправьте новые фото</b>\n\n"
        "Отправляйте фото по одному (до 10 штук).\n"
        "Когда закончите, нажмите 'Готово'.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="edit_photos_done")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_photos_cancel")]
        ])
    )
    await state.set_state(EditPropertyStates.editing_photos)


@dp.message(EditPropertyStates.editing_photos, F.photo)
async def edit_photos_receive(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("edit_photos", [])
    
    if len(photos) >= 10:
        await message.answer("⚠️ Достигнут лимит в 10 фотографий!")
        return
    
    photo_id = message.photo[-1].file_id
    photos.append(photo_id)
    await state.update_data(edit_photos=photos)
    
    await message.answer(
        f"✅ Фото добавлено ({len(photos)}/10)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="edit_photos_done")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_photos_cancel")]
        ])
    )


@dp.callback_query(F.data == "edit_photos_done", EditPropertyStates.editing_photos)
async def edit_photos_save(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    photos = data.get("edit_photos", [])
    prop_id = data.get("editing_prop_id")
    
    if not photos:
        await callback.answer("Добавьте хотя бы одно фото!")
        return
    
    db = SessionLocal()
    prop = db.query(Property).filter(Property.id == prop_id).first()
    if prop:
        prop.photos = ",".join(photos)
        db.commit()
    db.close()
    
    await state.clear()
    await callback.message.edit_text(f"✅ Фото обновлены! Добавлено {len(photos)} фото.")


@dp.callback_query(F.data == "edit_photos_cancel", EditPropertyStates.editing_photos)
async def edit_photos_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Редактирование фото отменено.")


@dp.message(F.text.in_(["❤️ Меня лайкнули", "❤️ Meni layklashdi"]))
async def likes_received(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    from datetime import timedelta
    last_24h = datetime.utcnow() - timedelta(hours=24)
    
    likes = db.query(Like).filter(
        Like.property_owner_id == user.id,
        Like.is_matched == False,
        Like.created_at >= last_24h
    ).order_by(Like.created_at.desc()).all()
    
    if not likes:
        await message.answer("Пока нет новых лайков за последние 24 часа. Добавьте больше объектов!")
        db.close()
        return
    
    text = f"❤️ Лайки за последние 24 часа ({len(likes)}):\n\n"
    
    keyboard_buttons = []
    for like in likes[:10]:
        buyer = db.query(User).filter(User.id == like.user_id).first()
        prop = db.query(Property).filter(Property.id == like.property_id).first()
        
        if buyer and prop:
            name = buyer.first_name or "Покупатель"
            username = f"@{buyer.username}" if buyer.username else "нет"
            phone = buyer.phone or "не указан"
            budget = f"до ${buyer.search_budget_max:,}" if buyer.search_budget_max else "не указан"
            prop_id = prop.unique_id or f"#{prop.id}"
            
            time_ago = datetime.utcnow() - like.created_at
            hours_ago = int(time_ago.total_seconds() // 3600)
            mins_ago = int((time_ago.total_seconds() % 3600) // 60)
            time_str = f"{hours_ago}ч {mins_ago}м назад" if hours_ago > 0 else f"{mins_ago}м назад"
            
            deal_type_emoji = "🔑" if prop.property_type == PropertyType.RENT else "🏠"
            deal_type_label = "Аренда" if prop.property_type == PropertyType.RENT else "Продажа"
            
            bio_line = f"📝 {buyer.buyer_bio}\n" if buyer.buyer_bio else ""
            
            text += (
                f"{deal_type_emoji} Объект: {prop_id} ({deal_type_label})\n"
                f"👤 {name} | {username}\n"
                f"📞 {phone}\n"
                f"💰 Бюджет: {budget}\n"
                f"{bio_line}"
                f"⏰ {time_str}\n"
                f"{'─' * 20}\n\n"
            )
            keyboard_buttons.append([
                InlineKeyboardButton(text=f"🤝 Открыть контакт {name}", callback_data=f"match_{like.id}")
            ])
    
    db.close()
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons))


@dp.callback_query(F.data.startswith("match_"))
async def create_match(callback: types.CallbackQuery):
    like_id = int(callback.data.replace("match_", ""))
    
    db = SessionLocal()
    like = db.query(Like).filter(Like.id == like_id).first()
    
    if not like:
        await callback.answer("Лайк не найден")
        db.close()
        return
    
    buyer = db.query(User).filter(User.id == like.user_id).first()
    seller = db.query(User).filter(User.id == like.property_owner_id).first()
    prop = db.query(Property).filter(Property.id == like.property_id).first()
    
    match = Match(
        buyer_id=like.user_id,
        seller_id=like.property_owner_id,
        property_id=like.property_id
    )
    db.add(match)
    like.is_matched = True
    db.commit()
    
    seller_phone = seller.phone or "Не указан"
    
    try:
        await bot.send_message(
            buyer.telegram_id,
            f"🎉 Отличные новости!\n\n"
            f"Владелец квартиры подтвердил интерес!\n\n"
            f"📍 {prop.district}\n"
            f"💰 {prop.price:,} сум\n\n"
            f"📞 Контакт: {seller_phone}\n"
            f"👤 Менеджер: {seller.manager_name or seller.first_name}\n\n"
            f"Свяжитесь для просмотра!"
        )
    except:
        pass
    
    db.close()
    
    await callback.message.edit_text(
        f"✅ Мэтч создан!\n\n"
        f"👤 Покупатель: {buyer.first_name or 'Покупатель'}\n"
        f"📞 Контакт доступен в разделе 'Сделки'"
    )


@dp.message(F.text.in_(["💬 Сделки", "💬 Bitimlar"]))
async def deals(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if user.role == UserRole.SELLER:
        matches = db.query(Match).filter(Match.seller_id == user.id).order_by(Match.created_at.desc()).all()
    else:
        matches = db.query(Match).filter(Match.buyer_id == user.id).order_by(Match.created_at.desc()).all()
    
    if not matches:
        db.close()
        await message.answer("Пока нет сделок. Они появятся после мэтчей!")
        return
    
    await message.answer(f"💬 Ваши сделки ({len(matches)}):\n\nНиже показаны анкеты ваших контактов:")
    
    for match in matches[:10]:
        buyer = db.query(User).filter(User.id == match.buyer_id).first()
        seller = db.query(User).filter(User.id == match.seller_id).first()
        prop = db.query(Property).filter(Property.id == match.property_id).first()
        
        if user.role == UserRole.SELLER:
            contact = buyer
            role_text = "🏠 Покупатель"
        else:
            contact = seller
            role_text = "💼 Продавец"
        
        contact_name = contact.first_name or contact.username or "Контакт"
        contact_username = f"@{contact.username}" if contact.username else "Не указан"
        contact_phone = contact.phone or "Не указан"
        
        prop_info = ""
        prop_button = None
        if prop:
            prop_id = prop.unique_id or f"#{prop.id}"
            prop_info = f"\n🆔 ID объекта: {prop_id}"
            prop_button = InlineKeyboardButton(text=f"📋 Открыть объект {prop_id}", callback_data=f"view_deal_prop_{prop.id}")
        
        buyer_info = ""
        if contact.role == UserRole.BUYER:
            search_rooms = contact.search_rooms or "Не указано"
            search_district = contact.search_district or "Любой"
            search_budget = f"${contact.search_budget_max:,}" if contact.search_budget_max else "Не указан"
            payment_types = {
                "cash": "💵 Наличные",
                "mortgage": "🏦 Ипотека",
                "installment": "📄 Рассрочка"
            }
            payment = payment_types.get(contact.search_payment_type, "Не указан")
            buyer_info = (
                f"\n\n📊 Параметры поиска клиента:\n"
                f"🚪 Комнат: {search_rooms}\n"
                f"📍 Район: {search_district}\n"
                f"💰 Бюджет до: {search_budget}\n"
                f"💳 Оплата: {payment}"
            )
        
        seller_info = ""
        if contact.role == UserRole.SELLER:
            seller_type_names = {
                SellerType.OWNER: "🏠 Собственник",
                SellerType.REALTOR: "🔑 Риелтор",
                SellerType.DEVELOPER: "🏗 Застройщик"
            }
            seller_type_text = seller_type_names.get(contact.seller_type, "Продавец")
            company = contact.company_name or "Не указана"
            manager = contact.manager_name or contact.first_name or "Не указан"
            seller_info = (
                f"\n\n📊 Информация о продавце:\n"
                f"💼 Тип: {seller_type_text}\n"
                f"🏢 Компания: {company}\n"
                f"👤 Менеджер: {manager}"
            )
        
        card_text = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{role_text}\n\n"
            f"👤 Имя: {contact_name}\n"
            f"📱 Телеграм: {contact_username}\n"
            f"📞 Телефон: {contact_phone}\n"
            f"📅 Дата мэтча: {match.created_at.strftime('%d.%m.%Y %H:%M')}"
            f"{prop_info}"
            f"{buyer_info}"
            f"{seller_info}"
        )
        
        if match.note:
            card_text += f"\n\n📝 Заметка: {match.note}"
        
        buttons = []
        if prop_button:
            buttons.append([prop_button])
        if contact.username:
            buttons.append([InlineKeyboardButton(text="💬 Написать в Telegram", url=f"https://t.me/{contact.username}")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        await message.answer(card_text, reply_markup=keyboard)
    
    if len(matches) > 10:
        await message.answer(f"... и ещё {len(matches) - 10} контактов")
    
    db.close()


@dp.callback_query(F.data.startswith("view_deal_prop_"))
async def view_deal_property(callback: types.CallbackQuery):
    prop_id = int(callback.data.replace("view_deal_prop_", ""))
    
    db = SessionLocal()
    prop = db.query(Property).filter(Property.id == prop_id).first()
    
    if not prop:
        await callback.answer("Объект не найден")
        db.close()
        return
    
    unique_id = prop.unique_id or f"#{prop.id}"
    type_emoji = "🏷" if prop.property_type == PropertyType.SALE else "🔑"
    type_name = "Продажа" if prop.property_type == PropertyType.SALE else "Аренда"
    furniture = "Да" if prop.has_furniture else "Нет"
    
    text = (
        f"🆔 {unique_id}\n\n"
        f"{type_emoji} {type_name}\n\n"
        f"📍 {prop.district or 'Район не указан'}\n"
        f"🚪 {prop.rooms} комн. | 📐 {prop.area} м²\n"
        f"🏢 Этаж {prop.floor}/{prop.total_floors}\n"
        f"🏠 {prop.building_type or ''}\n"
        f"🔨 {prop.renovation or ''}\n"
        f"🛋 Мебель: {furniture}\n\n"
        f"💰 {prop.price:,} сум\n"
    )
    
    if prop.description:
        text += f"\n📝 {prop.description}"
    
    photos = [p for p in (prop.photos.split(",") if prop.photos else []) if p]
    db.close()
    
    await callback.answer()
    
    if photos:
        from aiogram.types import InputMediaPhoto
        if len(photos) > 1:
            media_group = []
            for i, photo_id in enumerate(photos[:10]):
                if i == 0:
                    media_group.append(InputMediaPhoto(media=photo_id, caption=text))
                else:
                    media_group.append(InputMediaPhoto(media=photo_id))
            await callback.message.answer_media_group(media_group)
        else:
            await callback.message.answer_photo(photo=photos[0], caption=text)
    else:
        await callback.message.answer(text)


class FindBuyerStates(StatesGroup):
    deal_type = State()
    prop_type = State()
    budget = State()


def get_seller_menu(lang='ru', is_developer=False):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('add_property', lang))],
            [KeyboardButton(text=get_text('find_buyer', lang))],
            [KeyboardButton(text=get_text('profile', lang))]
        ],
        resize_keyboard=True
    )


def get_seller_profile_menu(lang='ru'):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('who_liked_me', lang)), KeyboardButton(text=get_text('deals', lang))],
            [KeyboardButton(text=get_text('my_properties', lang)), KeyboardButton(text=get_text('my_profile', lang))],
            [KeyboardButton(text=get_text('tariffs', lang)), KeyboardButton(text=get_text('ads', lang))],
            [KeyboardButton(text=get_text('back_button', lang))]
        ],
        resize_keyboard=True
    )


@dp.message(F.text.in_(["🎯 Найти покупателя", "🎯 Xaridor topish"]))
async def find_buyers(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    db.close()
    
    if not user or user.role != UserRole.SELLER:
        if user and user.role == UserRole.BUYER:
            lang = get_user_lang(user)
            await message.answer(get_text('returned_to_menu', lang), reply_markup=get_buyer_menu(lang))
        else:
            await message.answer("Нажмите /start чтобы начать.")
        return
    
    limits = get_tariff_limits(user.tariff, user.is_admin)
    if limits["daily_offers"] == 0:
        await message.answer(
            "⚠️ В бесплатном тарифе нельзя писать первым в базе спроса.\n\n"
            "Перейдите на тариф 'Агентство Start' или выше!"
        )
        return
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Ищут покупку")],
            [KeyboardButton(text="🔑 Ищут аренду")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🎯 Найти покупателя\n\n🏷 Каких клиентов ищем?", reply_markup=keyboard)
    await state.set_state(FindBuyerStates.deal_type)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), FindBuyerStates.deal_type)
async def find_buyer_back_from_deal(message: types.Message, state: FSMContext):
    await state.clear()
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    is_developer = user.seller_type == SellerType.DEVELOPER if user else False
    db.close()
    await message.answer(get_text('returned_to_menu', lang), reply_markup=get_seller_menu(lang, is_developer=is_developer))


@dp.message(FindBuyerStates.deal_type)
async def find_buyer_deal_type(message: types.Message, state: FSMContext):
    deal_types = {
        "🏠 Ищут покупку": "sale",
        "🔑 Ищут аренду": "rent"
    }
    deal_type = deal_types.get(message.text)
    if not deal_type:
        return
    
    await state.update_data(find_deal_type=deal_type)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏢 Квартиры")],
            [KeyboardButton(text="🏡 Дом / Участок")],
            [KeyboardButton(text="🏪 Коммерческая")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🏢 В каком разделе ищем?", reply_markup=keyboard)
    await state.set_state(FindBuyerStates.prop_type)


@dp.message(F.text == "⬅️ Назад", FindBuyerStates.prop_type)
async def find_buyer_back_to_deal(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Ищут покупку")],
            [KeyboardButton(text="🔑 Ищут аренду")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🏷 Каких клиентов ищем?", reply_markup=keyboard)
    await state.set_state(FindBuyerStates.deal_type)


@dp.message(FindBuyerStates.prop_type)
async def find_buyer_prop_type(message: types.Message, state: FSMContext):
    prop_types = {
        "🏢 Квартиры": "apartment",
        "🏡 Дом / Участок": "house",
        "🏪 Коммерческая": "commercial"
    }
    prop_type = prop_types.get(message.text)
    if not prop_type:
        return
    
    await state.update_data(find_prop_type=prop_type)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Любой бюджет")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("💰 Введите максимальный бюджет клиента в долларах:\n\n(например: 50000)", reply_markup=keyboard)
    await state.set_state(FindBuyerStates.budget)


@dp.message(F.text == "⬅️ Назад", FindBuyerStates.budget)
async def find_buyer_back_to_proptype(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏢 Квартиры")],
            [KeyboardButton(text="🏡 Дом / Участок")],
            [KeyboardButton(text="🏪 Коммерческая")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🏢 В каком разделе ищем?", reply_markup=keyboard)
    await state.set_state(FindBuyerStates.prop_type)


@dp.message(FindBuyerStates.budget)
async def find_buyer_show_results(message: types.Message, state: FSMContext):
    if message.text == "Любой бюджет":
        max_budget = 999999999
    else:
        max_budget = validate_number(message.text)
        if max_budget is None or max_budget <= 0:
            await message.answer("❌ Введите корректную сумму числом или нажмите 'Любой бюджет'")
            return
    
    data = await state.get_data()
    prop_type = data.get("find_prop_type", "apartment")
    deal_type = data.get("find_deal_type", "sale")
    
    await state.clear()
    
    db = SessionLocal()
    
    query = db.query(User).filter(
        User.role == UserRole.BUYER,
        User.search_budget_max > 0
    )
    
    if deal_type == "sale":
        query = query.filter(User.search_deal_type == "sale")
    else:
        query = query.filter(User.search_deal_type == "rent")
    
    if max_budget < 999999999:
        query = query.filter(User.search_budget_max <= max_budget)
    
    buyers = query.order_by(User.created_at.desc()).limit(10).all()
    db.close()
    
    if not buyers:
        db2 = SessionLocal()
        seller = db2.query(User).filter(User.telegram_id == message.from_user.id).first()
        is_dev = seller.seller_type == SellerType.DEVELOPER if seller else False
        l = get_user_lang(seller)
        db2.close()
        await message.answer("Пока нет покупателей с такими критериями.", reply_markup=get_seller_menu(l, is_developer=is_dev))
        return
    
    deal_names = {"sale": "Покупка", "rent": "Аренда"}
    prop_names = {"apartment": "Квартиры", "house": "Дом/Участок", "commercial": "Коммерческая"}
    text = f"🎯 Клиенты ({deal_names.get(deal_type)} — {prop_names.get(prop_type, prop_type)}, {message.text}):\n\n"
    
    keyboard_buttons = []
    for buyer in buyers:
        rooms = buyer.search_rooms or "Любые"
        district = buyer.search_district or "Любой район"
        budget = buyer.search_budget_max or 0
        bio_line = f"   📝 {buyer.buyer_bio}\n" if buyer.buyer_bio else ""
        
        text += (
            f"👤 {buyer.first_name or 'Клиент'}\n"
            f"   🚪 {rooms} комн. | 📍 {district}\n"
            f"   💰 до ${budget:,}\n"
            f"{bio_line}\n"
        )
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"📤 Предложить {buyer.first_name or 'клиенту'}", callback_data=f"offer_{buyer.id}")
        ])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons))
    
    db3 = SessionLocal()
    seller = db3.query(User).filter(User.telegram_id == message.from_user.id).first()
    is_dev = seller.seller_type == SellerType.DEVELOPER if seller else False
    l = get_user_lang(seller)
    db3.close()
    await message.answer("Выберите клиента или вернитесь в меню", reply_markup=get_seller_menu(l, is_developer=is_dev))


@dp.callback_query(F.data.startswith("offer_"))
async def send_offer(callback: types.CallbackQuery):
    buyer_id = int(callback.data.replace("offer_", ""))
    
    db = SessionLocal()
    seller = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    
    limits = get_tariff_limits(seller.tariff, seller.is_admin)
    
    if seller.daily_offers_count >= limits["daily_offers"]:
        await callback.answer("Вы достигли лимита предложений на сегодня!")
        db.close()
        return
    
    properties = db.query(Property).filter(
        Property.owner_id == seller.id,
        Property.status == PropertyStatus.ACTIVE
    ).all()
    db.close()
    
    if not properties:
        await callback.answer("У вас нет активных объектов!")
        return
    
    keyboard_buttons = []
    for prop in properties[:5]:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{prop.district} - {prop.price:,} сум",
                callback_data=f"sendprop_{buyer_id}_{prop.id}"
            )
        ])
    
    await callback.message.answer(
        "Выберите объект для предложения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    )


@dp.callback_query(F.data.startswith("sendprop_"))
async def send_property_offer(callback: types.CallbackQuery):
    parts = callback.data.replace("sendprop_", "").split("_")
    buyer_id = int(parts[0])
    property_id = int(parts[1])
    
    db = SessionLocal()
    seller = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    buyer = db.query(User).filter(User.id == buyer_id).first()
    prop = db.query(Property).filter(Property.id == property_id).first()
    
    offer = Offer(
        seller_id=seller.id,
        buyer_id=buyer_id,
        property_id=property_id
    )
    db.add(offer)
    seller.daily_offers_count += 1
    db.commit()
    
    try:
        await bot.send_message(
            buyer.telegram_id,
            f"📬 Новое предложение!\n\n"
            f"📍 {prop.district}\n"
            f"🚪 {prop.rooms} комн. | 📐 {prop.area} м²\n"
            f"💰 {prop.price:,} сум\n\n"
            f"Интересно?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Интересно", callback_data=f"accept_offer_{offer.id}"),
                    InlineKeyboardButton(text="❌ Нет", callback_data=f"reject_offer_{offer.id}")
                ]
            ])
        )
    except:
        pass
    
    db.close()
    
    await callback.message.edit_text("✅ Предложение отправлено!")


@dp.callback_query(F.data.startswith("accept_offer_"))
async def accept_offer(callback: types.CallbackQuery):
    offer_id = int(callback.data.replace("accept_offer_", ""))
    
    db = SessionLocal()
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    
    if not offer:
        await callback.answer("Предложение не найдено")
        db.close()
        return
    
    offer.is_accepted = True
    
    match = Match(
        buyer_id=offer.buyer_id,
        seller_id=offer.seller_id,
        property_id=offer.property_id
    )
    db.add(match)
    
    seller = db.query(User).filter(User.id == offer.seller_id).first()
    buyer = db.query(User).filter(User.id == offer.buyer_id).first()
    prop = db.query(Property).filter(Property.id == offer.property_id).first()
    
    db.commit()
    
    try:
        await bot.send_message(
            seller.telegram_id,
            f"🎉 Покупатель заинтересован!\n\n"
            f"👤 {buyer.first_name or 'Покупатель'} принял ваше предложение!\n"
            f"📍 {prop.district}\n\n"
            f"Контакт добавлен в раздел 'Сделки'"
        )
    except:
        pass
    
    seller_phone = seller.phone or "Не указан"
    
    db.close()
    
    await callback.message.edit_text(
        f"✅ Отлично!\n\n"
        f"Контакт продавца:\n"
        f"📞 {seller_phone}\n"
        f"👤 {seller.manager_name or seller.first_name}\n\n"
        f"Свяжитесь для просмотра!"
    )


@dp.callback_query(F.data.startswith("reject_offer_"))
async def reject_offer(callback: types.CallbackQuery):
    offer_id = int(callback.data.replace("reject_offer_", ""))
    
    db = SessionLocal()
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if offer:
        offer.is_accepted = False
        db.commit()
    db.close()
    
    await callback.message.edit_text("Спасибо за ответ! Мы найдем для вас другие варианты.")


@dp.message(lambda m: m.text in [get_text('profile', 'ru'), get_text('profile', 'uz')])
async def profile(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    db.close()
    
    if user.role == UserRole.SELLER:
        keyboard = get_seller_profile_menu(lang)
        await message.answer(get_text('profile', lang), reply_markup=keyboard)
    else:
        keyboard = get_buyer_profile_menu(lang)
        await message.answer(get_text('profile', lang), reply_markup=keyboard)


@dp.callback_query(F.data == "change_language")
async def change_language_callback(callback: types.CallbackQuery, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇷🇺 Русский")],
            [KeyboardButton(text="🇺🇿 O'zbekcha")]
        ],
        resize_keyboard=True
    )
    await callback.answer()
    await callback.message.answer(get_text('choose_language', 'ru'), reply_markup=keyboard)
    await state.set_state(RegistrationStates.choosing_language)


@dp.message(lambda m: m.text in [get_text('my_profile', 'ru'), get_text('my_profile', 'uz')])
async def my_profile(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    db.close()
    
    if user.role == UserRole.SELLER:
        await show_seller_profile_info(message, user)
    else:
        await show_buyer_profile(message, user)


@dp.message(F.text.in_(["🔙 Главное меню", "🔙 Asosiy menyu"]))
async def back_to_main_menu(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    is_developer = user.seller_type == SellerType.DEVELOPER if user else False
    db.close()
    
    if user.role == UserRole.SELLER:
        keyboard = get_seller_menu(lang, is_developer=is_developer)
    else:
        keyboard = get_buyer_menu(lang)
    
    await message.answer(get_text('returned_to_menu', lang), reply_markup=keyboard)


async def show_seller_profile_info(message, user):
    webapp_url = os.environ.get('REPLIT_DEV_DOMAIN', '')
    if not webapp_url:
        webapp_url = os.environ.get('REPLIT_DOMAINS', '').split(',')[0] if os.environ.get('REPLIT_DOMAINS') else ''
    
    db = SessionLocal()
    user = db.query(User).filter(User.id == user.id).first()
    active_properties_count = db.query(Property).filter(Property.owner_id == user.id).count()
    db.close()
    
    lang = get_user_lang(user)
    
    tariff_limits = get_tariff_limits(user.tariff, user.is_admin)
    base_properties = tariff_limits.get("properties", 2)
    bonus = user.bonus_properties or 0
    max_properties = base_properties + bonus
    remaining_properties = max(0, max_properties - active_properties_count)
    
    if user.tariff == TariffType.FREE or user.tariff_expires is None:
        days_left_text = "♾ Cheksiz" if lang == 'uz' else "♾ Безлимит"
    else:
        now = get_tashkent_now()
        if user.tariff_expires > now:
            days_left = (user.tariff_expires - now).days
            days_left_text = f"📅 {days_left} kun" if lang == 'uz' else f"📅 {days_left} дн."
        else:
            days_left_text = "⏰ Tugadi" if lang == 'uz' else "⏰ Истёк"
    
    if lang == 'uz':
        type_names = {
            SellerType.OWNER: "Mulkdor",
            SellerType.REALTOR: "Rieltor",
            SellerType.DEVELOPER: "Quruvchi"
        }
        tariff_names = {
            TariffType.FREE: "🆓 Bepul",
            TariffType.PRO: "⭐ Pro",
            TariffType.PREMIUM: "👑 Premium",
            TariffType.AGENCY_START: "⭐ Pro",
            TariffType.DEVELOPER_PRO: "👑 Premium"
        }
        not_specified = "Ko'rsatilmagan"
        text = (
            f"👤 Sizning profilingiz\n\n"
            f"🆔 Sizning ID: {user.telegram_id}\n"
            f"📋 Tur: {type_names.get(user.seller_type, not_specified)}\n"
            f"🏢 Kompaniya: {user.company_name or not_specified}\n"
            f"👤 Menejer: {user.manager_name or not_specified}\n"
            f"📞 Telefon: {user.phone or not_specified}\n"
            f"💳 Tarif: {tariff_names.get(user.tariff, 'Bepul')}\n"
            f"🏠 E'lonlar: {active_properties_count}/{max_properties} (qoldi: {remaining_properties})\n"
            f"⏳ Tarif tugashigacha: {days_left_text}\n"
        )
    else:
        type_names = {
            SellerType.OWNER: "Собственник",
            SellerType.REALTOR: "Риелтор",
            SellerType.DEVELOPER: "Застройщик"
        }
        tariff_names = {
            TariffType.FREE: "🆓 Бесплатный",
            TariffType.PRO: "⭐ Про",
            TariffType.PREMIUM: "👑 Премиум",
            TariffType.AGENCY_START: "⭐ Про",
            TariffType.DEVELOPER_PRO: "👑 Премиум"
        }
        text = (
            f"👤 Ваш профиль\n\n"
            f"🆔 Ваш ID: {user.telegram_id}\n"
            f"📋 Тип: {type_names.get(user.seller_type, 'Не указан')}\n"
            f"🏢 Компания: {user.company_name or 'Не указана'}\n"
            f"👤 Менеджер: {user.manager_name or 'Не указан'}\n"
            f"📞 Телефон: {user.phone or 'Не указан'}\n"
            f"💳 Тариф: {tariff_names.get(user.tariff, 'Бесплатный')}\n"
            f"🏠 Объявления: {active_properties_count}/{max_properties} (осталось: {remaining_properties})\n"
            f"⏳ До конца тарифа: {days_left_text}\n"
        )
    
    switch_text = "🏠 Xaridor rejimiga o'tish" if lang == 'uz' else "🏠 Перейти в режим покупателя"
    details_text = "📊 Batafsil" if lang == 'uz' else "📊 Подробно"
    admin_text = "🔐 Admin panel" if lang == 'uz' else "🔐 Админ-панель"
    
    buttons = [
        [InlineKeyboardButton(text=switch_text, callback_data="switch_to_buyer")],
        [InlineKeyboardButton(text=get_text('change_language', lang), callback_data="change_language")]
    ]
    
    if webapp_url:
        buttons.append([InlineKeyboardButton(
            text=details_text,
            web_app=types.WebAppInfo(url=f"https://{webapp_url}/webapp/user_stats?tg_id={user.telegram_id}")
        )])
    
    if user.is_admin and webapp_url:
        buttons.append([InlineKeyboardButton(
            text=admin_text,
            web_app=types.WebAppInfo(url=f"https://{webapp_url}/webapp/admin/home?tg_id={user.telegram_id}")
        )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=keyboard)


async def show_buyer_profile(message, user):
    webapp_url = os.environ.get('REPLIT_DEV_DOMAIN', '')
    if not webapp_url:
        webapp_url = os.environ.get('REPLIT_DOMAINS', '').split(',')[0] if os.environ.get('REPLIT_DOMAINS') else ''
    
    lang = get_user_lang(user)
    
    payment_names_ru = {"cash": "Наличные", "mortgage": "Ипотека", "installment": "Рассрочка"}
    payment_names_uz = {"cash": "Naqd pul", "mortgage": "Ipoteka", "installment": "Bo'lib to'lash"}
    payment_names = payment_names_uz if lang == 'uz' else payment_names_ru
    
    not_specified = "Ko'rsatilmagan" if lang == 'uz' else "Не указано"
    any_text = "Istalgan" if lang == 'uz' else "Любой"
    rooms_text = "xona" if lang == 'uz' else "комн."
    
    budget = f"${user.search_budget_max:,}" if user.search_budget_max else not_specified
    
    district_display = user.search_district or any_text
    if lang == 'uz' and user.search_district:
        district_display = get_district_name(user.search_district, lang)
    
    if lang == 'uz':
        bio_line = f"📝 Tavsif: {user.buyer_bio}\n" if user.buyer_bio else ""
        text = (
            f"👤 Sizning profilingiz\n\n"
            f"🆔 Sizning ID: {user.telegram_id}\n"
            f"🚪 Qidiraman: {user.search_rooms or 'Istalgan'} {rooms_text}\n"
            f"📍 Tuman: {district_display}\n"
            f"💰 Byudjet: {budget} gacha\n"
            f"💳 To'lov: {payment_names.get(user.search_payment_type, not_specified)}\n"
            f"{bio_line}"
        )
    else:
        bio_line = f"📝 Описание: {user.buyer_bio}\n" if user.buyer_bio else ""
        text = (
            f"👤 Ваш профиль\n\n"
            f"🆔 Ваш ID: {user.telegram_id}\n"
            f"🚪 Ищу: {user.search_rooms or 'Любые'} {rooms_text}\n"
            f"📍 Район: {district_display}\n"
            f"💰 Бюджет: до {budget}\n"
            f"💳 Оплата: {payment_names.get(user.search_payment_type, not_specified)}\n"
            f"{bio_line}"
        )
    
    switch_text = "💼 Sotuvchi rejimiga o'tish" if lang == 'uz' else "💼 Перейти в режим продавца"
    details_text = "📊 Batafsil" if lang == 'uz' else "📊 Подробно"
    admin_text = "🔐 Admin panel" if lang == 'uz' else "🔐 Админ-панель"
    
    buttons = [
        [InlineKeyboardButton(text=switch_text, callback_data="switch_to_seller")],
        [InlineKeyboardButton(text=get_text('change_language', lang), callback_data="change_language")]
    ]
    
    if webapp_url:
        buttons.append([InlineKeyboardButton(
            text=details_text,
            web_app=types.WebAppInfo(url=f"https://{webapp_url}/webapp/user_stats?tg_id={user.telegram_id}")
        )])
    
    if user.is_admin and webapp_url:
        buttons.append([InlineKeyboardButton(
            text=admin_text,
            web_app=types.WebAppInfo(url=f"https://{webapp_url}/webapp/admin/home?tg_id={user.telegram_id}")
        )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=keyboard)


@dp.callback_query(F.data == "switch_to_buyer")
async def switch_to_buyer(callback: types.CallbackQuery, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    lang = get_user_lang(user)
    
    if user:
        user.role = UserRole.BUYER
        db.commit()
    db.close()
    
    await callback.answer(get_text('switched_to_buyer_callback', lang))
    await callback.message.delete()
    
    keyboard = get_buyer_menu(lang)
    
    await callback.message.answer(
        get_text('switched_to_buyer', lang),
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "switch_to_seller")
async def switch_to_seller(callback: types.CallbackQuery, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    lang = get_user_lang(user)
    
    if user:
        user.role = UserRole.SELLER
        db.commit()
    
    is_developer = user.seller_type == SellerType.DEVELOPER if user else False
    buyers_count = db.query(User).filter(User.role == UserRole.BUYER).count()
    db.close()
    
    await callback.answer(get_text('switched_to_seller_callback', lang))
    await callback.message.delete()
    
    keyboard = get_seller_menu(lang, is_developer=is_developer)
    
    await callback.message.answer(
        get_text('switched_to_seller', lang, count=buyers_count),
        reply_markup=keyboard
    )


@dp.message(F.text.in_(["💼 Войти в режим продавца", "💼 Sotuvchi rejimiga o'tish"]))
async def buyer_switch_to_seller(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    
    if user:
        user.role = UserRole.SELLER
        db.commit()
    
    is_developer = user.seller_type == SellerType.DEVELOPER if user else False
    buyers_count = db.query(User).filter(User.role == UserRole.BUYER).count()
    db.close()
    
    keyboard = get_seller_menu(lang, is_developer=is_developer)
    
    await message.answer(
        get_text('switched_to_seller', lang, count=buyers_count),
        reply_markup=keyboard
    )


@dp.message(F.text.in_(["❤️ Лайки", "❤️ Layklar"]))
async def buyer_likes(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    three_days_ago = datetime.utcnow() - timedelta(days=3)
    likes = db.query(Like).filter(
        Like.user_id == user.id,
        Like.created_at >= three_days_ago
    ).order_by(Like.created_at.desc()).all()
    
    if not likes:
        db.close()
        no_likes_text = "Siz hali hech qanday kvartiraga layk qo'ymadingiz." if lang == 'uz' else "Вы еще не лайкнули ни одной квартиры."
        await message.answer(no_likes_text, reply_markup=get_buyer_profile_menu(lang))
        return
    
    header_text = f"❤️ <b>Sizning layklaringiz ({len(likes)})</b>" if lang == 'uz' else f"❤️ <b>Ваши лайки ({len(likes)})</b>"
    await message.answer(header_text, reply_markup=get_buyer_profile_menu(lang), parse_mode="HTML")
    
    if lang == 'uz':
        match_text = "Mos keldi!"
        waiting_text = "Kutilmoqda"
        sale_text = "Sotish"
        rent_text = "Ijara"
        rooms_text = "xona"
        floor_text = "qavat"
        not_specified = "Ko'rsatilmagan"
        with_furniture = "mebellar bilan"
        contact_label = "Kontakt"
    else:
        match_text = "Мэтч!"
        waiting_text = "Ожидание"
        sale_text = "Продажа"
        rent_text = "Аренда"
        rooms_text = "комн."
        floor_text = "этаж"
        not_specified = "Не указан"
        with_furniture = "с мебелью"
        contact_label = "Контакт"
    
    for like in likes[:10]:
        prop = db.query(Property).filter(Property.id == like.property_id).first()
        
        if prop:
            status_emoji = "🟢" if like.is_matched else "⏳"
            status_text = match_text if like.is_matched else waiting_text
            type_name = sale_text if prop.property_type == PropertyType.SALE else rent_text
            
            contact_phone = prop.phone
            if not contact_phone:
                owner = db.query(User).filter(User.id == prop.owner_id).first()
                contact_phone = owner.phone if owner else not_specified
            
            text = f"{status_emoji} <b>{status_text}</b>  •  {type_name}\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n\n"
            text += f"💰 <b>{prop.price:,} сум</b>\n\n"
            
            if prop.district:
                district_display = get_district_name(prop.district, lang)
                text += f"📍 {district_display}\n"
            if prop.rooms:
                text += f"🚪 {prop.rooms} {rooms_text}\n"
            if prop.area:
                text += f"📐 {prop.area} м²\n"
            if prop.floor and prop.total_floors:
                text += f"🏢 {prop.floor}/{prop.total_floors} {floor_text}\n"
            
            extras = []
            if prop.building_type:
                extras.append(prop.building_type)
            if prop.renovation:
                extras.append(prop.renovation)
            if prop.has_furniture:
                extras.append(with_furniture)
            if extras:
                text += f"\n🏠 {' • '.join(extras)}\n"
            
            text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
            text += f"📞 <b><u>{contact_label}: {contact_phone}</u></b>\n"
            
            photos = [p for p in (prop.photos.split(",") if prop.photos else []) if p]
            
            if photos:
                try:
                    await message.answer_photo(photo=photos[0], caption=text, parse_mode="HTML")
                except:
                    await message.answer(text, parse_mode="HTML")
            else:
                await message.answer(text, parse_mode="HTML")
    
    db.close()


@dp.message(F.text.in_(["💬 Переписка", "💬 Xabarlar"]))
async def buyer_messages(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    
    matches = db.query(Like).filter(
        Like.user_id == user.id,
        Like.is_matched == True
    ).order_by(Like.created_at.desc()).all()
    db.close()
    
    if not matches:
        if lang == 'uz':
            no_contacts_text = "💬 Sizda hali kontaktlar yo'q.\n\nKvartiralarni yoqtiring va sotuvchi kontaktni ochishini kuting!"
        else:
            no_contacts_text = "💬 У вас пока нет контактов.\n\nЛайкайте квартиры и ждите, когда продавец откроет контакт!"
        await message.answer(no_contacts_text, reply_markup=get_buyer_profile_menu(lang))
        return
    
    if lang == 'uz':
        text = f"💬 Sizning kontaktlaringiz ({len(matches)}):\n\n"
        rooms_text = "xona"
        not_specified = "Ko'rsatilmagan"
        obj_text = "Obyekt"
    else:
        text = f"💬 Ваши контакты ({len(matches)}):\n\n"
        rooms_text = "комн."
        not_specified = "Не указан"
        obj_text = "Объект"
    
    for match in matches[:20]:
        db = SessionLocal()
        prop = db.query(Property).filter(Property.id == match.property_id).first()
        if prop:
            seller = db.query(User).filter(User.id == prop.owner_id).first()
            district_display = get_district_name(prop.district, lang) if prop.district else obj_text
            text += (
                f"📍 {district_display}\n"
                f"   {prop.rooms} {rooms_text} | {prop.price:,} сум\n"
                f"   📞 {seller.phone if seller else not_specified}\n\n"
            )
        db.close()
    
    await message.answer(text, reply_markup=get_buyer_profile_menu(lang))


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga", "🔙 Назад", "🔙 Orqaga"]))
async def buyer_profile_back(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = user.language if user and user.language else 'ru'
    db.close()
    
    menu_text = "🏠 Bosh menyu" if lang == 'uz' else "🏠 Главное меню"
    
    if user and user.role == UserRole.BUYER:
        keyboard = get_buyer_menu(lang)
        await message.answer(menu_text, reply_markup=keyboard)
    else:
        keyboard = get_seller_menu(lang)
        await message.answer(menu_text, reply_markup=keyboard)


@dp.message(F.text.in_(["💳 Тарифы", "💳 Tariflar"]))
async def tariffs(message: types.Message):
    webapp_url = WEBAPP_BASE_URL or os.environ.get('REPLIT_DEV_DOMAIN', '')
    if webapp_url and not webapp_url.startswith('https://'):
        webapp_url = f"https://{webapp_url}"
    
    if webapp_url:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📋 Посмотреть тарифы",
                web_app=WebAppInfo(url=f"{webapp_url}/webapp/tariffs")
            )],
            [InlineKeyboardButton(
                text="💬 Связаться с администратором",
                url="https://t.me/InvictumMurad"
            )]
        ])
        
        await message.answer(
            "💳 Тарифные планы\n\n"
            "Нажмите кнопку ниже, чтобы посмотреть подробное описание тарифов:",
            reply_markup=keyboard
        )
    else:
        text = (
            "💳 Тарифные планы\n\n"
            "🔥 АКЦИЯ! Специальные цены на время запуска\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🆓 Бесплатный\n"
            "• 2 объявления\n"
            "• 1 лайк в день\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⭐ Про (300 000 сум/мес)\n"
            "• 50 объявлений в месяц\n"
            "• 10 лайков в день\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "👑 Премиум (500 000 сум/мес)\n"
            "• 100 объявлений в месяц\n"
            "• 30 лайков в день\n"
            "• Приоритетный показ\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Для оплаты: @InvictumMurad"
        )
        await message.answer(text)


@dp.message(F.text.in_(["📢 Реклама", "📢 Reklama"]))
async def advertising(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    db.close()
    
    webapp_url = WEBAPP_BASE_URL or os.environ.get('REPLIT_DEV_DOMAIN', '')
    if webapp_url and not webapp_url.startswith('https://'):
        webapp_url = f"https://{webapp_url}"
    
    if lang == 'uz':
        btn_place_ad = "📢 Reklama joylashtirish"
        btn_contact = "💬 Administrator bilan bog'lanish"
        text_with_webapp = (
            "📢 Botda reklama\n\n"
            "25,000+ faol foydalanuvchilar uchun reklama joylashtiring!\n\n"
            "Batafsil ma'lumot uchun tugmani bosing:"
        )
        text_no_webapp = (
            "📢 Botda reklama\n\n"
            "💰 100 000 so'm/oy\n"
            "👥 25 000+ faol foydalanuvchilar\n\n"
            "✅ Maqsadli auditoriya — ko'chmas mulk qidiruvchilar\n"
            "✅ Ko'rishlar statistikasi\n"
            "✅ Arzon narx\n\n"
            "Joylashtirish uchun: @InvictumMurad"
        )
    else:
        btn_place_ad = "📢 Разместить рекламу"
        btn_contact = "💬 Связаться с администратором"
        text_with_webapp = (
            "📢 Реклама в боте\n\n"
            "Разместите рекламу для 25,000+ активных пользователей!\n\n"
            "Нажмите кнопку ниже для подробностей:"
        )
        text_no_webapp = (
            "📢 Реклама в боте\n\n"
            "💰 100 000 сум/месяц\n"
            "👥 25 000+ активных пользователей\n\n"
            "✅ Целевая аудитория — искатели недвижимости\n"
            "✅ Статистика показов\n"
            "✅ Доступная цена\n\n"
            "Для размещения: @InvictumMurad"
        )
    
    if webapp_url:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=btn_place_ad,
                web_app=WebAppInfo(url=f"{webapp_url}/webapp/advertising")
            )],
            [InlineKeyboardButton(
                text=btn_contact,
                url="https://t.me/InvictumMurad"
            )]
        ])
        await message.answer(text_with_webapp, reply_markup=keyboard)
    else:
        await message.answer(text_no_webapp)


@dp.message(F.text.in_(["❤️ Мои лайки", "❤️ Mening layklarim"]))
async def my_likes(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    likes = db.query(Like).filter(Like.user_id == user.id).order_by(Like.created_at.desc()).all()
    db.close()
    
    if not likes:
        await message.answer("Вы еще не лайкнули ни одной квартиры.")
        return
    
    text = "❤️ Ваши лайки:\n\n"
    
    for like in likes[:20]:
        db = SessionLocal()
        prop = db.query(Property).filter(Property.id == like.property_id).first()
        db.close()
        
        if prop:
            status = "🟢 Мэтч!" if like.is_matched else "⏳ Ожидание"
            text += (
                f"{status} {prop.district or 'Объект'}\n"
                f"   {prop.rooms} комн. | {prop.price:,} сум\n\n"
            )
    
    await message.answer(text)


class QuickChangeStates(StatesGroup):
    district = State()
    budget = State()


@dp.callback_query(F.data == "quick_change_district")
async def quick_change_district_callback(callback: types.CallbackQuery, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    lang = user.language if user else 'ru'
    districts = db.query(District).all()
    db.close()
    
    keyboard_buttons = []
    row = []
    for district in districts:
        row.append(KeyboardButton(text=district.name))
        if len(row) == 2:
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)
    keyboard_buttons.append([KeyboardButton(text=get_text('any_district', lang))])
    keyboard_buttons.append([KeyboardButton(text=get_text('back', lang))])
    
    await state.update_data(user_lang=lang)
    await callback.message.answer(
        get_text('choose_district', lang),
        reply_markup=ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
    )
    await state.set_state(QuickChangeStates.district)
    await callback.answer()


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), QuickChangeStates.district)
async def quick_district_back(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    await state.clear()
    keyboard = get_buyer_menu(lang)
    await message.answer(get_text('returned_to_main_menu', lang), reply_markup=keyboard)


@dp.message(QuickChangeStates.district)
async def quick_district_selected(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    any_district_texts = [get_text('any_district', 'ru'), get_text('any_district', 'uz')]
    if message.text in any_district_texts:
        db = SessionLocal()
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        user.search_district = "Любой"
        db.commit()
        db.close()
        
        await state.clear()
        keyboard = get_buyer_menu(lang)
        await message.answer(
            "✅ Район изменён: Любой" if lang == 'ru' else "✅ Tuman o'zgartirildi: Istalgan",
            reply_markup=keyboard
        )
        return
    
    district = message.text.strip()
    db = SessionLocal()
    valid_districts = [d.name for d in db.query(District).all()]
    db.close()
    
    if district in valid_districts:
        db = SessionLocal()
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        user.search_district = district
        db.commit()
        db.close()
        
        await state.clear()
        keyboard = get_buyer_menu(lang)
        await message.answer(
            f"✅ Район изменён: {district}" if lang == 'ru' else f"✅ Tuman o'zgartirildi: {district}",
            reply_markup=keyboard
        )


@dp.callback_query(F.data == "quick_change_budget")
async def quick_change_budget_callback(callback: types.CallbackQuery, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    lang = user.language if user else 'ru'
    db.close()
    
    await state.update_data(user_lang=lang)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('budget_single', lang))],
            [KeyboardButton(text=get_text('budget_range', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await callback.message.answer(get_text('budget_type_question', lang), reply_markup=keyboard)
    await state.set_state(QuickChangeStates.budget)
    await callback.answer()


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), QuickChangeStates.budget)
async def quick_budget_back(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    await state.clear()
    keyboard = get_buyer_menu(lang)
    await message.answer(get_text('returned_to_main_menu', lang), reply_markup=keyboard)


@dp.message(QuickChangeStates.budget)
async def quick_budget_type_selected(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    if message.text == get_text('budget_single', lang):
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=get_text('back', lang))]],
            resize_keyboard=True
        )
        await message.answer(get_text('enter_single_budget', lang), reply_markup=keyboard)
        await state.update_data(budget_mode='single')
    elif message.text == get_text('budget_range', lang):
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=get_text('back', lang))]],
            resize_keyboard=True
        )
        await message.answer(get_text('enter_min_budget', lang), reply_markup=keyboard)
        await state.update_data(budget_mode='range')
    else:
        budget = validate_number(message.text)
        if budget is None or budget <= 0:
            await message.answer(get_text('invalid_budget', lang))
            return
        
        budget_mode = data.get('budget_mode')
        if budget_mode == 'single':
            db = SessionLocal()
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            user.search_budget_min = int(budget * 0.8)
            user.search_budget_max = int(budget * 1.2)
            db.commit()
            db.close()
            
            await state.clear()
            keyboard = get_buyer_menu(lang)
            await message.answer(
                f"✅ Бюджет изменён: ${budget:,.0f} (±20%)" if lang == 'ru' else f"✅ Byudjet o'zgartirildi: ${budget:,.0f} (±20%)",
                reply_markup=keyboard
            )
        elif budget_mode == 'range':
            if 'quick_budget_min' not in data:
                await state.update_data(quick_budget_min=int(budget))
                await message.answer(get_text('enter_max_budget', lang))
            else:
                budget_min = data.get('quick_budget_min')
                budget_max = int(budget)
                if budget_min > budget_max:
                    await message.answer(get_text('min_greater_than_max', lang))
                    return
                
                db = SessionLocal()
                user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
                user.search_budget_min = budget_min
                user.search_budget_max = budget_max
                db.commit()
                db.close()
                
                await state.clear()
                keyboard = get_buyer_menu(lang)
                await message.answer(
                    f"✅ Бюджет изменён: ${budget_min:,} - ${budget_max:,}" if lang == 'ru' else f"✅ Byudjet o'zgartirildi: ${budget_min:,} - ${budget_max:,}",
                    reply_markup=keyboard
                )


class SearchSettingsStates(StatesGroup):
    deal_type = State()
    prop_type = State()
    rooms = State()
    floor = State()
    floor_custom = State()
    district = State()
    budget_type = State()
    budget_single = State()
    budget_min = State()
    budget_max = State()
    bio = State()


@dp.message(F.text.in_(["⚙️ Настройки поиска", "⚙️ Qidiruv sozlamalari"]))
async def search_settings(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    lang = get_user_lang(user)
    db.close()
    
    await state.update_data(user_lang=lang)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('buy_button', lang)), KeyboardButton(text=get_text('rent_button', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('search_settings_title', lang), reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.deal_type)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), SearchSettingsStates.deal_type)
async def settings_back_to_menu(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    await state.clear()
    keyboard = get_buyer_menu(lang)
    await message.answer(get_text('returned_to_main_menu', lang), reply_markup=keyboard)


@dp.message(SearchSettingsStates.deal_type)
async def settings_deal_selected(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    if message.text in [get_text('buy_button', 'ru'), get_text('buy_button', 'uz')]:
        deal_type = "buy"
    elif message.text in [get_text('rent_button', 'ru'), get_text('rent_button', 'uz')]:
        deal_type = "rent"
    else:
        return
    
    await state.update_data(search_deal_type=deal_type)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('apartment', lang))],
            [KeyboardButton(text=get_text('house', lang))],
            [KeyboardButton(text=get_text('commercial', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('choose_property_type', lang), reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.prop_type)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), SearchSettingsStates.prop_type)
async def settings_back_to_deal(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('buy_button', lang)), KeyboardButton(text=get_text('rent_button', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('what_interests_you', lang), reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.deal_type)


@dp.message(SearchSettingsStates.prop_type)
async def settings_proptype_selected(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    prop_types = {
        get_text('apartment', 'ru'): "apartment",
        get_text('apartment', 'uz'): "apartment",
        get_text('house', 'ru'): "house",
        get_text('house', 'uz'): "house",
        get_text('commercial', 'ru'): "commercial",
        get_text('commercial', 'uz'): "commercial"
    }
    prop_type = prop_types.get(message.text)
    if not prop_type:
        return
    
    await state.update_data(search_prop_type=prop_type)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2"), KeyboardButton(text="3")],
            [KeyboardButton(text="4+"), KeyboardButton(text=get_text('studio', lang))],
            [KeyboardButton(text=get_text('any_rooms', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('choose_rooms_count', lang), reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.rooms)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), SearchSettingsStates.rooms)
async def settings_back_to_proptype(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('apartment', lang))],
            [KeyboardButton(text=get_text('house', lang))],
            [KeyboardButton(text=get_text('commercial', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('choose_property_type', lang), reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.prop_type)


@dp.message(SearchSettingsStates.rooms)
async def settings_rooms_selected(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    rooms_map = {"1": "1", "2": "2", "3": "3", "4+": "4", "студия": "studio", "studiya": "studio", "любое": "any", "istalgan": "any"}
    rooms = rooms_map.get(message.text.lower())
    if not rooms:
        return
    
    await state.update_data(search_rooms=rooms)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('floor_any', lang))],
            [KeyboardButton(text=get_text('floor_custom', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('choose_floor', lang), reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.floor)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), SearchSettingsStates.floor)
async def settings_back_to_rooms_from_floor(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2"), KeyboardButton(text="3")],
            [KeyboardButton(text="4+"), KeyboardButton(text="Студия" if lang == 'ru' else "Studiya")],
            [KeyboardButton(text=get_text('any_rooms', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('choose_rooms_count', lang), reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.rooms)


@dp.message(SearchSettingsStates.floor)
async def settings_floor_selected(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    custom_texts = [get_text('floor_custom', 'ru'), get_text('floor_custom', 'uz')]
    if message.text in custom_texts:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=get_text('back', lang))]],
            resize_keyboard=True
        )
        await message.answer(get_text('enter_floor_custom', lang), reply_markup=keyboard)
        await state.set_state(SearchSettingsStates.floor_custom)
        return
    
    any_texts = [get_text('floor_any', 'ru'), get_text('floor_any', 'uz')]
    if message.text in any_texts:
        floor = "any"
    else:
        return
    
    await state.update_data(search_floor=floor)
    
    await message.answer(
        get_text('choose_district', lang),
        reply_markup=get_district_keyboard([], lang)
    )
    await state.set_state(SearchSettingsStates.district)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), SearchSettingsStates.floor_custom)
async def settings_back_to_floor_from_custom(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('floor_any', lang))],
            [KeyboardButton(text=get_text('floor_custom', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('choose_floor', lang), reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.floor)


@dp.message(SearchSettingsStates.floor_custom)
async def settings_floor_custom_entered(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    text = message.text.strip()
    
    import re
    if re.match(r'^\d+$', text):
        floor = text
    elif re.match(r'^\d+-\d+$', text):
        parts = text.split('-')
        if int(parts[0]) <= int(parts[1]):
            floor = text
        else:
            await message.answer(get_text('invalid_floor', lang))
            return
    else:
        await message.answer(get_text('invalid_floor', lang))
        return
    
    await state.update_data(search_floor=floor)
    
    await message.answer(
        get_text('choose_district', lang),
        reply_markup=get_district_keyboard([], lang)
    )
    await state.set_state(SearchSettingsStates.district)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), SearchSettingsStates.district)
async def settings_back_to_floor(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('floor_any', lang))],
            [KeyboardButton(text=get_text('floor_custom', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('choose_floor', lang), reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.floor)


@dp.message(SearchSettingsStates.district)
async def settings_district_selected(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    any_district_texts = [get_text('any_district', 'ru'), get_text('any_district', 'uz')]
    
    if message.text in any_district_texts:
        await state.update_data(search_district="Любой")
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=get_text('budget_single', lang))],
                [KeyboardButton(text=get_text('budget_range', lang))],
                [KeyboardButton(text=get_text('back', lang))]
            ],
            resize_keyboard=True
        )
        await message.answer(get_text('budget_type_question', lang), reply_markup=keyboard)
        await state.set_state(SearchSettingsStates.budget_type)
        return
    
    district_name = message.text.strip()
    
    district_name_ru = district_name
    for ru_name, uz_name in DISTRICT_TRANSLATIONS.items():
        if district_name == uz_name:
            district_name_ru = ru_name
            break
    
    db = SessionLocal()
    valid_districts = [d.name for d in db.query(District).all()]
    db.close()
    
    if district_name_ru in valid_districts:
        await state.update_data(search_district=district_name_ru)
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=get_text('budget_single', lang))],
                [KeyboardButton(text=get_text('budget_range', lang))],
                [KeyboardButton(text=get_text('back', lang))]
            ],
            resize_keyboard=True
        )
        await message.answer(get_text('budget_type_question', lang), reply_markup=keyboard)
        await state.set_state(SearchSettingsStates.budget_type)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), SearchSettingsStates.budget_type)
async def settings_back_to_district(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    await message.answer(
        get_text('choose_district', lang),
        reply_markup=get_district_keyboard([], lang)
    )
    await state.set_state(SearchSettingsStates.district)


@dp.message(SearchSettingsStates.budget_type)
async def settings_budget_type_selected(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    single_texts = [get_text('budget_single', 'ru'), get_text('budget_single', 'uz')]
    range_texts = [get_text('budget_range', 'ru'), get_text('budget_range', 'uz')]
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=get_text('back', lang))]],
        resize_keyboard=True
    )
    
    if message.text in single_texts:
        await state.update_data(budget_mode='single')
        await message.answer(get_text('enter_single_budget', lang), reply_markup=keyboard)
        await state.set_state(SearchSettingsStates.budget_single)
    elif message.text in range_texts:
        await state.update_data(budget_mode='range')
        await message.answer(get_text('enter_min_budget', lang), reply_markup=keyboard)
        await state.set_state(SearchSettingsStates.budget_min)
    else:
        await message.answer(get_text('budget_type_question', lang))


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), SearchSettingsStates.budget_single)
async def settings_back_to_budget_type_from_single(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('budget_single', lang))],
            [KeyboardButton(text=get_text('budget_range', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('budget_type_question', lang), reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.budget_type)


@dp.message(SearchSettingsStates.budget_single)
async def settings_single_budget_entered(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    budget = validate_number(message.text)
    if budget is None or budget <= 0:
        await message.answer(get_text('invalid_budget', lang))
        return
    
    budget = int(budget)
    budget_min = int(budget * 0.8)
    budget_max = int(budget * 1.2)
    await state.update_data(search_budget_min=budget_min, search_budget_max=budget_max)
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    current_bio = user.buyer_bio or ""
    db.close()
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('skip', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    
    bio_hint = f"\n\n{get_text('current_bio', lang)} {current_bio}" if current_bio else ""
    await message.answer(
        f"{get_text('add_bio', lang)}{bio_hint}",
        reply_markup=keyboard
    )
    await state.set_state(SearchSettingsStates.bio)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), SearchSettingsStates.budget_min)
async def settings_back_to_budget_type_from_min(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('budget_single', lang))],
            [KeyboardButton(text=get_text('budget_range', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('budget_type_question', lang), reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.budget_type)


@dp.message(SearchSettingsStates.budget_min)
async def settings_min_budget_entered(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    budget_min = validate_number(message.text)
    if budget_min is None or budget_min <= 0:
        await message.answer(get_text('invalid_budget', lang))
        return
    
    await state.update_data(search_budget_min=int(budget_min))
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=get_text('back', lang))]],
        resize_keyboard=True
    )
    await message.answer(get_text('enter_max_budget', lang), reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.budget_max)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), SearchSettingsStates.budget_max)
async def settings_back_to_min_budget(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=get_text('back', lang))]],
        resize_keyboard=True
    )
    await message.answer(get_text('enter_min_budget', lang), reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.budget_min)


@dp.message(SearchSettingsStates.budget_max)
async def settings_max_budget_entered(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    budget_max = validate_number(message.text)
    if budget_max is None or budget_max <= 0:
        await message.answer(get_text('invalid_budget', lang))
        return
    
    budget_min = data.get('search_budget_min', 0)
    if budget_max < budget_min:
        await message.answer(get_text('min_greater_than_max', lang))
        return
    
    await state.update_data(search_budget_max=int(budget_max))
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    current_bio = user.buyer_bio or ""
    db.close()
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('skip', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    
    bio_hint = f"\n\n{get_text('current_bio', lang)} {current_bio}" if current_bio else ""
    await message.answer(
        f"{get_text('add_bio', lang)}{bio_hint}",
        reply_markup=keyboard
    )
    await state.set_state(SearchSettingsStates.bio)


@dp.message(F.text.in_(["⬅️ Назад", "⬅️ Orqaga"]), SearchSettingsStates.bio)
async def settings_back_to_budget(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    budget_mode = data.get('budget_mode', 'single')
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('budget_single', lang))],
            [KeyboardButton(text=get_text('budget_range', lang))],
            [KeyboardButton(text=get_text('back', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('budget_type_question', lang), reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.budget_type)


@dp.message(SearchSettingsStates.bio)
async def settings_bio_entered(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('user_lang', 'ru')
    
    skip_texts = [get_text('skip', 'ru'), get_text('skip', 'uz')]
    is_skip = message.text in skip_texts
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if not is_skip:
        bio = message.text.strip()
        if len(bio) > 320:
            db.close()
            await message.answer(get_text('bio_too_long', lang))
            return
        user.buyer_bio = bio
    
    deal_type = data.get("search_deal_type", "buy")
    prop_type = data.get("search_prop_type", "apartment")
    rooms = data.get("search_rooms", "any")
    floor = data.get("search_floor", "any")
    district = data.get("search_district", "Любой")
    budget_min = data.get("search_budget_min", 0)
    budget_max = data.get("search_budget_max", 0)
    
    user.search_budget_min = int(budget_min) if budget_min else None
    user.search_budget_max = int(budget_max) if budget_max else None
    user.search_rooms = rooms
    user.search_floor = floor
    user.search_district = district
    user.search_payment_type = f"{deal_type}_{prop_type}"
    user.search_deal_type = "sale" if deal_type == "buy" else "rent"
    db.commit()
    db.close()
    
    await state.clear()
    
    keyboard = get_buyer_menu(lang)
    
    await message.answer(
        get_text('settings_saved', lang),
        reply_markup=keyboard
    )


PROPERTY_ACTIVE_DAYS = 30
PROPERTY_ARCHIVE_DAYS = 30
LIKE_LIFETIME_DAYS = 1


async def cleanup_old_likes():
    """Фоновая задача для удаления лайков старше 1 дня"""
    while True:
        try:
            await asyncio.sleep(3600)
            
            db = SessionLocal()
            cutoff_date = datetime.utcnow() - timedelta(days=LIKE_LIFETIME_DAYS)
            
            old_likes = db.query(Like).filter(Like.created_at < cutoff_date).all()
            
            deleted_count = 0
            for like in old_likes:
                prop = db.query(Property).filter(Property.id == like.property_id).first()
                if prop and prop.likes_count > 0:
                    prop.likes_count -= 1
                db.delete(like)
                deleted_count += 1
            
            if deleted_count > 0:
                db.commit()
                print(f"Cleanup: deleted {deleted_count} old likes")
            
            db.close()
            
        except Exception as e:
            print(f"Likes cleanup task error: {e}")
            await asyncio.sleep(60)


async def property_lifecycle_task():
    """Фоновая задача для управления жизненным циклом объявлений:
    - Через 30 дней активности -> архив
    - Через 30 дней в архиве -> удаление
    """
    while True:
        try:
            await asyncio.sleep(3600)
            
            db = SessionLocal()
            now = datetime.utcnow()
            
            archive_cutoff = now - timedelta(days=PROPERTY_ACTIVE_DAYS)
            active_properties = db.query(Property).filter(
                Property.status == PropertyStatus.ACTIVE,
                Property.created_at < archive_cutoff
            ).all()
            
            archived_count = 0
            for prop in active_properties:
                try:
                    prop.status = PropertyStatus.ARCHIVE
                    prop.archived_at = now
                    archived_count += 1
                    
                    owner = db.query(User).filter(User.id == prop.owner_id).first()
                    if owner and owner.telegram_id:
                        try:
                            await bot.send_message(
                                owner.telegram_id,
                                f"📦 Объявление перемещено в архив\n\n"
                                f"📍 {prop.district or 'Объект'}\n"
                                f"💰 {prop.price:,} сум\n\n"
                                f"Причина: прошло 30 дней с момента публикации.\n"
                                f"У вас есть 30 дней, чтобы активировать его снова, иначе оно будет удалено.\n\n"
                                f"Перейдите в '🏢 Мои объекты', чтобы активировать."
                            )
                        except:
                            pass
                except Exception as e:
                    print(f"Error archiving property {prop.id}: {e}")
                    continue
            
            if archived_count > 0:
                db.commit()
                print(f"Lifecycle: archived {archived_count} properties")
            
            delete_cutoff = now - timedelta(days=PROPERTY_ARCHIVE_DAYS)
            old_archived = db.query(Property).filter(
                Property.status == PropertyStatus.ARCHIVE,
                Property.archived_at != None,
                Property.archived_at < delete_cutoff
            ).all()
            
            deleted_count = 0
            for prop in old_archived:
                try:
                    owner = db.query(User).filter(User.id == prop.owner_id).first()
                    
                    if owner and owner.telegram_id:
                        try:
                            await bot.send_message(
                                owner.telegram_id,
                                f"🗑 Объявление удалено\n\n"
                                f"📍 {prop.district or 'Объект'}\n"
                                f"💰 {prop.price:,} сум\n\n"
                                f"Причина: объявление находилось в архиве более 30 дней.\n"
                                f"Вы можете добавить новое объявление."
                            )
                        except:
                            pass
                    
                    db.query(Like).filter(Like.property_id == prop.id).delete()
                    db.delete(prop)
                    deleted_count += 1
                except Exception as e:
                    print(f"Error deleting property {prop.id}: {e}")
                    continue
            
            if deleted_count > 0:
                db.commit()
                print(f"Lifecycle: deleted {deleted_count} old archived properties")
            
            db.close()
            
        except Exception as e:
            print(f"Property lifecycle task error: {e}")
            await asyncio.sleep(60)


@dp.message(F.text)
async def catch_all_handler(message: types.Message, state: FSMContext):
    """Ловит все нераспознанные текстовые сообщения и показывает актуальное меню"""
    current_state = await state.get_state()
    if current_state:
        return
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    db.close()
    
    if not user:
        await message.answer(
            "👋 Добро пожаловать! Нажмите /start чтобы начать.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return
    
    lang = get_user_lang(user)
    if user.role == UserRole.BUYER:
        keyboard = get_buyer_menu(lang)
        await message.answer(
            "🏠 Главное меню покупателя\n\n"
            "Выберите действие:",
            reply_markup=keyboard
        )
    elif user.role == UserRole.SELLER:
        is_developer = user.seller_type == SellerType.DEVELOPER if user else False
        keyboard = get_seller_menu(lang, is_developer=is_developer)
        await message.answer(
            "💼 Главное меню продавца\n\n"
            "Выберите действие:",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            "Нажмите /start чтобы начать.",
            reply_markup=types.ReplyKeyboardRemove()
        )


@dp.message(F.photo)
async def handle_photo_for_file_id(message: types.Message):
    """Возвращает file_id фото для старших админов"""
    from models import AdminRole
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    is_senior_admin = user and (user.is_admin or user.admin_role in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]) if user else False
    db.close()
    
    if is_senior_admin:
        photo = message.photo[-1]
        await message.reply(
            f"<b>file_id из отвеченного медиа:</b>\n"
            f"• photo:\n<code>{photo.file_id}</code>\n"
            f"• unique_id: <code>{photo.file_unique_id}</code>",
            parse_mode="HTML"
        )


@dp.message(F.video)
async def handle_video_for_file_id(message: types.Message):
    """Возвращает file_id видео для старших админов"""
    from models import AdminRole
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    is_senior_admin = user and (user.is_admin or user.admin_role in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]) if user else False
    db.close()
    
    if is_senior_admin:
        video = message.video
        await message.reply(
            f"<b>file_id из отвеченного медиа:</b>\n"
            f"• video:\n<code>{video.file_id}</code>\n"
            f"• unique_id: <code>{video.file_unique_id}</code>",
            parse_mode="HTML"
        )


async def main():
    print("Initializing database...")
    init_db()
    
    print("Starting background tasks...")
    asyncio.create_task(property_lifecycle_task())
    asyncio.create_task(cleanup_old_likes())
    
    print("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
