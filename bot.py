import asyncio
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
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
    complex_name = State()
    district = State()
    rooms = State()
    floor = State()
    area = State()
    price = State()
    description = State()
    photos = State()


class SearchStates(StatesGroup):
    viewing_properties = State()
    current_index = State()


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


# Start command
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


# Role selection
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


@dp.callback_query(F.data.startswith("district_"))
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
        "💰 Какой у вас бюджет (в USD)?\n\nВведите максимальную сумму:",
    )
    await state.set_state(RegistrationStates.buyer_budget)


@dp.message(RegistrationStates.buyer_budget)
async def process_budget(message: types.Message, state: FSMContext):
    try:
        budget = int(message.text.replace("$", "").replace(" ", "").replace(",", ""))
        await state.update_data(budget=budget)
        
        await message.answer(
            "💳 Способ оплаты:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💵 Наличные", callback_data="payment_cash")],
                [InlineKeyboardButton(text="🏦 Ипотека", callback_data="payment_mortgage")],
                [InlineKeyboardButton(text="📄 Рассрочка", callback_data="payment_installment")],
            ])
        )
        await state.set_state(RegistrationStates.buyer_payment)
    except ValueError:
        await message.answer("Пожалуйста, введите число (например: 50000)")


@dp.callback_query(F.data.startswith("payment_"))
async def process_payment(callback: types.CallbackQuery, state: FSMContext):
    payment = callback.data.replace("payment_", "")
    payment_names = {"cash": "Наличные", "mortgage": "Ипотека", "installment": "Рассрочка"}
    
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
    user = db.query(User).filter(User.telegram_id == user_id).first()
    properties_count = db.query(Property).filter(
        Property.status == PropertyStatus.ACTIVE
    ).count()
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
        f"📊 Сейчас доступно {properties_count} квартир по вашим параметрам.\n\n"
        f"Нажмите '🏠 Смотреть квартиры', чтобы начать поиск!",
        reply_markup=keyboard
    )


# Seller registration
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
    
    await callback.message.edit_text(
        "🏢 Введите название компании или ваше имя:"
    )
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
        user.trial_used = False
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
        f"🔥 Прямо сейчас в боте {buyers_count} человек ищут квартиру!\n"
        f"Разместите объект, чтобы их увидеть.\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 Ваша статистика:\n"
        f"👁 Просмотров: {total_views}\n"
        f"❤️ Лайков: {total_likes}\n"
        f"🤝 Мэтчей: {matches_count}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 Тариф: {tariff_names.get(user.tariff, 'Бесплатный')}",
        reply_markup=keyboard
    )


# Property viewing for buyers
@dp.message(F.text == "🏠 Смотреть квартиры")
async def view_properties(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    liked_ids = [l.property_id for l in db.query(Like).filter(Like.user_id == user.id).all()]
    
    properties = db.query(Property).filter(
        Property.status == PropertyStatus.ACTIVE,
        Property.id.notin_(liked_ids) if liked_ids else True
    ).order_by(Property.created_at.desc()).all()
    
    db.close()
    
    if not properties:
        await message.answer("😔 Пока нет новых квартир по вашим параметрам. Попробуйте позже!")
        return
    
    await state.update_data(properties=[p.id for p in properties], current_index=0)
    await show_property_card(message, properties[0])
    await state.set_state(SearchStates.viewing_properties)


async def show_property_card(message, property_obj):
    db = SessionLocal()
    prop = db.query(Property).filter(Property.id == property_obj.id if hasattr(property_obj, 'id') else Property.id == property_obj).first()
    
    if not prop:
        await message.answer("Объект не найден")
        db.close()
        return
    
    prop.views_count += 1
    db.commit()
    
    type_emoji = "🏷" if prop.property_type == PropertyType.SALE else "🔑"
    type_name = "Продажа" if prop.property_type == PropertyType.SALE else "Аренда"
    
    text = (
        f"{type_emoji} {type_name}\n\n"
        f"🏢 {prop.residential_complex or 'Не указан ЖК'}\n"
        f"📍 {prop.district or 'Район не указан'}\n"
        f"🚪 {prop.rooms} комн. | {prop.area} м² | Этаж {prop.floor}/{prop.total_floors}\n"
        f"💰 ${prop.price:,}\n\n"
        f"{prop.description or ''}"
    )
    
    db.close()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ Пропустить", callback_data=f"skip_{prop.id}"),
            InlineKeyboardButton(text="❤️ Нравится", callback_data=f"like_{prop.id}")
        ]
    ])
    
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
                        f"🏢 {prop.residential_complex or 'Объект'}\n"
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


# Add property for sellers
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
    
    await message.answer(
        "📝 Добавление нового объекта\n\nВыберите тип:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏷 Продажа", callback_data="proptype_sale")],
            [InlineKeyboardButton(text="🔑 Аренда", callback_data="proptype_rent")],
        ])
    )
    await state.set_state(PropertyStates.property_type)


@dp.callback_query(F.data.startswith("proptype_"))
async def process_property_type(callback: types.CallbackQuery, state: FSMContext):
    prop_type = PropertyType.SALE if callback.data == "proptype_sale" else PropertyType.RENT
    await state.update_data(property_type=prop_type)
    
    await callback.message.edit_text("🏢 Введите название ЖК (или 'Нет' если вторичка):")
    await state.set_state(PropertyStates.complex_name)


@dp.message(PropertyStates.complex_name)
async def process_complex_name(message: types.Message, state: FSMContext):
    complex_name = message.text if message.text.lower() != "нет" else None
    await state.update_data(complex_name=complex_name)
    
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
    
    await message.answer("📍 Выберите район:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons))
    await state.set_state(PropertyStates.district)


@dp.callback_query(F.data.startswith("propdistrict_"))
async def process_prop_district(callback: types.CallbackQuery, state: FSMContext):
    district_id = int(callback.data.replace("propdistrict_", ""))
    
    db = SessionLocal()
    district = db.query(District).filter(District.id == district_id).first()
    db.close()
    
    await state.update_data(district=district.name if district else "")
    
    await callback.message.edit_text("🚪 Сколько комнат?")
    await state.set_state(PropertyStates.rooms)


@dp.message(PropertyStates.rooms)
async def process_prop_rooms(message: types.Message, state: FSMContext):
    try:
        rooms = int(message.text)
        await state.update_data(rooms=rooms)
        await message.answer("🏢 Этаж и этажность (например: 5/9):")
        await state.set_state(PropertyStates.floor)
    except:
        await message.answer("Введите число комнат (например: 2)")


@dp.message(PropertyStates.floor)
async def process_prop_floor(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split("/")
        floor = int(parts[0])
        total_floors = int(parts[1]) if len(parts) > 1 else floor
        await state.update_data(floor=floor, total_floors=total_floors)
        await message.answer("📐 Площадь в м²:")
        await state.set_state(PropertyStates.area)
    except:
        await message.answer("Введите в формате: этаж/этажность (например: 5/9)")


@dp.message(PropertyStates.area)
async def process_prop_area(message: types.Message, state: FSMContext):
    try:
        area = float(message.text.replace(",", "."))
        await state.update_data(area=area)
        await message.answer("💰 Цена в USD:")
        await state.set_state(PropertyStates.price)
    except:
        await message.answer("Введите число (например: 65)")


@dp.message(PropertyStates.price)
async def process_prop_price(message: types.Message, state: FSMContext):
    try:
        price = int(message.text.replace("$", "").replace(" ", "").replace(",", ""))
        await state.update_data(price=price)
        await message.answer("📝 Описание (или 'Пропустить'):")
        await state.set_state(PropertyStates.description)
    except:
        await message.answer("Введите цену (например: 55000)")


@dp.message(PropertyStates.description)
async def process_prop_description(message: types.Message, state: FSMContext):
    description = message.text if message.text.lower() != "пропустить" else ""
    await state.update_data(description=description)
    
    data = await state.get_data()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    prop = Property(
        owner_id=user.id,
        property_type=data.get("property_type", PropertyType.SALE),
        residential_complex=data.get("complex_name"),
        district=data.get("district", ""),
        rooms=data.get("rooms", 1),
        floor=data.get("floor", 1),
        total_floors=data.get("total_floors", 9),
        area=data.get("area", 50),
        price=data.get("price", 0),
        description=description,
        status=PropertyStatus.ACTIVE
    )
    db.add(prop)
    db.commit()
    db.close()
    
    await state.clear()
    
    buyers_count = get_active_buyers_count(
        rooms=data.get("rooms"),
        district=data.get("district"),
        budget_max=data.get("price")
    )
    
    await message.answer(
        f"✅ Объект успешно добавлен!\n\n"
        f"📊 {buyers_count} покупателей ищут похожие квартиры.\n\n"
        f"Ваш объект уже виден им в ленте!",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="➕ Добавить объект")],
                [KeyboardButton(text="🏢 Мои объекты"), KeyboardButton(text="🎯 Найти покупателя")],
                [KeyboardButton(text="❤️ Меня лайкнули"), KeyboardButton(text="💬 Сделки")],
                [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="💳 Тарифы")]
            ],
            resize_keyboard=True
        )
    )


# My properties
@dp.message(F.text == "🏢 Мои объекты")
async def my_properties(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    properties = db.query(Property).filter(Property.owner_id == user.id).order_by(Property.created_at.desc()).all()
    db.close()
    
    if not properties:
        await message.answer("У вас пока нет объектов. Нажмите '➕ Добавить объект', чтобы разместить первый!")
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
            f"{emoji} {prop.residential_complex or 'Объект'}\n"
            f"   {type_str} | {prop.rooms} комн. | ${prop.price:,}\n"
            f"   👁 {prop.views_count} | ❤️ {prop.likes_count}\n\n"
        )
    
    await message.answer(text)


# Likes received
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
        await message.answer("Пока нет новых лайков. Добавьте больше объектов, чтобы привлечь покупателей!")
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
            text += (
                f"👤 {name}\n"
                f"   Интересуется: {prop.residential_complex or 'Объект'} (${prop.price:,})\n"
                f"   Бюджет: до ${buyer.search_budget_max:,}\n\n"
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
    buyer_info = f"{buyer.first_name or 'Покупатель'}"
    
    try:
        await bot.send_message(
            buyer.telegram_id,
            f"🎉 Отличные новости!\n\n"
            f"Владелец квартиры подтвердил интерес!\n\n"
            f"🏢 {prop.residential_complex or 'Объект'}\n"
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
        f"👤 Покупатель: {buyer_info}\n"
        f"📞 Контакт покупателя доступен в разделе 'Сделки'"
    )


# Deals/Matches
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
            f"🏢 {prop.residential_complex or 'Объект'} | ${prop.price:,}\n"
            f"📞 {contact.phone or 'Нет телефона'}\n"
            f"📅 {match.created_at.strftime('%d.%m.%Y')}\n"
            f"{'📝 ' + match.note if match.note else ''}\n\n"
        )
    
    await message.answer(text)


# Find buyers (for sellers)
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
            "Перейдите на тариф 'Агентство Start' или выше, чтобы активно искать покупателей!"
        )
        db.close()
        return
    
    buyers = db.query(User).filter(
        User.role == UserRole.BUYER,
        User.search_budget_max > 0
    ).order_by(User.created_at.desc()).limit(10).all()
    db.close()
    
    if not buyers:
        await message.answer("Пока нет активных покупателей в базе.")
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
        await callback.answer("У вас нет активных объектов для предложения!")
        return
    
    keyboard_buttons = []
    for prop in properties[:5]:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{prop.residential_complex or 'Объект'} - ${prop.price:,}",
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
            f"Продавец предлагает вам квартиру:\n\n"
            f"🏢 {prop.residential_complex or 'Объект'}\n"
            f"📍 {prop.district}\n"
            f"🚪 {prop.rooms} комн. | {prop.area} м²\n"
            f"💰 ${prop.price:,}\n\n"
            f"Интересно?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Интересно", callback_data=f"accept_offer_{offer.id}"),
                    InlineKeyboardButton(text="❌ Не интересно", callback_data=f"reject_offer_{offer.id}")
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
            f"🏢 {prop.residential_complex or 'Объект'}\n\n"
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


# Profile
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
        
        text = (
            f"👤 Ваш профиль\n\n"
            f"🚪 Ищу: {user.search_rooms or 'Любые'} комн.\n"
            f"📍 Район: {user.search_district or 'Любой'}\n"
            f"💰 Бюджет: до ${user.search_budget_max:,}\n"
            f"💳 Оплата: {payment_names.get(user.search_payment_type, 'Не указано')}\n"
        )
    
    await message.answer(text)


# Tariffs
@dp.message(F.text == "💳 Тарифы")
async def tariffs(message: types.Message):
    text = (
        "💳 Тарифные планы\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🆓 Частник (Бесплатно)\n"
        "• 2 объекта\n"
        "• Нельзя писать первым в базе спроса\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🏢 Агентство Start (500,000 сум/мес)\n"
        "• 20 объектов\n"
        "• 10 предложений в день\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🏗 Застройщик PRO (2,000,000 сум/мес)\n"
        "• Безлимит объектов\n"
        "• 50 предложений в день\n"
        "• Выделение цветом\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Для оплаты обратитесь к @InvictumMurad"
    )
    
    await message.answer(text)


# My likes (for buyers)
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
                f"{status} {prop.residential_complex or 'Объект'}\n"
                f"   {prop.rooms} комн. | ${prop.price:,}\n\n"
            )
    
    await message.answer(text)


# Settings (for buyers)
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
