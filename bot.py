import asyncio
import os
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, WebAppInfo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from models import SessionLocal, User, Property, Like, Match, Offer, District, ResidentialComplex
from models import UserRole, SellerType, TariffType, PropertyType, PropertyStatus, init_db

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'InvictumMurad')
WEBAPP_URL = os.environ.get('WEBAPP_URL', '')

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


class RegistrationStates(StatesGroup):
    choosing_role = State()
    buyer_rooms = State()
    buyer_housing_type = State()
    buyer_district = State()
    buyer_budget = State()
    buyer_payment = State()
    buyer_phone = State()
    seller_type = State()
    seller_company = State()
    seller_manager = State()
    seller_phone = State()


class PropertyStates(StatesGroup):
    property_type = State()
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


class SearchStates(StatesGroup):
    viewing_properties = State()
    current_index = State()


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
            [KeyboardButton(text="🏠 Я ищу недвижимость")],
            [KeyboardButton(text="💼 Я хочу продать/сдать")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "👋 Добро пожаловать в Real Estate Bot!\n\n"
        "Это \"Tinder для недвижимости\" — находите покупателей или квартиры одним свайпом.\n\n"
        "Выберите вашу роль:",
        reply_markup=keyboard
    )
    await state.set_state(RegistrationStates.choosing_role)


@dp.message(F.text == "🏠 Я ищу недвижимость", RegistrationStates.choosing_role)
async def process_buyer_role(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    if user:
        user.role = UserRole.BUYER
        db.commit()
    db.close()
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2"), KeyboardButton(text="3")],
            [KeyboardButton(text="4+"), KeyboardButton(text="Студия")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "🏠 Отлично! Давайте настроим ваши параметры поиска.\n\n"
        "Сколько комнат вам нужно?",
        reply_markup=keyboard
    )
    await state.set_state(RegistrationStates.buyer_rooms)


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
    housing_map = {
        "🏗 новостройка": "Новостройка",
        "🏠 вторичный рынок": "Вторичный рынок",
        "любой тип": "Любой"
    }
    housing_type = housing_map.get(message.text.lower(), message.text)
    await state.update_data(housing_type=housing_type)
    
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
    keyboard_buttons.append([KeyboardButton(text="Любой район")])
    keyboard_buttons.append([KeyboardButton(text="⬅️ Назад")])
    
    await message.answer(
        "📍 Выберите район:",
        reply_markup=ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
    )
    await state.set_state(RegistrationStates.buyer_district)


@dp.message(F.text == "⬅️ Назад", RegistrationStates.buyer_district)
async def back_to_housing_type(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏗 Новостройка")],
            [KeyboardButton(text="🏠 Вторичный рынок")],
            [KeyboardButton(text="Любой тип")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🏠 Какой тип жилья вас интересует?", reply_markup=keyboard)
    await state.set_state(RegistrationStates.buyer_housing_type)


@dp.message(RegistrationStates.buyer_district)
async def process_district(message: types.Message, state: FSMContext):
    district_name = message.text if message.text != "Любой район" else "Любой"
    await state.update_data(district=district_name)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True
    )
    
    await message.answer(
        "💰 Какой у вас бюджет (в USD)?\n\nВведите максимальную сумму цифрами:",
        reply_markup=keyboard
    )
    await state.set_state(RegistrationStates.buyer_budget)


@dp.message(F.text == "⬅️ Назад", RegistrationStates.buyer_budget)
async def back_to_district(message: types.Message, state: FSMContext):
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
    keyboard_buttons.append([KeyboardButton(text="Любой район")])
    keyboard_buttons.append([KeyboardButton(text="⬅️ Назад")])
    
    await message.answer(
        "📍 Выберите район:",
        reply_markup=ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
    )
    await state.set_state(RegistrationStates.buyer_district)


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


@dp.message(F.text == "⬅️ Назад", RegistrationStates.buyer_phone)
async def back_to_payment(message: types.Message, state: FSMContext):
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


@dp.message(F.contact, RegistrationStates.buyer_phone)
async def process_buyer_phone_contact(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number
    data = await state.get_data()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    if user:
        user.phone = phone
        user.search_rooms = data.get("rooms", "")
        user.search_housing_type = data.get("housing_type", "")
        user.search_district = data.get("district", "")
        user.search_budget_max = data.get("budget", 0)
        user.search_payment_type = data.get("payment", "cash")
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
        user.search_rooms = data.get("rooms", "")
        user.search_housing_type = data.get("housing_type", "")
        user.search_district = data.get("district", "")
        user.search_budget_max = data.get("budget", 0)
        user.search_payment_type = data.get("payment", "cash")
        db.commit()
    db.close()
    
    await state.clear()
    await show_buyer_menu(message, message.from_user.id)


async def show_buyer_menu(message, user_id):
    db = SessionLocal()
    properties_count = db.query(Property).filter(Property.status == PropertyStatus.ACTIVE).count()
    db.close()
    
    keyboard = get_buyer_menu()
    
    await message.answer(
        f"✅ Регистрация завершена!\n\n"
        f"📊 Сейчас доступно {properties_count} квартир.\n\n"
        f"Нажмите '🏠 Смотреть квартиры', чтобы начать поиск!",
        reply_markup=keyboard
    )


def get_buyer_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Смотреть квартиры")],
            [KeyboardButton(text="⚙️ Настройки поиска")],
            [KeyboardButton(text="👤 Профиль")]
        ],
        resize_keyboard=True
    )


def get_buyer_profile_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💼 Войти в режим продавца")],
            [KeyboardButton(text="❤️ Лайки"), KeyboardButton(text="💬 Переписка")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )


WEBAPP_BASE_URL = os.environ.get('REPLIT_DEV_DOMAIN', '')
if WEBAPP_BASE_URL and not WEBAPP_BASE_URL.startswith('https://'):
    WEBAPP_BASE_URL = f"https://{WEBAPP_BASE_URL}"


@dp.message(F.text == "💼 Я хочу продать/сдать", RegistrationStates.choosing_role)
async def process_seller_role(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    if user:
        user.role = UserRole.SELLER
        db.commit()
    db.close()
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Собственник")],
            [KeyboardButton(text="🔑 Риелтор")],
            [KeyboardButton(text="🏗 Застройщик")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer("💼 Отлично! Выберите тип аккаунта:", reply_markup=keyboard)
    await state.set_state(RegistrationStates.seller_type)


@dp.message(F.text == "⬅️ Назад", RegistrationStates.seller_type)
async def back_to_role_from_seller(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Я ищу недвижимость")],
            [KeyboardButton(text="💼 Я хочу продать/сдать")]
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите вашу роль:", reply_markup=keyboard)
    await state.set_state(RegistrationStates.choosing_role)


@dp.message(F.text == "🏠 Собственник", RegistrationStates.seller_type)
async def process_owner_type(message: types.Message, state: FSMContext):
    await state.update_data(seller_type=SellerType.OWNER)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер", request_contact=True)],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "📱 Поделитесь вашим номером телефона.\n\n"
        "Это будет ваш идентификатор аккаунта:",
        reply_markup=keyboard
    )
    await state.set_state(RegistrationStates.seller_phone)


@dp.message(F.text == "🔑 Риелтор", RegistrationStates.seller_type)
async def process_realtor_type(message: types.Message, state: FSMContext):
    await state.update_data(seller_type=SellerType.REALTOR)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер", request_contact=True)],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "📱 Поделитесь вашим номером телефона.\n\n"
        "Это будет ваш идентификатор аккаунта:",
        reply_markup=keyboard
    )
    await state.set_state(RegistrationStates.seller_phone)


@dp.message(F.text == "🏗 Застройщик", RegistrationStates.seller_type)
async def process_developer_type(message: types.Message, state: FSMContext):
    await state.update_data(seller_type=SellerType.DEVELOPER)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер", request_contact=True)],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "📱 Поделитесь вашим номером телефона.\n\n"
        "Это будет ваш идентификатор аккаунта:",
        reply_markup=keyboard
    )
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
    
    await message.answer("🏢 Введите название компании или ваше имя:", reply_markup=keyboard)
    await state.set_state(RegistrationStates.seller_company)


async def show_seller_menu(message, user_id, buyers_count=None):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_id).first()
    
    if buyers_count is None:
        buyers_count = db.query(User).filter(User.role == UserRole.BUYER).count()
    
    properties = db.query(Property).filter(Property.owner_id == user.id).all()
    total_views = sum(p.views_count for p in properties)
    total_likes = sum(p.likes_count for p in properties)
    matches_count = db.query(Match).filter(Match.seller_id == user.id).count()
    db.close()
    
    tariff_names = {
        TariffType.FREE: "🆓 Бесплатный",
        TariffType.PRO: "⭐ Про",
        TariffType.PREMIUM: "👑 Премиум",
        TariffType.AGENCY_START: "⭐ Про",
        TariffType.DEVELOPER_PRO: "👑 Премиум"
    }
    
    keyboard = get_seller_menu()
    
    await message.answer(
        f"✅ Регистрация завершена!\n\n"
        f"🔥 Прямо сейчас в боте {buyers_count} человек ищут квартиру!\n\n"
        f"📊 Ваша статистика:\n"
        f"👁 Просмотров: {total_views}\n"
        f"❤️ Лайков: {total_likes}\n"
        f"🤝 Мэтчей: {matches_count}\n"
        f"💳 Тариф: {tariff_names.get(user.tariff, 'Бесплатный')}",
        reply_markup=keyboard
    )


@dp.message(F.text == "➕ Добавить объект")
async def add_property_start(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if not user or user.role != UserRole.SELLER:
        await message.answer("Эта функция доступна только для продавцов.")
        db.close()
        return
    
    limits = get_tariff_limits(user.tariff, user.is_admin)
    current_properties = db.query(Property).filter(
        Property.owner_id == user.id,
        Property.status != PropertyStatus.ARCHIVE
    ).count()
    db.close()
    
    if current_properties >= limits["properties"]:
        await message.answer(
            f"⚠️ Вы достигли лимита объектов ({limits['properties']}) для вашего тарифа.\n\n"
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
    await message.answer("📝 Введите описание объекта (или отправьте 'Пропустить'):")
    await state.set_state(PropertyStates.description)


@dp.message(PropertyStates.description)
async def process_prop_description(message: types.Message, state: FSMContext):
    description = message.text if message.text.lower() != "пропустить" else ""
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
    
    prop = Property(
        owner_id=user.id,
        property_type=data.get("property_type", PropertyType.SALE),
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
        status=PropertyStatus.ACTIVE
    )
    db.add(prop)
    db.commit()
    
    prop.unique_id = f"F2F-{prop.id:05d}"
    db.commit()
    prop_id = prop.id
    db.close()
    
    type_name = "Продажа" if data.get("property_type") == PropertyType.SALE else "Аренда"
    furniture = "Да" if data.get("has_furniture") else "Нет"
    
    summary = (
        f"✅ Объявление добавлено!\n\n"
        f"🆔 <b>ID: {prop.unique_id}</b>\n\n"
        f"📋 ХАРАКТЕРИСТИКИ:\n"
        f"🏷 Тип сделки: {type_name}\n"
        f"📍 Район: {data.get('district', '')}\n"
        f"🚪 Комнат: {data.get('rooms', '')}\n"
        f"🏢 Этаж: {data.get('floor', '')}/{data.get('total_floors', '')}\n"
        f"📐 Площадь: {data.get('area', '')} м²\n"
        f"🏠 Тип дома: {data.get('building_type', '')}\n"
        f"🔨 Ремонт: {data.get('renovation', '')}\n"
        f"🛋 Мебель: {furniture}\n"
        f"🚪 Комнаты: {data.get('room_type', '')}\n"
        f"🚿 Санузел: {data.get('bathroom_type', '')}\n"
        f"💰 Цена: ${data.get('price', 0):,}\n"
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
    
    keyboard = get_seller_menu()
    
    await callback.message.answer(
        f"🎯 {buyers_count} покупателей ищут похожие квартиры.\n"
        f"Ваш объект уже виден им в ленте!",
        reply_markup=keyboard
    )


@dp.message(F.text == "🏠 Смотреть квартиры")
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
    
    if user.search_payment_type:
        if user.search_payment_type.startswith("rent"):
            query = query.filter(Property.property_type == PropertyType.RENT)
        elif user.search_payment_type.startswith("buy"):
            query = query.filter(Property.property_type == PropertyType.SALE)
    
    if user.search_rooms:
        rooms_list = [int(r.strip()) for r in user.search_rooms.split(",") if r.strip().isdigit()]
        if rooms_list:
            query = query.filter(Property.rooms.in_(rooms_list))
    
    if user.search_housing_type and user.search_housing_type not in ["Любой", ""]:
        query = query.filter(Property.housing_type.ilike(f"%{user.search_housing_type}%"))
    
    if user.search_district and user.search_district not in ["Любой", ""]:
        districts = [d.strip() for d in user.search_district.split(",") if d.strip() and d.strip() != "Любой"]
        if districts:
            query = query.filter(Property.district.in_(districts))
    
    if user.search_budget_max:
        query = query.filter(Property.price <= user.search_budget_max)
    
    if user.search_budget_min:
        query = query.filter(Property.price >= user.search_budget_min)
    
    if liked_ids:
        query = query.filter(Property.id.notin_(liked_ids))
    if skipped_ids:
        query = query.filter(Property.id.notin_(skipped_ids))
    properties = query.order_by(Property.created_at.desc()).all()
    
    db.close()
    
    if not properties:
        if liked_ids or skipped_ids:
            await message.answer("✅ Вы просмотрели все доступные квартиры!\n\nПопробуйте позже — появятся новые объекты.")
        else:
            await message.answer("😔 Пока нет квартир по вашим критериям. Попробуйте позже!")
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
    
    contact_phone = prop.phone if prop.phone else None
    if not contact_phone:
        owner = db.query(User).filter(User.id == prop.owner_id).first()
        contact_phone = owner.phone if owner and owner.phone else "Не указан"
    
    type_emoji = "🏷" if prop.property_type == PropertyType.SALE else "🔑"
    type_name = "ПРОДАЖА" if prop.property_type == PropertyType.SALE else "АРЕНДА"
    
    text = f"{type_emoji} <b>{type_name}</b>  •  ID: {prop.id}\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    text += f"💰 <b>${prop.price:,}</b>\n\n"
    
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
        desc = prop.description[:300] + "..." if len(prop.description) > 300 else prop.description
        text += f"\n💬 <i>{desc}</i>"
    
    search_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Не нравится"), KeyboardButton(text="❤️ Нравится")],
            [KeyboardButton(text="🔙 Назад")]
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


@dp.message(F.text == "❤️ Нравится", SearchStates.viewing_properties)
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
                        f"💰 ${prop.price:,}\n\n"
                        f"Перейдите в раздел 'Меня лайкнули', чтобы открыть контакт!"
                    )
                except:
                    pass
    
    db.close()
    
    await message.answer("❤️ Лайк отправлен!")
    await show_next_property_reply(message, state)


@dp.message(F.text == "❌ Не нравится", SearchStates.viewing_properties)
async def process_skip_reply(message: types.Message, state: FSMContext):
    await show_next_property_reply(message, state)


@dp.message(F.text == "🔙 Назад", SearchStates.viewing_properties)
async def process_back_reply(message: types.Message, state: FSMContext):
    await state.clear()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    db.close()
    
    if user and user.role == UserRole.BUYER:
        keyboard = get_buyer_menu()
    else:
        keyboard = get_seller_menu()
    
    await message.answer("Вы вернулись в меню", reply_markup=keyboard)


async def show_next_property_reply(message, state):
    data = await state.get_data()
    properties = data.get("properties", [])
    current_index = data.get("current_index", 0) + 1
    
    if current_index >= len(properties):
        db = SessionLocal()
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        db.close()
        
        keyboard = get_buyer_menu()
        
        await message.answer(
            "🎉 Вы просмотрели все доступные квартиры!\n\n"
            "Новые объекты появляются каждый день. Заходите позже!",
            reply_markup=keyboard
        )
        await state.clear()
        return
    
    await state.update_data(current_index=current_index)
    await show_property_card(message, properties[current_index], state)


@dp.message(F.text == "🏢 Мои объекты")
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
            f"📋 {type_str} | {prop.rooms} комн. | <b>${prop.price:,}</b>\n"
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
            ],
            [
                InlineKeyboardButton(text="📦 В архив" if prop.status == PropertyStatus.ACTIVE else "✅ Активировать", 
                                     callback_data=f"prop_toggle_{prop.id}")
            ]
        ]
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
    
    await callback.message.edit_text(
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
    
    db.query(Like).filter(Like.property_id == prop_id).delete()
    db.delete(prop)
    db.commit()
    db.close()
    
    await callback.message.edit_text("✅ Объект успешно удалён!")


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
    await message.answer(f"✅ Цена изменена на ${int(price):,}")


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


@dp.message(F.text == "❤️ Меня лайкнули")
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
            
            text += (
                f"🏠 Объект: {prop_id}\n"
                f"👤 {name} | {username}\n"
                f"📞 {phone}\n"
                f"💰 Бюджет: {budget}\n"
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
            f"💰 ${prop.price:,}\n\n"
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


@dp.message(F.text == "💬 Сделки")
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
        f"💰 ${prop.price:,}\n"
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
    prop_type = State()
    budget = State()


def get_seller_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить объект")],
            [KeyboardButton(text="🎯 Найти покупателя")],
            [KeyboardButton(text="👤 Профиль")]
        ],
        resize_keyboard=True
    )


def get_seller_profile_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❤️ Меня лайкнули"), KeyboardButton(text="💬 Сделки")],
            [KeyboardButton(text="🏢 Мои объекты"), KeyboardButton(text="💳 Тарифы")],
            [KeyboardButton(text="👤 Мой профиль")],
            [KeyboardButton(text="🔙 Главное меню")]
        ],
        resize_keyboard=True
    )


@dp.message(F.text == "🎯 Найти покупателя")
async def find_buyers(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    db.close()
    
    if user.role != UserRole.SELLER:
        await message.answer("Эта функция доступна только для продавцов.")
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
            [KeyboardButton(text="🏢 Квартиры")],
            [KeyboardButton(text="🏡 Дом / Участок")],
            [KeyboardButton(text="🏪 Коммерческая")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🎯 Найти покупателя\n\n🏢 В каком разделе ищем?", reply_markup=keyboard)
    await state.set_state(FindBuyerStates.prop_type)


@dp.message(F.text == "⬅️ Назад", FindBuyerStates.prop_type)
async def find_buyer_back_to_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы вернулись в меню", reply_markup=get_seller_menu())


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
            [KeyboardButton(text="До $30,000")],
            [KeyboardButton(text="$30,000 - $50,000")],
            [KeyboardButton(text="$50,000 - $100,000")],
            [KeyboardButton(text="$100,000 - $200,000")],
            [KeyboardButton(text="Свыше $200,000")],
            [KeyboardButton(text="Любой бюджет")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("💰 Под какой бюджет ищем покупателя?", reply_markup=keyboard)
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
    budget_ranges = {
        "До $30,000": (0, 30000),
        "$30,000 - $50,000": (30000, 50000),
        "$50,000 - $100,000": (50000, 100000),
        "$100,000 - $200,000": (100000, 200000),
        "Свыше $200,000": (200000, 999999999),
        "Любой бюджет": (0, 999999999)
    }
    budget_range = budget_ranges.get(message.text)
    if not budget_range:
        return
    
    data = await state.get_data()
    prop_type = data.get("find_prop_type", "apartment")
    min_budget, max_budget = budget_range
    
    await state.clear()
    
    db = SessionLocal()
    
    query = db.query(User).filter(
        User.role == UserRole.BUYER,
        User.search_budget_max > 0
    )
    
    if min_budget > 0:
        query = query.filter(User.search_budget_max >= min_budget)
    if max_budget < 999999999:
        query = query.filter(User.search_budget_max <= max_budget)
    
    buyers = query.order_by(User.created_at.desc()).limit(10).all()
    db.close()
    
    if not buyers:
        await message.answer("Пока нет покупателей с такими критериями.", reply_markup=get_seller_menu())
        return
    
    prop_names = {"apartment": "Квартиры", "house": "Дом/Участок", "commercial": "Коммерческая"}
    text = f"🎯 Покупатели ({prop_names.get(prop_type, prop_type)}, {message.text}):\n\n"
    
    keyboard_buttons = []
    for buyer in buyers:
        rooms = buyer.search_rooms or "Любые"
        district = buyer.search_district or "Любой район"
        budget = buyer.search_budget_max or 0
        
        text += (
            f"👤 {buyer.first_name or 'Покупатель'}\n"
            f"   🚪 {rooms} комн. | 📍 {district}\n"
            f"   💰 до ${budget:,}\n\n"
        )
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"📤 Предложить {buyer.first_name or 'покупателю'}", callback_data=f"offer_{buyer.id}")
        ])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons))
    await message.answer("Выберите покупателя или вернитесь в меню", reply_markup=get_seller_menu())


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
                text=f"{prop.district} - ${prop.price:,}",
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
            f"💰 ${prop.price:,}\n\n"
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


@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    db.close()
    
    if user.role == UserRole.SELLER:
        keyboard = get_seller_profile_menu()
        await message.answer("📂 Раздел профиля:", reply_markup=keyboard)
    else:
        keyboard = get_buyer_profile_menu()
        await message.answer("👤 Профиль", reply_markup=keyboard)


@dp.message(F.text == "👤 Мой профиль")
async def my_profile(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    db.close()
    
    await show_seller_profile_info(message, user)


@dp.message(F.text == "🔙 Главное меню")
async def back_to_main_menu(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    db.close()
    
    if user.role == UserRole.SELLER:
        keyboard = get_seller_menu()
    else:
        keyboard = get_buyer_menu()
    
    await message.answer("🏠 Главное меню", reply_markup=keyboard)


async def show_seller_profile_info(message, user):
    webapp_url = os.environ.get('REPLIT_DEV_DOMAIN', '')
    if not webapp_url:
        webapp_url = os.environ.get('REPLIT_DOMAINS', '').split(',')[0] if os.environ.get('REPLIT_DOMAINS') else ''
    
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
    )
    
    buttons = [[InlineKeyboardButton(text="🏠 Перейти в режим покупателя", callback_data="switch_to_buyer")]]
    
    if user.is_admin and webapp_url:
        buttons.append([InlineKeyboardButton(
            text="🔐 Админ-панель",
            web_app=types.WebAppInfo(url=f"https://{webapp_url}/webapp/admin?tg_id={user.telegram_id}")
        )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=keyboard)


async def show_buyer_profile(message, user):
    webapp_url = os.environ.get('REPLIT_DEV_DOMAIN', '')
    if not webapp_url:
        webapp_url = os.environ.get('REPLIT_DOMAINS', '').split(',')[0] if os.environ.get('REPLIT_DOMAINS') else ''
    
    payment_names = {"cash": "Наличные", "mortgage": "Ипотека", "installment": "Рассрочка"}
    budget = f"${user.search_budget_max:,}" if user.search_budget_max else "Не указан"
    
    text = (
        f"👤 Ваш профиль\n\n"
        f"🆔 Ваш ID: {user.telegram_id}\n"
        f"🚪 Ищу: {user.search_rooms or 'Любые'} комн.\n"
        f"📍 Район: {user.search_district or 'Любой'}\n"
        f"💰 Бюджет: до {budget}\n"
        f"💳 Оплата: {payment_names.get(user.search_payment_type, 'Не указано')}\n"
    )
    
    buttons = [[InlineKeyboardButton(text="💼 Перейти в режим продавца", callback_data="switch_to_seller")]]
    
    if user.is_admin and webapp_url:
        buttons.append([InlineKeyboardButton(
            text="🔐 Админ-панель",
            web_app=types.WebAppInfo(url=f"https://{webapp_url}/webapp/admin?tg_id={user.telegram_id}")
        )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=keyboard)


@dp.callback_query(F.data == "switch_to_buyer")
async def switch_to_buyer(callback: types.CallbackQuery, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    
    if user:
        user.role = UserRole.BUYER
        db.commit()
    db.close()
    
    await callback.answer("Режим изменён на покупателя")
    await callback.message.delete()
    
    keyboard = get_buyer_menu()
    
    await callback.message.answer(
        "🏠 Вы теперь в режиме покупателя!\n\n"
        "Нажмите '🏠 Смотреть квартиры', чтобы начать поиск.",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "switch_to_seller")
async def switch_to_seller(callback: types.CallbackQuery, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    
    if user:
        user.role = UserRole.SELLER
        db.commit()
    
    buyers_count = db.query(User).filter(User.role == UserRole.BUYER).count()
    db.close()
    
    await callback.answer("Режим изменён на продавца")
    await callback.message.delete()
    
    keyboard = get_seller_menu()
    
    await callback.message.answer(
        f"💼 Вы теперь в режиме продавца!\n\n"
        f"🔥 Прямо сейчас в боте {buyers_count} человек ищут квартиру!",
        reply_markup=keyboard
    )


@dp.message(F.text == "💼 Войти в режим продавца")
async def buyer_switch_to_seller(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if user:
        user.role = UserRole.SELLER
        db.commit()
    
    buyers_count = db.query(User).filter(User.role == UserRole.BUYER).count()
    db.close()
    
    keyboard = get_seller_menu()
    
    await message.answer(
        f"💼 Вы теперь в режиме продавца!\n\n"
        f"🔥 Прямо сейчас в боте {buyers_count} человек ищут квартиру!",
        reply_markup=keyboard
    )


@dp.message(F.text == "❤️ Лайки")
async def buyer_likes(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    likes = db.query(Like).filter(Like.user_id == user.id).order_by(Like.created_at.desc()).all()
    
    if not likes:
        db.close()
        await message.answer("Вы еще не лайкнули ни одной квартиры.", reply_markup=get_buyer_profile_menu())
        return
    
    await message.answer(f"❤️ <b>Ваши лайки ({len(likes)})</b>", reply_markup=get_buyer_profile_menu(), parse_mode="HTML")
    
    for like in likes[:10]:
        prop = db.query(Property).filter(Property.id == like.property_id).first()
        
        if prop:
            status_emoji = "🟢" if like.is_matched else "⏳"
            status_text = "Мэтч!" if like.is_matched else "Ожидание"
            type_name = "Продажа" if prop.property_type == PropertyType.SALE else "Аренда"
            
            contact_phone = prop.phone
            if not contact_phone:
                owner = db.query(User).filter(User.id == prop.owner_id).first()
                contact_phone = owner.phone if owner else "Не указан"
            
            text = f"{status_emoji} <b>{status_text}</b>  •  {type_name}\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n\n"
            text += f"💰 <b>${prop.price:,}</b>\n\n"
            
            if prop.district:
                text += f"📍 {prop.district}\n"
            if prop.rooms:
                text += f"🚪 {prop.rooms} комн.\n"
            if prop.area:
                text += f"📐 {prop.area} м²\n"
            if prop.floor and prop.total_floors:
                text += f"🏢 {prop.floor}/{prop.total_floors} этаж\n"
            
            extras = []
            if prop.building_type:
                extras.append(prop.building_type)
            if prop.renovation:
                extras.append(prop.renovation)
            if prop.has_furniture:
                extras.append("с мебелью")
            if extras:
                text += f"\n🏠 {' • '.join(extras)}\n"
            
            text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
            text += f"📞 <b><u>Контакт: {contact_phone}</u></b>\n"
            
            photos = [p for p in (prop.photos.split(",") if prop.photos else []) if p]
            
            if photos:
                try:
                    await message.answer_photo(photo=photos[0], caption=text, parse_mode="HTML")
                except:
                    await message.answer(text, parse_mode="HTML")
            else:
                await message.answer(text, parse_mode="HTML")
    
    db.close()


@dp.message(F.text == "💬 Переписка")
async def buyer_messages(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    matches = db.query(Like).filter(
        Like.user_id == user.id,
        Like.is_matched == True
    ).order_by(Like.created_at.desc()).all()
    db.close()
    
    if not matches:
        await message.answer(
            "💬 У вас пока нет контактов.\n\n"
            "Лайкайте квартиры и ждите, когда продавец откроет контакт!",
            reply_markup=get_buyer_profile_menu()
        )
        return
    
    text = f"💬 Ваши контакты ({len(matches)}):\n\n"
    
    for match in matches[:20]:
        db = SessionLocal()
        prop = db.query(Property).filter(Property.id == match.property_id).first()
        if prop:
            seller = db.query(User).filter(User.id == prop.owner_id).first()
            text += (
                f"📍 {prop.district or 'Объект'}\n"
                f"   {prop.rooms} комн. | ${prop.price:,}\n"
                f"   📞 {seller.phone if seller else 'Не указан'}\n\n"
            )
        db.close()
    
    await message.answer(text, reply_markup=get_buyer_profile_menu())


@dp.message(F.text == "⬅️ Назад")
async def buyer_profile_back(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    db.close()
    
    if user and user.role == UserRole.BUYER:
        keyboard = get_buyer_menu()
        await message.answer("🏠 Главное меню", reply_markup=keyboard)
    else:
        keyboard = get_seller_menu()
        await message.answer("🏠 Главное меню", reply_markup=keyboard)


@dp.message(F.text == "💳 Тарифы")
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


@dp.message(F.text == "❤️ Мои лайки")
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
                f"   {prop.rooms} комн. | ${prop.price:,}\n\n"
            )
    
    await message.answer(text)


class SearchSettingsStates(StatesGroup):
    deal_type = State()
    prop_type = State()
    rooms = State()
    district = State()
    budget = State()


@dp.message(F.text == "⚙️ Настройки поиска")
async def search_settings(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Купить"), KeyboardButton(text="🔑 Снять в аренду")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("⚙️ Изменить параметры поиска\n\n🏷 Что вас интересует?", reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.deal_type)


@dp.message(F.text == "⬅️ Назад", SearchSettingsStates.deal_type)
async def settings_back_to_menu(message: types.Message, state: FSMContext):
    await state.clear()
    keyboard = get_buyer_menu()
    await message.answer("Вы вернулись в главное меню", reply_markup=keyboard)


@dp.message(SearchSettingsStates.deal_type)
async def settings_deal_selected(message: types.Message, state: FSMContext):
    if message.text == "🏠 Купить":
        deal_type = "buy"
    elif message.text == "🔑 Снять в аренду":
        deal_type = "rent"
    else:
        return
    
    await state.update_data(search_deal_type=deal_type)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏢 Квартира")],
            [KeyboardButton(text="🏡 Дом / Участок")],
            [KeyboardButton(text="🏪 Коммерческая")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🏢 Выберите тип недвижимости:", reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.prop_type)


@dp.message(F.text == "⬅️ Назад", SearchSettingsStates.prop_type)
async def settings_back_to_deal(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Купить"), KeyboardButton(text="🔑 Снять в аренду")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🏷 Что вас интересует?", reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.deal_type)


@dp.message(SearchSettingsStates.prop_type)
async def settings_proptype_selected(message: types.Message, state: FSMContext):
    prop_types = {
        "🏢 Квартира": "apartment",
        "🏡 Дом / Участок": "house",
        "🏪 Коммерческая": "commercial"
    }
    prop_type = prop_types.get(message.text)
    if not prop_type:
        return
    
    await state.update_data(search_prop_type=prop_type)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2"), KeyboardButton(text="3")],
            [KeyboardButton(text="4+"), KeyboardButton(text="Студия")],
            [KeyboardButton(text="Любое")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🚪 Выберите количество комнат:", reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.rooms)


@dp.message(F.text == "⬅️ Назад", SearchSettingsStates.rooms)
async def settings_back_to_proptype(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏢 Квартира")],
            [KeyboardButton(text="🏡 Дом / Участок")],
            [KeyboardButton(text="🏪 Коммерческая")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🏢 Выберите тип недвижимости:", reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.prop_type)


@dp.message(SearchSettingsStates.rooms)
async def settings_rooms_selected(message: types.Message, state: FSMContext):
    rooms_map = {"1": "1", "2": "2", "3": "3", "4+": "4", "студия": "studio", "любое": "any"}
    rooms = rooms_map.get(message.text.lower())
    if not rooms:
        return
    
    await state.update_data(search_rooms=rooms)
    
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
    keyboard_buttons.append([KeyboardButton(text="Любой район")])
    keyboard_buttons.append([KeyboardButton(text="⬅️ Назад")])
    
    keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
    await message.answer("📍 Выберите район:", reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.district)


@dp.message(F.text == "⬅️ Назад", SearchSettingsStates.district)
async def settings_back_to_rooms(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2"), KeyboardButton(text="3")],
            [KeyboardButton(text="4+"), KeyboardButton(text="Студия")],
            [KeyboardButton(text="Любое")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🚪 Выберите количество комнат:", reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.rooms)


@dp.message(SearchSettingsStates.district)
async def settings_district_selected(message: types.Message, state: FSMContext):
    district = message.text if message.text != "Любой район" else "Любой"
    await state.update_data(search_district=district)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True
    )
    await message.answer("💰 Введите максимальный бюджет в долларах:\n\n(например: 50000)", reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.budget)


@dp.message(F.text == "⬅️ Назад", SearchSettingsStates.budget)
async def settings_back_to_district(message: types.Message, state: FSMContext):
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
    keyboard_buttons.append([KeyboardButton(text="Любой район")])
    keyboard_buttons.append([KeyboardButton(text="⬅️ Назад")])
    
    keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
    await message.answer("📍 Выберите район:", reply_markup=keyboard)
    await state.set_state(SearchSettingsStates.district)


@dp.message(SearchSettingsStates.budget)
async def settings_budget_entered(message: types.Message, state: FSMContext):
    budget = validate_number(message.text)
    if budget is None or budget <= 0:
        await message.answer("❌ Введите корректный бюджет числом")
        return
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    data = await state.get_data()
    deal_type = data.get("search_deal_type", "buy")
    prop_type = data.get("search_prop_type", "apartment")
    rooms = data.get("search_rooms", "any")
    district = data.get("search_district", "Любой")
    
    user.search_budget_max = int(budget)
    user.search_rooms = rooms
    user.search_district = district
    user.search_payment_type = f"{deal_type}_{prop_type}"
    db.commit()
    db.close()
    
    await state.clear()
    
    deal_names = {"buy": "Покупка", "rent": "Аренда"}
    prop_names = {"apartment": "Квартира", "house": "Дом/Участок", "commercial": "Коммерческая"}
    
    keyboard = get_buyer_menu()
    
    await message.answer(
        f"✅ Настройки обновлены!\n\n"
        f"🏷 Тип: {deal_names.get(deal_type, deal_type)} — {prop_names.get(prop_type, prop_type)}\n"
        f"🚪 Комнаты: {rooms if rooms != 'any' else 'Любые'}\n"
        f"📍 Район: {district}\n"
        f"💰 Бюджет: до ${int(budget):,}",
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
                                f"💰 ${prop.price:,}\n\n"
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
                                f"💰 ${prop.price:,}\n\n"
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
