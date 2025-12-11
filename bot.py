import asyncio
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from models import SessionLocal, User, Property, Like, Match, Offer, District, ResidentialComplex
from models import UserRole, SellerType, TariffType, PropertyType, PropertyStatus, init_db

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'InvictumMurad')

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
    building_type = State()
    renovation = State()
    furniture = State()
    room_layout = State()
    bathroom = State()
    price = State()
    description = State()
    photos = State()


class SearchStates(StatesGroup):
    viewing_properties = State()
    current_index = State()


def get_tariff_limits(tariff: TariffType):
    limits = {
        TariffType.FREE: {"properties": 2, "daily_offers": 0},
        TariffType.AGENCY_START: {"properties": 20, "daily_offers": 10},
        TariffType.DEVELOPER_PRO: {"properties": 999, "daily_offers": 50},
    }
    return limits.get(tariff, limits[TariffType.FREE])


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
        "🏠 Отлично! Давайте настроим ваши параметры поиска.\n\nСколько комнат вам нужно?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="1", callback_data="brooms_1"),
                InlineKeyboardButton(text="2", callback_data="brooms_2"),
                InlineKeyboardButton(text="3", callback_data="brooms_3"),
            ],
            [
                InlineKeyboardButton(text="4", callback_data="brooms_4"),
                InlineKeyboardButton(text="5+", callback_data="brooms_5"),
                InlineKeyboardButton(text="Студия", callback_data="brooms_studio"),
            ]
        ])
    )
    await state.set_state(RegistrationStates.buyer_rooms)


@dp.callback_query(F.data.startswith("brooms_"))
async def process_buyer_rooms(callback: types.CallbackQuery, state: FSMContext):
    rooms = callback.data.replace("brooms_", "")
    await state.update_data(rooms=rooms)
    
    db = SessionLocal()
    districts = db.query(District).all()
    db.close()
    
    keyboard_buttons = []
    row = []
    for district in districts:
        row.append(InlineKeyboardButton(text=district.name, callback_data=f"bdistrict_{district.id}"))
        if len(row) == 2:
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)
    keyboard_buttons.append([InlineKeyboardButton(text="Любой район", callback_data="bdistrict_any")])
    
    await callback.message.edit_text("📍 Выберите район:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons))
    await state.set_state(RegistrationStates.buyer_district)


@dp.callback_query(F.data.startswith("bdistrict_"))
async def process_buyer_district(callback: types.CallbackQuery, state: FSMContext):
    district_id = callback.data.replace("bdistrict_", "")
    
    if district_id == "any":
        district_name = "Любой"
    else:
        db = SessionLocal()
        district = db.query(District).filter(District.id == int(district_id)).first()
        district_name = district.name if district else "Любой"
        db.close()
    
    await state.update_data(district=district_name)
    
    await callback.message.edit_text(
        "💰 Какой у вас бюджет (в USD)?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="До $30,000", callback_data="bbudget_30000")],
            [InlineKeyboardButton(text="До $50,000", callback_data="bbudget_50000")],
            [InlineKeyboardButton(text="До $70,000", callback_data="bbudget_70000")],
            [InlineKeyboardButton(text="До $100,000", callback_data="bbudget_100000")],
            [InlineKeyboardButton(text="До $150,000", callback_data="bbudget_150000")],
            [InlineKeyboardButton(text="$150,000+", callback_data="bbudget_500000")],
        ])
    )
    await state.set_state(RegistrationStates.buyer_budget)


@dp.callback_query(F.data.startswith("bbudget_"))
async def process_buyer_budget(callback: types.CallbackQuery, state: FSMContext):
    budget = int(callback.data.replace("bbudget_", ""))
    await state.update_data(budget=budget)
    
    await callback.message.edit_text(
        "💳 Способ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💵 Наличные", callback_data="bpayment_cash")],
            [InlineKeyboardButton(text="🏦 Ипотека", callback_data="bpayment_mortgage")],
            [InlineKeyboardButton(text="📄 Рассрочка", callback_data="bpayment_installment")],
        ])
    )
    await state.set_state(RegistrationStates.buyer_payment)


@dp.callback_query(F.data.startswith("bpayment_"))
async def process_buyer_payment(callback: types.CallbackQuery, state: FSMContext):
    payment = callback.data.replace("bpayment_", "")
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
        "💼 Выберите тип аккаунта:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Собственник", callback_data="stype_owner")],
            [InlineKeyboardButton(text="🔑 Риелтор", callback_data="stype_realtor")],
            [InlineKeyboardButton(text="🏗 Застройщик", callback_data="stype_developer")],
        ])
    )
    await state.set_state(RegistrationStates.seller_type)


@dp.callback_query(F.data.startswith("stype_"))
async def process_seller_type(callback: types.CallbackQuery, state: FSMContext):
    seller_type = callback.data.replace("stype_", "")
    type_map = {"owner": SellerType.OWNER, "realtor": SellerType.REALTOR, "developer": SellerType.DEVELOPER}
    await state.update_data(seller_type=type_map.get(seller_type, SellerType.OWNER))
    
    await callback.message.edit_text("🏢 Введите название компании или ваше имя:")
    await state.set_state(RegistrationStates.seller_company)


@dp.message(RegistrationStates.seller_company)
async def process_company_name(message: types.Message, state: FSMContext):
    await state.update_data(company_name=message.text)
    await message.answer("👤 Введите имя менеджера:")
    await state.set_state(RegistrationStates.seller_manager)


@dp.message(RegistrationStates.seller_manager)
async def process_manager_name(message: types.Message, state: FSMContext):
    await state.update_data(manager_name=message.text)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("📱 Поделитесь номером телефона:", reply_markup=keyboard)
    await state.set_state(RegistrationStates.seller_phone)


@dp.message(RegistrationStates.seller_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
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
        f"✅ Добро пожаловать!\n\n"
        f"🔥 Прямо сейчас в боте {buyers_count} покупателей!\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 Ваша статистика:\n"
        f"👁 Просмотров: {total_views}\n"
        f"❤️ Лайков: {total_likes}\n"
        f"🤝 Мэтчей: {matches_count}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 Тариф: {tariff_names.get(user.tariff, 'Бесплатный')}",
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
    
    type_name = "🏷 Продажа" if prop.property_type == PropertyType.SALE else "🔑 Аренда"
    
    building_types = {"monolith": "Монолит", "panel": "Панель", "brick": "Кирпич"}
    renovation_types = {"euro": "Евроремонт", "cosmetic": "Косметический", "none": "Без ремонта", "rough": "Черновая"}
    furniture_types = {"yes": "С мебелью", "no": "Без мебели"}
    layout_types = {"separate": "Раздельные", "adjacent": "Смежные"}
    bathroom_types = {"separate": "Раздельный", "combined": "Совмещённый"}
    
    details = []
    if prop.building_type:
        details.append(f"🏗 {building_types.get(prop.building_type, prop.building_type)}")
    if prop.renovation:
        details.append(f"🔨 {renovation_types.get(prop.renovation, prop.renovation)}")
    if prop.furniture:
        details.append(f"🛋 {furniture_types.get(prop.furniture, prop.furniture)}")
    if prop.room_layout:
        details.append(f"🚪 Комнаты: {layout_types.get(prop.room_layout, prop.room_layout)}")
    if prop.bathroom:
        details.append(f"🚿 Санузел: {bathroom_types.get(prop.bathroom, prop.bathroom)}")
    
    text = (
        f"{type_name}\n\n"
        f"📍 {prop.district or 'Район не указан'}\n"
        f"🚪 {prop.rooms} комн. | Этаж {prop.floor}/{prop.total_floors}\n"
        f"💰 ${prop.price:,}\n\n"
    )
    
    if details:
        text += "\n".join(details) + "\n\n"
    
    if prop.description:
        text += f"📝 {prop.description}\n"
    
    db.close()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ Пропустить", callback_data=f"skip_{prop.id}"),
            InlineKeyboardButton(text="❤️ Нравится", callback_data=f"like_{prop.id}")
        ]
    ])
    
    if prop.photos:
        photo_ids = prop.photos.split(",")
        if len(photo_ids) > 0 and photo_ids[0]:
            try:
                await message.answer_photo(photo=photo_ids[0], caption=text, reply_markup=keyboard)
                return
            except:
                pass
    
    await message.answer(text, reply_markup=keyboard)


@dp.callback_query(F.data.startswith("like_"))
async def process_like(callback: types.CallbackQuery, state: FSMContext):
    property_id = int(callback.data.replace("like_", ""))
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    prop = db.query(Property).filter(Property.id == property_id).first()
    
    if user and prop:
        existing = db.query(Like).filter(Like.user_id == user.id, Like.property_id == property_id).first()
        if not existing:
            like = Like(user_id=user.id, property_id=property_id, property_owner_id=prop.owner_id)
            db.add(like)
            prop.likes_count += 1
            db.commit()
            
            owner = db.query(User).filter(User.id == prop.owner_id).first()
            if owner:
                try:
                    await bot.send_message(
                        owner.telegram_id,
                        f"❤️ Новый лайк!\n\nПользователь заинтересовался вашим объектом:\n📍 {prop.district}\n💰 ${prop.price:,}"
                    )
                except:
                    pass
    db.close()
    
    await callback.answer("❤️ Лайк!")
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
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer("🎉 Вы просмотрели все квартиры! Заходите позже.")
        await state.clear()
        return
    
    await state.update_data(current_index=current_index)
    try:
        await callback.message.delete()
    except:
        pass
    await show_property_card(callback.message, properties[current_index])


@dp.message(F.text == "➕ Добавить объект")
async def add_property_start(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if not user or user.role != UserRole.SELLER:
        await message.answer("Эта функция доступна только для продавцов.")
        db.close()
        return
    
    limits = get_tariff_limits(user.tariff)
    current_count = db.query(Property).filter(Property.owner_id == user.id, Property.status != PropertyStatus.ARCHIVE).count()
    db.close()
    
    if current_count >= limits["properties"]:
        await message.answer(f"⚠️ Лимит объектов ({limits['properties']}) достигнут. Обновите тариф!")
        return
    
    await state.update_data(photos=[])
    
    await message.answer(
        "📝 Добавление объекта\n\nВыберите тип сделки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏷 Продажа", callback_data="ptype_sale")],
            [InlineKeyboardButton(text="🔑 Аренда", callback_data="ptype_rent")],
        ])
    )
    await state.set_state(PropertyStates.property_type)


@dp.callback_query(F.data.startswith("ptype_"))
async def prop_type(callback: types.CallbackQuery, state: FSMContext):
    prop_type = "sale" if callback.data == "ptype_sale" else "rent"
    await state.update_data(property_type=prop_type)
    
    db = SessionLocal()
    districts = db.query(District).all()
    db.close()
    
    buttons = []
    row = []
    for d in districts:
        row.append(InlineKeyboardButton(text=d.name, callback_data=f"pdistrict_{d.id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    await callback.message.edit_text("📍 Выберите район:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(PropertyStates.district)


@dp.callback_query(F.data.startswith("pdistrict_"))
async def prop_district(callback: types.CallbackQuery, state: FSMContext):
    district_id = int(callback.data.replace("pdistrict_", ""))
    db = SessionLocal()
    district = db.query(District).filter(District.id == district_id).first()
    db.close()
    
    await state.update_data(district=district.name if district else "")
    
    await callback.message.edit_text(
        "🚪 Количество комнат:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="1", callback_data="prooms_1"),
                InlineKeyboardButton(text="2", callback_data="prooms_2"),
                InlineKeyboardButton(text="3", callback_data="prooms_3"),
            ],
            [
                InlineKeyboardButton(text="4", callback_data="prooms_4"),
                InlineKeyboardButton(text="5", callback_data="prooms_5"),
                InlineKeyboardButton(text="6+", callback_data="prooms_6"),
            ]
        ])
    )
    await state.set_state(PropertyStates.rooms)


@dp.callback_query(F.data.startswith("prooms_"))
async def prop_rooms(callback: types.CallbackQuery, state: FSMContext):
    rooms = int(callback.data.replace("prooms_", ""))
    await state.update_data(rooms=rooms)
    
    buttons = []
    for i in range(1, 17, 4):
        row = []
        for j in range(4):
            floor = i + j
            if floor <= 16:
                row.append(InlineKeyboardButton(text=str(floor), callback_data=f"pfloor_{floor}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="17+", callback_data="pfloor_17")])
    
    await callback.message.edit_text("🏢 На каком этаже?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(PropertyStates.floor)


@dp.callback_query(F.data.startswith("pfloor_"))
async def prop_floor(callback: types.CallbackQuery, state: FSMContext):
    floor = int(callback.data.replace("pfloor_", ""))
    await state.update_data(floor=floor)
    
    buttons = []
    for i in range(5, 25, 4):
        row = []
        for j in range(4):
            floors = i + j
            if floors <= 24:
                row.append(InlineKeyboardButton(text=str(floors), callback_data=f"ptotal_{floors}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="25+", callback_data="ptotal_25")])
    
    await callback.message.edit_text("🏗 Этажность дома:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(PropertyStates.total_floors)


@dp.callback_query(F.data.startswith("ptotal_"))
async def prop_total_floors(callback: types.CallbackQuery, state: FSMContext):
    total = int(callback.data.replace("ptotal_", ""))
    await state.update_data(total_floors=total)
    
    await callback.message.edit_text(
        "🏗 Тип строения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧱 Монолит", callback_data="pbuild_monolith")],
            [InlineKeyboardButton(text="🏢 Панель", callback_data="pbuild_panel")],
            [InlineKeyboardButton(text="🧱 Кирпич", callback_data="pbuild_brick")],
        ])
    )
    await state.set_state(PropertyStates.building_type)


@dp.callback_query(F.data.startswith("pbuild_"))
async def prop_building(callback: types.CallbackQuery, state: FSMContext):
    build = callback.data.replace("pbuild_", "")
    await state.update_data(building_type=build)
    
    await callback.message.edit_text(
        "🔨 Ремонт:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✨ Евроремонт", callback_data="preno_euro")],
            [InlineKeyboardButton(text="🔧 Косметический", callback_data="preno_cosmetic")],
            [InlineKeyboardButton(text="📦 Без ремонта", callback_data="preno_none")],
            [InlineKeyboardButton(text="🏗 Черновая отделка", callback_data="preno_rough")],
        ])
    )
    await state.set_state(PropertyStates.renovation)


@dp.callback_query(F.data.startswith("preno_"))
async def prop_renovation(callback: types.CallbackQuery, state: FSMContext):
    reno = callback.data.replace("preno_", "")
    await state.update_data(renovation=reno)
    
    await callback.message.edit_text(
        "🛋 Мебель:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ С мебелью", callback_data="pfurn_yes")],
            [InlineKeyboardButton(text="❌ Без мебели", callback_data="pfurn_no")],
        ])
    )
    await state.set_state(PropertyStates.furniture)


@dp.callback_query(F.data.startswith("pfurn_"))
async def prop_furniture(callback: types.CallbackQuery, state: FSMContext):
    furn = callback.data.replace("pfurn_", "")
    await state.update_data(furniture=furn)
    
    await callback.message.edit_text(
        "🚪 Планировка комнат:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📐 Раздельные", callback_data="playout_separate")],
            [InlineKeyboardButton(text="🔗 Смежные", callback_data="playout_adjacent")],
        ])
    )
    await state.set_state(PropertyStates.room_layout)


@dp.callback_query(F.data.startswith("playout_"))
async def prop_layout(callback: types.CallbackQuery, state: FSMContext):
    layout = callback.data.replace("playout_", "")
    await state.update_data(room_layout=layout)
    
    await callback.message.edit_text(
        "🚿 Санузел:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📐 Раздельный", callback_data="pbath_separate")],
            [InlineKeyboardButton(text="🔗 Совмещённый", callback_data="pbath_combined")],
        ])
    )
    await state.set_state(PropertyStates.bathroom)


@dp.callback_query(F.data.startswith("pbath_"))
async def prop_bathroom(callback: types.CallbackQuery, state: FSMContext):
    bath = callback.data.replace("pbath_", "")
    await state.update_data(bathroom=bath)
    
    await callback.message.edit_text(
        "💰 Цена в USD:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="$30,000", callback_data="pprice_30000"),
                InlineKeyboardButton(text="$40,000", callback_data="pprice_40000"),
            ],
            [
                InlineKeyboardButton(text="$50,000", callback_data="pprice_50000"),
                InlineKeyboardButton(text="$60,000", callback_data="pprice_60000"),
            ],
            [
                InlineKeyboardButton(text="$70,000", callback_data="pprice_70000"),
                InlineKeyboardButton(text="$80,000", callback_data="pprice_80000"),
            ],
            [
                InlineKeyboardButton(text="$90,000", callback_data="pprice_90000"),
                InlineKeyboardButton(text="$100,000", callback_data="pprice_100000"),
            ],
            [
                InlineKeyboardButton(text="$120,000", callback_data="pprice_120000"),
                InlineKeyboardButton(text="$150,000", callback_data="pprice_150000"),
            ],
            [
                InlineKeyboardButton(text="$200,000", callback_data="pprice_200000"),
                InlineKeyboardButton(text="$300,000+", callback_data="pprice_300000"),
            ],
        ])
    )
    await state.set_state(PropertyStates.price)


@dp.callback_query(F.data.startswith("pprice_"))
async def prop_price(callback: types.CallbackQuery, state: FSMContext):
    price = int(callback.data.replace("pprice_", ""))
    await state.update_data(price=price)
    
    await callback.message.edit_text(
        "📝 Введите описание объекта (или отправьте 'Пропустить'):\n\n"
        "Например: Светлая квартира с видом на парк, рядом метро и школа."
    )
    await state.set_state(PropertyStates.description)


@dp.message(PropertyStates.description)
async def prop_description(message: types.Message, state: FSMContext):
    desc = "" if message.text.lower() == "пропустить" else message.text
    await state.update_data(description=desc)
    
    await message.answer(
        "📷 Отправьте фотографии объекта (до 10 шт.)\n\n"
        "Можете отправлять по одной или несколько сразу.\n"
        "Когда закончите, нажмите кнопку '✅ Готово'",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="photos_done")],
            [InlineKeyboardButton(text="⏭ Пропустить фото", callback_data="photos_skip")]
        ])
    )
    await state.set_state(PropertyStates.photos)


@dp.message(PropertyStates.photos, F.photo)
async def prop_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    
    if len(photos) >= 10:
        await message.answer("Максимум 10 фото! Нажмите '✅ Готово'")
        return
    
    photo_id = message.photo[-1].file_id
    photos.append(photo_id)
    await state.update_data(photos=photos)
    
    await message.answer(
        f"📷 Фото добавлено ({len(photos)}/10)\n\nОтправьте ещё или нажмите '✅ Готово'",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="photos_done")]
        ])
    )


@dp.callback_query(F.data == "photos_done")
async def photos_done(callback: types.CallbackQuery, state: FSMContext):
    await save_property(callback, state)


@dp.callback_query(F.data == "photos_skip")
async def photos_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(photos=[])
    await save_property(callback, state)


async def save_property(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    
    prop = Property(
        owner_id=user.id,
        property_type=PropertyType.SALE if data.get("property_type") == "sale" else PropertyType.RENT,
        district=data.get("district", ""),
        rooms=data.get("rooms", 1),
        floor=data.get("floor", 1),
        total_floors=data.get("total_floors", 9),
        building_type=data.get("building_type", ""),
        renovation=data.get("renovation", ""),
        furniture=data.get("furniture", ""),
        room_layout=data.get("room_layout", ""),
        bathroom=data.get("bathroom", ""),
        price=data.get("price", 0),
        description=data.get("description", ""),
        photos=",".join(data.get("photos", [])),
        status=PropertyStatus.ACTIVE
    )
    db.add(prop)
    db.commit()
    
    prop_id = prop.id
    db.close()
    
    await state.clear()
    
    type_name = "🏷 Продажа" if data.get("property_type") == "sale" else "🔑 Аренда"
    
    building_types = {"monolith": "Монолит", "panel": "Панель", "brick": "Кирпич"}
    renovation_types = {"euro": "Евроремонт", "cosmetic": "Косметический", "none": "Без ремонта", "rough": "Черновая"}
    furniture_types = {"yes": "С мебелью", "no": "Без мебели"}
    layout_types = {"separate": "Раздельные", "adjacent": "Смежные"}
    bathroom_types = {"separate": "Раздельный", "combined": "Совмещённый"}
    
    card_text = (
        f"✅ Объявление добавлено!\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{type_name}\n\n"
        f"📍 Район: {data.get('district', '-')}\n"
        f"🚪 Комнат: {data.get('rooms', '-')}\n"
        f"🏢 Этаж: {data.get('floor', '-')}/{data.get('total_floors', '-')}\n"
        f"🏗 Тип: {building_types.get(data.get('building_type', ''), '-')}\n"
        f"🔨 Ремонт: {renovation_types.get(data.get('renovation', ''), '-')}\n"
        f"🛋 Мебель: {furniture_types.get(data.get('furniture', ''), '-')}\n"
        f"🚪 Комнаты: {layout_types.get(data.get('room_layout', ''), '-')}\n"
        f"🚿 Санузел: {bathroom_types.get(data.get('bathroom', ''), '-')}\n"
        f"💰 Цена: ${data.get('price', 0):,}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
    )
    
    if data.get("description"):
        card_text += f"📝 {data.get('description')}\n"
    
    photos = data.get("photos", [])
    
    try:
        await callback.message.delete()
    except:
        pass
    
    if photos and len(photos) > 0:
        if len(photos) == 1:
            await callback.message.answer_photo(photo=photos[0], caption=card_text)
        else:
            media = [InputMediaPhoto(media=photos[0], caption=card_text)]
            for p in photos[1:10]:
                media.append(InputMediaPhoto(media=p))
            await callback.message.answer_media_group(media=media)
    else:
        await callback.message.answer(card_text)
    
    buyers = get_active_buyers_count(rooms=data.get("rooms"), district=data.get("district"), budget_max=data.get("price"))
    await callback.message.answer(f"📊 {buyers} покупателей ищут похожие квартиры!")


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
    status_emoji = {PropertyStatus.ACTIVE: "🟢", PropertyStatus.MODERATION: "🟡", PropertyStatus.ARCHIVE: "⚫"}
    
    for prop in properties:
        emoji = status_emoji.get(prop.status, "⚪")
        text += f"{emoji} {prop.district} | {prop.rooms} комн. | ${prop.price:,}\n   👁 {prop.views_count} | ❤️ {prop.likes_count}\n\n"
    
    await message.answer(text)


@dp.message(F.text == "❤️ Меня лайкнули")
async def likes_received(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    likes = db.query(Like).filter(Like.property_owner_id == user.id, Like.is_matched == False).order_by(Like.created_at.desc()).all()
    db.close()
    
    if not likes:
        await message.answer("Пока нет новых лайков.")
        return
    
    text = "❤️ Вас лайкнули:\n\n"
    buttons = []
    
    for like in likes[:10]:
        db = SessionLocal()
        buyer = db.query(User).filter(User.id == like.user_id).first()
        prop = db.query(Property).filter(Property.id == like.property_id).first()
        db.close()
        
        if buyer and prop:
            name = buyer.first_name or "Покупатель"
            text += f"👤 {name} → {prop.district} (${prop.price:,})\n"
            buttons.append([InlineKeyboardButton(text=f"🤝 Открыть контакт {name}", callback_data=f"match_{like.id}")])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


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
    
    match = Match(buyer_id=like.user_id, seller_id=like.property_owner_id, property_id=like.property_id)
    db.add(match)
    like.is_matched = True
    db.commit()
    
    try:
        await bot.send_message(
            buyer.telegram_id,
            f"🎉 Мэтч!\n\nВладелец подтвердил интерес!\n📍 {prop.district}\n💰 ${prop.price:,}\n\n📞 Контакт: {seller.phone or 'Нет'}\n👤 {seller.manager_name or seller.first_name}"
        )
    except:
        pass
    
    db.close()
    
    await callback.message.edit_text(f"✅ Мэтч создан!\n\n👤 {buyer.first_name or 'Покупатель'}\nКонтакт в разделе 'Сделки'")


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
        await message.answer("Пока нет сделок.")
        return
    
    text = "💬 Ваши сделки:\n\n"
    for match in matches[:20]:
        db = SessionLocal()
        buyer = db.query(User).filter(User.id == match.buyer_id).first()
        seller = db.query(User).filter(User.id == match.seller_id).first()
        prop = db.query(Property).filter(Property.id == match.property_id).first()
        db.close()
        
        contact = buyer if user.role == UserRole.SELLER else seller
        text += f"👤 {contact.first_name or 'Контакт'}\n📞 {contact.phone or 'Нет'}\n📍 {prop.district if prop else '-'} | ${prop.price:,}\n📅 {match.created_at.strftime('%d.%m.%Y')}\n\n"
    
    await message.answer(text)


@dp.message(F.text == "🎯 Найти покупателя")
async def find_buyers(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if user.role != UserRole.SELLER:
        await message.answer("Только для продавцов.")
        db.close()
        return
    
    limits = get_tariff_limits(user.tariff)
    if limits["daily_offers"] == 0:
        await message.answer("⚠️ В бесплатном тарифе нельзя писать первым. Обновите тариф!")
        db.close()
        return
    
    buyers = db.query(User).filter(User.role == UserRole.BUYER, User.search_budget_max > 0).order_by(User.created_at.desc()).limit(10).all()
    db.close()
    
    if not buyers:
        await message.answer("Пока нет активных покупателей.")
        return
    
    text = "🎯 Активные покупатели:\n\n"
    buttons = []
    
    for buyer in buyers:
        payment = {"cash": "Нал.", "mortgage": "Ипотека", "installment": "Рассрочка"}.get(buyer.search_payment_type, "")
        text += f"👤 {buyer.first_name or 'Покупатель'}\n   🚪 {buyer.search_rooms or '?'} комн. | до ${buyer.search_budget_max:,} | {payment}\n\n"
        buttons.append([InlineKeyboardButton(text=f"📤 Предложить {buyer.first_name or 'покупателю'}", callback_data=f"offer_{buyer.id}")])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data.startswith("offer_"))
async def send_offer(callback: types.CallbackQuery):
    buyer_id = int(callback.data.replace("offer_", ""))
    
    db = SessionLocal()
    seller = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    properties = db.query(Property).filter(Property.owner_id == seller.id, Property.status == PropertyStatus.ACTIVE).all()
    db.close()
    
    if not properties:
        await callback.answer("Нет активных объектов!")
        return
    
    buttons = [[InlineKeyboardButton(text=f"{p.district} - ${p.price:,}", callback_data=f"sendprop_{buyer_id}_{p.id}")] for p in properties[:5]]
    await callback.message.answer("Выберите объект:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data.startswith("sendprop_"))
async def send_property_offer(callback: types.CallbackQuery):
    parts = callback.data.replace("sendprop_", "").split("_")
    buyer_id, property_id = int(parts[0]), int(parts[1])
    
    db = SessionLocal()
    seller = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    buyer = db.query(User).filter(User.id == buyer_id).first()
    prop = db.query(Property).filter(Property.id == property_id).first()
    
    offer = Offer(seller_id=seller.id, buyer_id=buyer_id, property_id=property_id)
    db.add(offer)
    seller.daily_offers_count += 1
    db.commit()
    
    try:
        await bot.send_message(
            buyer.telegram_id,
            f"📬 Новое предложение!\n\n📍 {prop.district}\n🚪 {prop.rooms} комн.\n💰 ${prop.price:,}\n\nИнтересно?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да", callback_data=f"accept_offer_{offer.id}"),
                 InlineKeyboardButton(text="❌ Нет", callback_data=f"reject_offer_{offer.id}")]
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
        db.close()
        return
    
    offer.is_accepted = True
    match = Match(buyer_id=offer.buyer_id, seller_id=offer.seller_id, property_id=offer.property_id)
    db.add(match)
    
    seller = db.query(User).filter(User.id == offer.seller_id).first()
    buyer = db.query(User).filter(User.id == offer.buyer_id).first()
    prop = db.query(Property).filter(Property.id == offer.property_id).first()
    db.commit()
    
    try:
        await bot.send_message(seller.telegram_id, f"🎉 Покупатель принял предложение!\n👤 {buyer.first_name or 'Покупатель'}")
    except:
        pass
    
    db.close()
    await callback.message.edit_text(f"✅ Отлично!\n\n📞 {seller.phone or 'Нет'}\n👤 {seller.manager_name or seller.first_name}")


@dp.callback_query(F.data.startswith("reject_offer_"))
async def reject_offer(callback: types.CallbackQuery):
    offer_id = int(callback.data.replace("reject_offer_", ""))
    db = SessionLocal()
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if offer:
        offer.is_accepted = False
        db.commit()
    db.close()
    await callback.message.edit_text("Спасибо! Найдём другие варианты.")


@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    db.close()
    
    if user.role == UserRole.SELLER:
        type_names = {SellerType.OWNER: "Собственник", SellerType.REALTOR: "Риелтор", SellerType.DEVELOPER: "Застройщик"}
        tariff_names = {TariffType.FREE: "Бесплатный", TariffType.AGENCY_START: "Агентство Start", TariffType.DEVELOPER_PRO: "Застройщик PRO"}
        text = f"👤 Профиль\n\n📋 Тип: {type_names.get(user.seller_type, '-')}\n🏢 Компания: {user.company_name or '-'}\n👤 Менеджер: {user.manager_name or '-'}\n📞 Телефон: {user.phone or '-'}\n💳 Тариф: {tariff_names.get(user.tariff, 'Бесплатный')}"
    else:
        payment_names = {"cash": "Наличные", "mortgage": "Ипотека", "installment": "Рассрочка"}
        text = f"👤 Профиль\n\n🚪 Ищу: {user.search_rooms or '?'} комн.\n📍 Район: {user.search_district or 'Любой'}\n💰 Бюджет: до ${user.search_budget_max:,}\n💳 Оплата: {payment_names.get(user.search_payment_type, '-')}"
    
    await message.answer(text)


@dp.message(F.text == "💳 Тарифы")
async def tariffs(message: types.Message):
    text = (
        "💳 Тарифы\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🆓 Частник (Бесплатно)\n• 2 объекта\n• Нельзя писать первым\n\n"
        "🏢 Агентство Start (500,000 сум/мес)\n• 20 объектов\n• 10 предложений в день\n\n"
        "🏗 Застройщик PRO (2,000,000 сум/мес)\n• Безлимит объектов\n• 50 предложений в день\n\n"
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
        await message.answer("Вы ещё не лайкнули ни одной квартиры.")
        return
    
    text = "❤️ Ваши лайки:\n\n"
    for like in likes[:20]:
        db = SessionLocal()
        prop = db.query(Property).filter(Property.id == like.property_id).first()
        db.close()
        if prop:
            status = "🟢 Мэтч!" if like.is_matched else "⏳ Ожидание"
            text += f"{status} {prop.district} | {prop.rooms} комн. | ${prop.price:,}\n\n"
    
    await message.answer(text)


@dp.message(F.text == "⚙️ Настройки поиска")
async def search_settings(message: types.Message, state: FSMContext):
    await message.answer(
        "⚙️ Изменить параметры\n\nВыберите количество комнат:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="1", callback_data="brooms_1"), InlineKeyboardButton(text="2", callback_data="brooms_2"), InlineKeyboardButton(text="3", callback_data="brooms_3")],
            [InlineKeyboardButton(text="4", callback_data="brooms_4"), InlineKeyboardButton(text="5+", callback_data="brooms_5"), InlineKeyboardButton(text="Студия", callback_data="brooms_studio")]
        ])
    )
    await state.set_state(RegistrationStates.buyer_rooms)


@dp.message(F.text == "💬 Мэтчи")
async def buyer_matches(message: types.Message):
    await deals(message)


async def main():
    print("Initializing database...")
    init_db()
    print("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
