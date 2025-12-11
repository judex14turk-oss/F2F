import asyncio
import os
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
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
    buyer_district = State()
    buyer_budget = State()
    buyer_payment = State()
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


def get_tariff_limits(tariff: TariffType):
    limits = {
        TariffType.FREE: {"properties": 2, "daily_offers": 0},
        TariffType.AGENCY_START: {"properties": 20, "daily_offers": 10},
        TariffType.DEVELOPER_PRO: {"properties": 999, "daily_offers": 50},
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
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Я ищу недвижимость", callback_data="role_buyer")],
        [InlineKeyboardButton(text="💼 Я хочу продать/сдать", callback_data="role_seller")]
    ])
    
    await message.answer(
        "👋 Добро пожаловать в Real Estate Bot!\n\n"
        "Это \"Tinder для недвижимости\" — находите покупателей или квартиры одним свайпом.\n\n"
        "Выберите вашу роль:",
        reply_markup=keyboard
    )
    await state.set_state(RegistrationStates.choosing_role)


@dp.callback_query(F.data == "role_buyer")
async def process_buyer_role(callback: types.CallbackQuery, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    if user:
        user.role = UserRole.BUYER
        db.commit()
    db.close()
    
    await callback.message.edit_text(
        "🏠 Отлично! Давайте настроим ваши параметры поиска.\n\n"
        "Сколько комнат вам нужно?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="1", callback_data="rooms_1"),
                InlineKeyboardButton(text="2", callback_data="rooms_2"),
                InlineKeyboardButton(text="3", callback_data="rooms_3"),
            ],
            [
                InlineKeyboardButton(text="4+", callback_data="rooms_4"),
                InlineKeyboardButton(text="Студия", callback_data="rooms_studio"),
            ]
        ])
    )
    await state.set_state(RegistrationStates.buyer_rooms)


@dp.callback_query(F.data.startswith("rooms_"))
async def process_rooms(callback: types.CallbackQuery, state: FSMContext):
    rooms = callback.data.replace("rooms_", "")
    await state.update_data(rooms=rooms)
    
    db = SessionLocal()
    districts = db.query(District).all()
    db.close()
    
    keyboard_buttons = []
    row = []
    for district in districts:
        row.append(InlineKeyboardButton(text=district.name, callback_data=f"district_{district.id}"))
        if len(row) == 2:
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)
    keyboard_buttons.append([InlineKeyboardButton(text="Любой район", callback_data="district_any")])
    
    await callback.message.edit_text(
        "📍 Выберите район:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    )
    await state.set_state(RegistrationStates.buyer_district)


@dp.callback_query(F.data.startswith("district_"), RegistrationStates.buyer_district)
async def process_district(callback: types.CallbackQuery, state: FSMContext):
    district_id = callback.data.replace("district_", "")
    
    if district_id == "any":
        district_name = "Любой"
    else:
        db = SessionLocal()
        district = db.query(District).filter(District.id == int(district_id)).first()
        district_name = district.name if district else "Любой"
        db.close()
    
    await state.update_data(district=district_name)
    
    await callback.message.edit_text(
        "💰 Какой у вас бюджет (в USD)?\n\nВведите максимальную сумму цифрами:",
    )
    await state.set_state(RegistrationStates.buyer_budget)


@dp.message(RegistrationStates.buyer_budget)
async def process_budget(message: types.Message, state: FSMContext):
    budget = validate_number(message.text.replace("$", ""))
    if budget is None:
        await message.answer("❌ Пожалуйста, введите число цифрами (например: 50000)")
        return
    
    await state.update_data(budget=int(budget))
    
    await message.answer(
        "💳 Способ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💵 Наличные", callback_data="payment_cash")],
            [InlineKeyboardButton(text="🏦 Ипотека", callback_data="payment_mortgage")],
            [InlineKeyboardButton(text="📄 Рассрочка", callback_data="payment_installment")],
        ])
    )
    await state.set_state(RegistrationStates.buyer_payment)


@dp.callback_query(F.data.startswith("payment_"))
async def process_payment(callback: types.CallbackQuery, state: FSMContext):
    payment = callback.data.replace("payment_", "")
    data = await state.get_data()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    if user:
        user.search_rooms = data.get("rooms", "")
        user.search_district = data.get("district", "")
        user.search_budget_max = data.get("budget", 0)
        user.search_payment_type = payment
        db.commit()
    db.close()
    
    await state.clear()
    await show_buyer_menu(callback.message, callback.from_user.id)


async def show_buyer_menu(message, user_id):
    db = SessionLocal()
    properties_count = db.query(Property).filter(Property.status == PropertyStatus.ACTIVE).count()
    db.close()
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Смотреть квартиры")],
            [KeyboardButton(text="❤️ Мои лайки"), KeyboardButton(text="💬 Мэтчи")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="⚙️ Настройки поиска")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"✅ Регистрация завершена!\n\n"
        f"📊 Сейчас доступно {properties_count} квартир.\n\n"
        f"Нажмите '🏠 Смотреть квартиры', чтобы начать поиск!",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "role_seller")
async def process_seller_role(callback: types.CallbackQuery, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    if user:
        user.role = UserRole.SELLER
        db.commit()
    db.close()
    
    await callback.message.edit_text(
        "💼 Отлично! Выберите тип аккаунта:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Собственник", callback_data="seller_owner")],
            [InlineKeyboardButton(text="🔑 Риелтор", callback_data="seller_realtor")],
            [InlineKeyboardButton(text="🏗 Застройщик", callback_data="seller_developer")],
        ])
    )
    await state.set_state(RegistrationStates.seller_type)


@dp.callback_query(F.data.startswith("seller_"))
async def process_seller_type(callback: types.CallbackQuery, state: FSMContext):
    seller_type = callback.data.replace("seller_", "")
    type_map = {"owner": SellerType.OWNER, "realtor": SellerType.REALTOR, "developer": SellerType.DEVELOPER}
    await state.update_data(seller_type=type_map.get(seller_type, SellerType.OWNER))
    
    await callback.message.edit_text("🏢 Введите название компании или ваше имя:")
    await state.set_state(RegistrationStates.seller_company)


@dp.message(RegistrationStates.seller_company)
async def process_company_name(message: types.Message, state: FSMContext):
    await state.update_data(company_name=message.text)
    await message.answer("👤 Введите имя менеджера (кто будет отвечать на звонки):")
    await state.set_state(RegistrationStates.seller_manager)


@dp.message(RegistrationStates.seller_manager)
async def process_manager_name(message: types.Message, state: FSMContext):
    await state.update_data(manager_name=message.text)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await message.answer("📱 Поделитесь вашим номером телефона:", reply_markup=keyboard)
    await state.set_state(RegistrationStates.seller_phone)


@dp.message(RegistrationStates.seller_phone)
async def process_phone(message: types.Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
    else:
        phone = message.text
    
    data = await state.get_data()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    if user:
        user.seller_type = data.get("seller_type", SellerType.OWNER)
        user.company_name = data.get("company_name", "")
        user.manager_name = data.get("manager_name", "")
        user.phone = phone
        user.tariff = TariffType.FREE
        db.commit()
    
    buyers_count = db.query(User).filter(User.role == UserRole.BUYER).count()
    db.close()
    
    await state.clear()
    await show_seller_menu(message, message.from_user.id, buyers_count)


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
        TariffType.FREE: "Бесплатный",
        TariffType.AGENCY_START: "Агентство Start",
        TariffType.DEVELOPER_PRO: "Застройщик PRO"
    }
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить объект")],
            [KeyboardButton(text="🏢 Мои объекты"), KeyboardButton(text="🎯 Найти покупателя")],
            [KeyboardButton(text="❤️ Меня лайкнули"), KeyboardButton(text="💬 Сделки")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="💳 Тарифы")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"✅ Регистрация завершена!\n\n"
        f"🔥 Прямо сейчас в боте {buyers_count} человек ищут квартиру!\n\n"
        f"📊 Ваша статистика:\n"
        f"👁 Просмотров: {total_views}\n"
        f"❤️ Лайков: {total_likes}\n"
        f"🤝 Мэтчей: {matches_count}\n"
        f"💰 Тариф: {tariff_names.get(user.tariff, 'Бесплатный')}",
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
    
    limits = get_tariff_limits(user.tariff)
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
    data = await state.get_data()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    
    photos_str = ",".join(data.get("photos", []))
    
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
    prop_id = prop.id
    db.close()
    
    type_name = "Продажа" if data.get("property_type") == PropertyType.SALE else "Аренда"
    furniture = "Да" if data.get("has_furniture") else "Нет"
    
    summary = (
        f"✅ Объявление добавлено!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 ХАРАКТЕРИСТИКИ:\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
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
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    if data.get("description"):
        summary += f"📝 Описание:\n{data.get('description')}\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    photos_list = data.get("photos", [])
    summary += f"📸 Фото: {len(photos_list)} шт.\n"
    
    await state.clear()
    
    await callback.message.edit_text(summary)
    
    if photos_list:
        from aiogram.types import InputMediaPhoto
        media_group = [InputMediaPhoto(media=photo_id) for photo_id in photos_list]
        await callback.message.answer_media_group(media_group)
    
    buyers_count = get_active_buyers_count(
        rooms=data.get("rooms"),
        district=data.get("district"),
        budget_max=data.get("price")
    )
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить объект")],
            [KeyboardButton(text="🏢 Мои объекты"), KeyboardButton(text="🎯 Найти покупателя")],
            [KeyboardButton(text="❤️ Меня лайкнули"), KeyboardButton(text="💬 Сделки")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="💳 Тарифы")]
        ],
        resize_keyboard=True
    )
    
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
    
    query = db.query(Property).filter(Property.status == PropertyStatus.ACTIVE)
    if liked_ids:
        query = query.filter(Property.id.notin_(liked_ids))
    properties = query.order_by(Property.created_at.desc()).all()
    
    db.close()
    
    if not properties:
        await message.answer("😔 Пока нет новых квартир. Попробуйте позже!")
        return
    
    await state.update_data(properties=[p.id for p in properties], current_index=0)
    await show_property_card(message, properties[0].id)
    await state.set_state(SearchStates.viewing_properties)


async def show_property_card(message, property_id):
    db = SessionLocal()
    prop = db.query(Property).filter(Property.id == property_id).first()
    
    if not prop:
        await message.answer("Объект не найден")
        db.close()
        return
    
    prop.views_count += 1
    db.commit()
    
    type_emoji = "🏷" if prop.property_type == PropertyType.SALE else "🔑"
    type_name = "Продажа" if prop.property_type == PropertyType.SALE else "Аренда"
    furniture = "Да" if prop.has_furniture else "Нет"
    
    text = (
        f"{type_emoji} {type_name}\n\n"
        f"📍 {prop.district or 'Район не указан'}\n"
        f"🚪 {prop.rooms} комн. | 📐 {prop.area} м²\n"
        f"🏢 Этаж {prop.floor}/{prop.total_floors}\n"
        f"🏠 {prop.building_type or ''}\n"
        f"🔨 {prop.renovation or ''}\n"
        f"🛋 Мебель: {furniture}\n"
        f"🚪 Комнаты: {prop.room_type or ''}\n"
        f"🚿 Санузел: {prop.bathroom_type or ''}\n\n"
        f"💰 ${prop.price:,}\n"
    )
    
    if prop.description:
        text += f"\n📝 {prop.description}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ Пропустить", callback_data=f"skip_{prop.id}"),
            InlineKeyboardButton(text="❤️ Нравится", callback_data=f"like_{prop.id}")
        ]
    ])
    
    photos = prop.photos.split(",") if prop.photos else []
    
    db.close()
    
    if photos and photos[0]:
        from aiogram.types import InputMediaPhoto
        media_group = [InputMediaPhoto(media=photo_id) for photo_id in photos if photo_id]
        if media_group:
            await message.answer_media_group(media_group)
    
    await message.answer(text, reply_markup=keyboard)


@dp.callback_query(F.data.startswith("like_"))
async def process_like(callback: types.CallbackQuery, state: FSMContext):
    property_id = int(callback.data.replace("like_", ""))
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
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
    
    await callback.answer("❤️ Лайк отправлен!")
    await show_next_property(callback, state)


@dp.callback_query(F.data.startswith("skip_"))
async def process_skip(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_next_property(callback, state)


async def show_next_property(callback, state):
    data = await state.get_data()
    properties = data.get("properties", [])
    current_index = data.get("current_index", 0) + 1
    
    if current_index >= len(properties):
        await callback.message.edit_text(
            "🎉 Вы просмотрели все доступные квартиры!\n\n"
            "Новые объекты появляются каждый день. Заходите позже!"
        )
        await state.clear()
        return
    
    await state.update_data(current_index=current_index)
    await callback.message.delete()
    await show_property_card(callback.message, properties[current_index])


@dp.message(F.text == "🏢 Мои объекты")
async def my_properties(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    properties = db.query(Property).filter(Property.owner_id == user.id).order_by(Property.created_at.desc()).all()
    db.close()
    
    if not properties:
        await message.answer("У вас пока нет объектов. Нажмите '➕ Добавить объект'!")
        return
    
    text = "🏢 Ваши объекты:\n\n"
    
    status_emoji = {
        PropertyStatus.ACTIVE: "🟢",
        PropertyStatus.MODERATION: "🟡",
        PropertyStatus.ARCHIVE: "⚫"
    }
    
    for prop in properties:
        emoji = status_emoji.get(prop.status, "⚪")
        type_str = "Продажа" if prop.property_type == PropertyType.SALE else "Аренда"
        text += (
            f"{emoji} {prop.district or 'Объект'}\n"
            f"   {type_str} | {prop.rooms} комн. | ${prop.price:,}\n"
            f"   👁 {prop.views_count} | ❤️ {prop.likes_count}\n\n"
        )
    
    await message.answer(text)


@dp.message(F.text == "❤️ Меня лайкнули")
async def likes_received(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    likes = db.query(Like).filter(
        Like.property_owner_id == user.id,
        Like.is_matched == False
    ).order_by(Like.created_at.desc()).all()
    db.close()
    
    if not likes:
        await message.answer("Пока нет новых лайков. Добавьте больше объектов!")
        return
    
    text = "❤️ Вас лайкнули:\n\n"
    
    keyboard_buttons = []
    for like in likes[:10]:
        db = SessionLocal()
        buyer = db.query(User).filter(User.id == like.user_id).first()
        prop = db.query(Property).filter(Property.id == like.property_id).first()
        db.close()
        
        if buyer and prop:
            name = buyer.first_name or "Покупатель"
            budget = f"до ${buyer.search_budget_max:,}" if buyer.search_budget_max else ""
            text += (
                f"👤 {name}\n"
                f"   Интересуется: {prop.district} (${prop.price:,})\n"
                f"   Бюджет: {budget}\n\n"
            )
            keyboard_buttons.append([
                InlineKeyboardButton(text=f"🤝 Открыть контакт {name}", callback_data=f"match_{like.id}")
            ])
    
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
    
    db.close()
    
    if not matches:
        await message.answer("Пока нет сделок. Они появятся после мэтчей!")
        return
    
    text = "💬 Ваши сделки:\n\n"
    
    for match in matches[:20]:
        db = SessionLocal()
        buyer = db.query(User).filter(User.id == match.buyer_id).first()
        seller = db.query(User).filter(User.id == match.seller_id).first()
        prop = db.query(Property).filter(Property.id == match.property_id).first()
        db.close()
        
        if user.role == UserRole.SELLER:
            contact = buyer
        else:
            contact = seller
        
        text += (
            f"👤 {contact.first_name or 'Контакт'}\n"
            f"📍 {prop.district if prop else ''} | ${prop.price:,} if prop else ''\n"
            f"📞 {contact.phone or 'Нет телефона'}\n"
            f"📅 {match.created_at.strftime('%d.%m.%Y')}\n"
        )
        if match.note:
            text += f"📝 {match.note}\n"
        text += "\n"
    
    await message.answer(text)


@dp.message(F.text == "🎯 Найти покупателя")
async def find_buyers(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if user.role != UserRole.SELLER:
        await message.answer("Эта функция доступна только для продавцов.")
        db.close()
        return
    
    limits = get_tariff_limits(user.tariff)
    if limits["daily_offers"] == 0:
        await message.answer(
            "⚠️ В бесплатном тарифе нельзя писать первым в базе спроса.\n\n"
            "Перейдите на тариф 'Агентство Start' или выше!"
        )
        db.close()
        return
    
    buyers = db.query(User).filter(
        User.role == UserRole.BUYER,
        User.search_budget_max > 0
    ).order_by(User.created_at.desc()).limit(10).all()
    db.close()
    
    if not buyers:
        await message.answer("Пока нет активных покупателей.")
        return
    
    text = "🎯 Активные покупатели:\n\n"
    
    keyboard_buttons = []
    for buyer in buyers:
        rooms = buyer.search_rooms or "Любые"
        district = buyer.search_district or "Любой район"
        budget = buyer.search_budget_max or 0
        payment = {"cash": "Наличные", "mortgage": "Ипотека", "installment": "Рассрочка"}.get(buyer.search_payment_type, "")
        
        text += (
            f"👤 {buyer.first_name or 'Покупатель'}\n"
            f"   🚪 {rooms} комн. | 📍 {district}\n"
            f"   💰 до ${budget:,} | {payment}\n\n"
        )
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"📤 Предложить {buyer.first_name or 'покупателю'}", callback_data=f"offer_{buyer.id}")
        ])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons))


@dp.callback_query(F.data.startswith("offer_"))
async def send_offer(callback: types.CallbackQuery):
    buyer_id = int(callback.data.replace("offer_", ""))
    
    db = SessionLocal()
    seller = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    
    limits = get_tariff_limits(seller.tariff)
    
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
        type_names = {
            SellerType.OWNER: "Собственник",
            SellerType.REALTOR: "Риелтор",
            SellerType.DEVELOPER: "Застройщик"
        }
        tariff_names = {
            TariffType.FREE: "Бесплатный",
            TariffType.AGENCY_START: "Агентство Start",
            TariffType.DEVELOPER_PRO: "Застройщик PRO"
        }
        
        text = (
            f"👤 Ваш профиль\n\n"
            f"📋 Тип: {type_names.get(user.seller_type, 'Не указан')}\n"
            f"🏢 Компания: {user.company_name or 'Не указана'}\n"
            f"👤 Менеджер: {user.manager_name or 'Не указан'}\n"
            f"📞 Телефон: {user.phone or 'Не указан'}\n"
            f"💳 Тариф: {tariff_names.get(user.tariff, 'Бесплатный')}\n"
        )
    else:
        payment_names = {"cash": "Наличные", "mortgage": "Ипотека", "installment": "Рассрочка"}
        budget = f"${user.search_budget_max:,}" if user.search_budget_max else "Не указан"
        
        text = (
            f"👤 Ваш профиль\n\n"
            f"🚪 Ищу: {user.search_rooms or 'Любые'} комн.\n"
            f"📍 Район: {user.search_district or 'Любой'}\n"
            f"💰 Бюджет: до {budget}\n"
            f"💳 Оплата: {payment_names.get(user.search_payment_type, 'Не указано')}\n"
        )
    
    await message.answer(text)


@dp.message(F.text == "💳 Тарифы")
async def tariffs(message: types.Message):
    text = (
        "💳 Тарифные планы\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🆓 Частник (Бесплатно)\n"
        "• 2 объекта\n"
        "• Нельзя писать первым\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🏢 Агентство Start (500,000 сум/мес)\n"
        "• 20 объектов\n"
        "• 10 предложений в день\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🏗 Застройщик PRO (2,000,000 сум/мес)\n"
        "• Безлимит объектов\n"
        "• 50 предложений в день\n\n"
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


@dp.message(F.text == "⚙️ Настройки поиска")
async def search_settings(message: types.Message, state: FSMContext):
    await message.answer(
        "⚙️ Изменить параметры поиска\n\nВыберите количество комнат:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="1", callback_data="rooms_1"),
                InlineKeyboardButton(text="2", callback_data="rooms_2"),
                InlineKeyboardButton(text="3", callback_data="rooms_3"),
            ],
            [
                InlineKeyboardButton(text="4+", callback_data="rooms_4"),
                InlineKeyboardButton(text="Студия", callback_data="rooms_studio"),
            ]
        ])
    )
    await state.set_state(RegistrationStates.buyer_rooms)


async def main():
    print("Initializing database...")
    init_db()
    
    print("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
