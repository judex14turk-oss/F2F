from sqlalchemy import create_engine, Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, Enum, BigInteger
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timedelta, timezone
import enum
import os


def get_tashkent_now():
    """Возвращает текущее время в Ташкенте (UTC+5)"""
    tashkent_tz = timezone(timedelta(hours=5))
    return datetime.now(tashkent_tz).replace(tzinfo=None)

DATABASE_URL = os.environ.get('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class UserRole(enum.Enum):
    BUYER = "buyer"
    SELLER = "seller"


class AdminRole(enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    OPERATOR = "operator"


class SellerType(enum.Enum):
    OWNER = "owner"
    REALTOR = "realtor"
    DEVELOPER = "developer"


class TariffType(enum.Enum):
    FREE = "FREE"
    AGENCY_START = "AGENCY_START"
    DEVELOPER_PRO = "DEVELOPER_PRO"
    PRO = "PRO"
    PREMIUM = "PREMIUM"


class PropertyType(enum.Enum):
    SALE = "sale"
    RENT = "rent"


class PropertyStatus(enum.Enum):
    ACTIVE = "active"
    MODERATION = "moderation"
    ARCHIVE = "archive"


class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    phone = Column(String(20))
    language = Column(String(10), default=None)
    email = Column(String(200))
    password = Column(String(200))
    role = Column(Enum(UserRole), default=UserRole.BUYER)
    is_admin = Column(Boolean, default=False)
    admin_role = Column(Enum(AdminRole), nullable=True)
    is_blocked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=get_tashkent_now)
    
    search_rooms = Column(String(50))
    search_floor = Column(String(20))
    search_district = Column(String(200))
    search_budget_min = Column(Integer)
    search_budget_max = Column(Integer)
    search_payment_type = Column(String(50))
    search_housing_type = Column(String(50))
    search_deal_type = Column(String(20))
    buyer_bio = Column(String(320))
    search_area_min = Column(Integer)
    search_area_max = Column(Integer)
    search_building_type = Column(String(100))
    search_renovation = Column(String(100))
    search_furniture = Column(String(20))
    search_bathroom = Column(String(50))
    
    seller_type = Column(Enum(SellerType))
    company_name = Column(String(200))
    manager_name = Column(String(100))
    tariff = Column(Enum(TariffType), default=TariffType.FREE)
    tariff_expires = Column(DateTime)
    trial_ends_at = Column(DateTime)
    daily_offers_count = Column(Integer, default=0)
    daily_offers_reset = Column(DateTime, default=get_tashkent_now)
    trial_used = Column(Boolean, default=False)
    balance = Column(Integer, default=0)
    bonus_properties = Column(Integer, default=0)
    bonus_likes = Column(Integer, default=0)
    
    properties = relationship("Property", back_populates="owner")
    likes_given = relationship("Like", foreign_keys="Like.user_id", back_populates="user")
    likes_received = relationship("Like", foreign_keys="Like.property_owner_id", back_populates="property_owner")
    offers_sent = relationship("Offer", foreign_keys="Offer.seller_id", back_populates="seller")
    offers_received = relationship("Offer", foreign_keys="Offer.buyer_id", back_populates="buyer")


class Property(Base):
    __tablename__ = 'properties'
    
    id = Column(Integer, primary_key=True)
    unique_id = Column(String(20), unique=True, nullable=True)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    property_type = Column(Enum(PropertyType), nullable=False)
    residential_complex = Column(String(200))
    district = Column(String(200))
    address = Column(String(1000))
    rooms = Column(Integer)
    floor = Column(Integer)
    total_floors = Column(Integer)
    area = Column(Float)
    price = Column(Integer, nullable=False)
    description = Column(Text)
    photos = Column(Text)
    status = Column(Enum(PropertyStatus), default=PropertyStatus.MODERATION)
    views_count = Column(Integer, default=0)
    likes_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_tashkent_now)
    updated_at = Column(DateTime, default=get_tashkent_now, onupdate=get_tashkent_now)
    archived_at = Column(DateTime, nullable=True)
    
    housing_type = Column(String(200))
    building_type = Column(String(200))
    renovation = Column(String(200))
    layout = Column(String(200))
    room_type = Column(String(200))
    bathroom_type = Column(String(200))
    has_furniture = Column(Boolean, default=False)
    
    phone = Column(String(100))
    olx_url = Column(String(500))
    olx_id = Column(String(200), unique=True, nullable=True)
    olx_title = Column(String(500))
    source = Column(String(100), default='manual')
    seller_name = Column(String(200))
    
    owner = relationship("User", back_populates="properties")
    likes = relationship("Like", back_populates="property", cascade="all, delete-orphan")
    matches = relationship("Match", back_populates="property", cascade="all, delete-orphan")
    offers = relationship("Offer", back_populates="property", cascade="all, delete-orphan")


class Like(Base):
    __tablename__ = 'likes'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    property_id = Column(Integer, ForeignKey('properties.id'), nullable=False)
    property_owner_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=get_tashkent_now)
    is_matched = Column(Boolean, default=False)
    
    user = relationship("User", foreign_keys=[user_id], back_populates="likes_given")
    property_owner = relationship("User", foreign_keys=[property_owner_id], back_populates="likes_received")
    property = relationship("Property", back_populates="likes")


class Match(Base):
    __tablename__ = 'matches'
    
    id = Column(Integer, primary_key=True)
    buyer_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    seller_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    property_id = Column(Integer, ForeignKey('properties.id'), nullable=False)
    created_at = Column(DateTime, default=get_tashkent_now)
    note = Column(Text)
    status = Column(String(50), default='active')
    
    buyer = relationship("User", foreign_keys=[buyer_id])
    seller = relationship("User", foreign_keys=[seller_id])
    property = relationship("Property", back_populates="matches")


class Offer(Base):
    __tablename__ = 'offers'
    
    id = Column(Integer, primary_key=True)
    seller_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    buyer_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    property_id = Column(Integer, ForeignKey('properties.id'), nullable=False)
    created_at = Column(DateTime, default=get_tashkent_now)
    is_accepted = Column(Boolean)
    
    seller = relationship("User", foreign_keys=[seller_id], back_populates="offers_sent")
    buyer = relationship("User", foreign_keys=[buyer_id], back_populates="offers_received")
    property = relationship("Property", back_populates="offers")


class ResidentialComplex(Base):
    __tablename__ = 'residential_complexes'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    district = Column(String(200))
    developer = Column(String(200))
    created_at = Column(DateTime, default=get_tashkent_now)


class District(Base):
    __tablename__ = 'districts'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    city = Column(String(100), default='Ташкент')


class PromoCode(Base):
    __tablename__ = 'promo_codes'
    
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    discount_percent = Column(Integer, default=0)
    bonus_days = Column(Integer, default=0)
    bonus_properties = Column(Integer, default=0)
    bonus_likes = Column(Integer, default=0)
    tariff = Column(String(50))
    max_uses = Column(Integer, default=1)
    current_uses = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=get_tashkent_now)
    description = Column(String(200))


class PromoRequest(Base):
    __tablename__ = 'promo_requests'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    promo_code_id = Column(Integer, ForeignKey('promo_codes.id'))
    promo_code_text = Column(String(50))
    status = Column(String(20), default='pending')
    created_at = Column(DateTime, default=get_tashkent_now)
    processed_at = Column(DateTime)
    processed_by = Column(Integer)
    
    user = relationship("User")
    promo_code = relationship("PromoCode")


class TariffSettings(Base):
    __tablename__ = 'tariff_settings'
    
    id = Column(Integer, primary_key=True)
    tariff_type = Column(String(50), unique=True, nullable=False)
    price = Column(Integer, default=0)
    properties_limit = Column(Integer, default=2)
    likes_per_day = Column(Integer, default=1)
    priority_display = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=get_tashkent_now, onupdate=get_tashkent_now)


class Advertisement(Base):
    __tablename__ = 'advertisements'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(200))
    description = Column(Text)
    media = Column(Text)
    media_type = Column(String(20), default='photo')
    is_active = Column(Boolean, default=True)
    views_count = Column(Integer, default=0)
    clicks_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_tashkent_now)
    updated_at = Column(DateTime, default=get_tashkent_now, onupdate=get_tashkent_now)


def init_db():
    Base.metadata.create_all(engine)
    
    session = SessionLocal()
    try:
        districts = [
            "Алмазарский", "Бектемирский", "Мирабадский", "Мирзо-Улугбекский",
            "Сергелийский", "Учтепинский", "Чиланзарский", "Шайхантаурский",
            "Юнусабадский", "Яккасарайский", "Яшнабадский", "Янгихаётский", "Новый Ташкент"
        ]
        
        for district_name in districts:
            existing = session.query(District).filter_by(name=district_name).first()
            if not existing:
                session.add(District(name=district_name))
        
        complexes = [
            {"name": "Ташкент Сити", "district": "Юнусабадский"},
            {"name": "Сарбон Палас", "district": "Юнусабадский"},
            {"name": "Grand Mir Residence", "district": "Мирзо-Улугбекский"},
            {"name": "Mirabad Hills", "district": "Мирабадский"},
        ]
        
        for complex_data in complexes:
            existing = session.query(ResidentialComplex).filter_by(name=complex_data["name"]).first()
            if not existing:
                session.add(ResidentialComplex(**complex_data))
        
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error initializing database: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully!")
