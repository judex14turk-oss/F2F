import os
import time
import requests
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
from sqlalchemy.orm import joinedload
from models import SessionLocal, User, Property, Like, Match, Offer, District, ResidentialComplex, PromoCode, TariffSettings, Advertisement
from models import UserRole, SellerType, TariffType, PropertyType, PropertyStatus, AdminRole, init_db, get_tashkent_now

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'real-estate-bot-secret-key')
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True

ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'InvictumMurad')


def get_db():
    return SessionLocal()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        db = get_db()
        user = db.query(User).filter(User.id == session['user_id']).first()
        db.close()
        if not user or not user.is_admin:
            return "Access denied", 403
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        telegram_id = request.form.get('telegram_id')
        db = get_db()
        user = db.query(User).filter(User.telegram_id == int(telegram_id)).first()
        if user:
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            db.close()
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('seller_dashboard'))
        db.close()
        return render_template('login.html', error="User not found")
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/telegram_photo/<path:file_id>')
def telegram_photo(file_id):
    """Proxy Telegram photos to display in web interface"""
    if not TELEGRAM_BOT_TOKEN:
        return "Bot token not configured", 500
    
    try:
        get_file_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
        response = requests.get(get_file_url, timeout=10)
        data = response.json()
        
        if not data.get('ok'):
            return "File not found", 404
        
        file_path = data['result']['file_path']
        photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        
        photo_response = requests.get(photo_url, timeout=30)
        if photo_response.status_code == 200:
            return Response(
                photo_response.content,
                mimetype=photo_response.headers.get('Content-Type', 'image/jpeg')
            )
        return "Failed to fetch photo", 500
    except Exception as e:
        return f"Error: {str(e)}", 500


@app.route('/webapp/auth')
def webapp_auth():
    seller_type = request.args.get('type', 'realtor')
    tg_id = request.args.get('tg_id', '')
    
    type_names = {
        'realtor': '🔑 Риелтор',
        'developer': '🏗 Застройщик'
    }
    
    return render_template('webapp_auth.html',
        seller_type=seller_type,
        seller_type_name=type_names.get(seller_type, 'Риелтор'),
        tg_id=tg_id
    )


@app.route('/webapp/login', methods=['GET', 'POST'])
def webapp_login():
    seller_type = request.args.get('type', 'realtor')
    tg_id = request.args.get('tg_id', '')
    
    if request.method == 'POST':
        login_value = request.form.get('login', '')
        password = request.form.get('password', '')
        tg_id = request.form.get('tg_id', '')
        seller_type = request.form.get('seller_type', 'realtor')
        
        db = get_db()
        user = db.query(User).filter(
            (User.phone == login_value) | (User.email == login_value)
        ).first()
        
        if user and user.password == password:
            if tg_id:
                user.telegram_id = int(tg_id)
                db.commit()
            session['user_id'] = user.id
            db.close()
            return '''
                <script src="https://telegram.org/js/telegram-web-app.js"></script>
                <script>
                    const tg = window.Telegram.WebApp;
                    tg.ready();
                    tg.sendData(JSON.stringify({action: 'login_success', user_id: ''' + str(user.id) + '''}));
                    tg.close();
                </script>
            '''
        db.close()
        return render_template('webapp_login.html',
            error="Неверный логин или пароль",
            seller_type=seller_type,
            tg_id=tg_id
        )
    
    return render_template('webapp_login.html',
        seller_type=seller_type,
        tg_id=tg_id
    )


@app.route('/webapp/register', methods=['GET', 'POST'])
def webapp_register():
    seller_type = request.args.get('type', 'realtor')
    tg_id = request.args.get('tg_id', '')
    
    type_names = {
        'realtor': '🔑 Риелтор',
        'developer': '🏗 Застройщик'
    }
    
    if request.method == 'POST':
        company_name = request.form.get('company_name', '')
        manager_name = request.form.get('manager_name', '')
        phone = request.form.get('phone', '')
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        tg_id = request.form.get('tg_id', '')
        seller_type = request.form.get('seller_type', 'realtor')
        
        db = get_db()
        
        from models import SellerType as ST, TariffType as TT, UserRole as UR
        from datetime import timedelta
        
        existing_by_contact = db.query(User).filter(
            (User.phone == phone) | (User.email == email)
        ).first()
        
        existing_by_tg = None
        if tg_id:
            existing_by_tg = db.query(User).filter(User.telegram_id == int(tg_id)).first()
        
        if existing_by_contact and (not existing_by_tg or existing_by_contact.id != existing_by_tg.id):
            db.close()
            return render_template('webapp_register.html',
                error="Пользователь с таким телефоном или email уже существует",
                seller_type=seller_type,
                seller_type_name=type_names.get(seller_type, 'Риелтор'),
                tg_id=tg_id
            )
        
        seller_type_enum = ST.REALTOR if seller_type == 'realtor' else ST.DEVELOPER
        tariff = TT.AGENCY_START if seller_type == 'realtor' else TT.DEVELOPER_PRO
        
        if existing_by_tg:
            user = existing_by_tg
            user.role = UR.SELLER
            user.seller_type = seller_type_enum
            user.company_name = company_name
            user.manager_name = manager_name
            user.phone = phone
            user.email = email
            user.password = password
            user.tariff = tariff
            user.trial_ends_at = get_tashkent_now() + timedelta(days=14)
        else:
            user = User(
                telegram_id=int(tg_id) if tg_id else 0,
                role=UR.SELLER,
                seller_type=seller_type_enum,
                company_name=company_name,
                manager_name=manager_name,
                phone=phone,
                email=email,
                password=password,
                tariff=tariff,
                trial_ends_at=get_tashkent_now() + timedelta(days=14)
            )
            db.add(user)
        
        db.commit()
        user_id = user.id
        db.close()
        
        return '''
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
            <script>
                const tg = window.Telegram.WebApp;
                tg.ready();
                tg.sendData(JSON.stringify({action: 'register_success', user_id: ''' + str(user_id) + '''}));
                tg.close();
            </script>
        '''
    
    return render_template('webapp_register.html',
        seller_type=seller_type,
        seller_type_name=type_names.get(seller_type, 'Риелтор'),
        tg_id=tg_id
    )


@app.route('/admin')
@admin_required
def admin_dashboard():
    db = get_db()
    
    total_users = db.query(User).count()
    buyers = db.query(User).filter(User.role == UserRole.BUYER).count()
    sellers = db.query(User).filter(User.role == UserRole.SELLER).count()
    properties = db.query(Property).count()
    active_properties = db.query(Property).filter(Property.status == PropertyStatus.ACTIVE).count()
    matches = db.query(Match).count()
    
    recent_users = db.query(User).order_by(User.created_at.desc()).limit(10).all()
    recent_properties = db.query(Property).order_by(Property.created_at.desc()).limit(10).all()
    
    db.close()
    
    return render_template('admin/dashboard.html',
        total_users=total_users,
        buyers=buyers,
        sellers=sellers,
        properties=properties,
        active_properties=active_properties,
        matches=matches,
        recent_users=recent_users,
        recent_properties=recent_properties
    )


@app.route('/admin/users')
@admin_required
def admin_users():
    db = get_db()
    
    role_filter = request.args.get('role', 'all')
    tariff_filter = request.args.get('tariff', 'all')
    sort_by = request.args.get('sort', 'created_at')
    sort_order = request.args.get('order', 'desc')
    search_query = request.args.get('q', '').strip()
    
    query = db.query(User)
    
    if role_filter == 'buyer':
        query = query.filter(User.role == UserRole.BUYER)
    elif role_filter == 'seller':
        query = query.filter(User.role == UserRole.SELLER)
    
    if tariff_filter != 'all':
        tariff_map = {
            'free': TariffType.FREE,
            'agency_start': TariffType.AGENCY_START,
            'developer_pro': TariffType.DEVELOPER_PRO,
            'pro': TariffType.PRO,
            'premium': TariffType.PREMIUM
        }
        if tariff_filter in tariff_map:
            query = query.filter(User.tariff == tariff_map[tariff_filter])
    
    if search_query:
        search_pattern = f"%{search_query}%"
        if search_query.isdigit():
            query = query.filter(User.telegram_id == int(search_query))
        else:
            query = query.filter(
                (User.first_name.ilike(search_pattern)) |
                (User.last_name.ilike(search_pattern)) |
                (User.username.ilike(search_pattern)) |
                (User.phone.ilike(search_pattern)) |
                (User.company_name.ilike(search_pattern))
            )
    
    sort_columns = {
        'created_at': User.created_at,
        'telegram_id': User.telegram_id,
        'first_name': User.first_name,
        'tariff': User.tariff,
        'role': User.role,
        'balance': User.balance
    }
    sort_column = sort_columns.get(sort_by, User.created_at)
    
    if sort_order == 'asc':
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())
    
    users = query.all()
    
    total_count = db.query(User).count()
    buyers_count = db.query(User).filter(User.role == UserRole.BUYER).count()
    sellers_count = db.query(User).filter(User.role == UserRole.SELLER).count()
    
    db.close()
    
    return render_template('admin/users.html', 
        users=users,
        role_filter=role_filter,
        tariff_filter=tariff_filter,
        sort_by=sort_by,
        sort_order=sort_order,
        search_query=search_query,
        total_count=total_count,
        buyers_count=buyers_count,
        sellers_count=sellers_count
    )


@app.route('/admin/users/<int:user_id>')
@admin_required
def admin_user_detail(user_id):
    db = get_db()
    user = db.query(User).filter(User.id == user_id).first()
    properties = db.query(Property).filter(Property.owner_id == user_id).all() if user else []
    matches = db.query(Match).filter((Match.buyer_id == user_id) | (Match.seller_id == user_id)).all() if user else []
    db.close()
    return render_template('admin/user_detail.html', user=user, properties=properties, matches=matches)


@app.route('/admin/users/<int:user_id>/update_tariff', methods=['POST'])
@admin_required
def update_user_tariff(user_id):
    tariff = request.form.get('tariff')
    redirect_to = request.form.get('redirect', 'detail')
    db = get_db()
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        tariff_map = {
            'free': TariffType.FREE,
            'agency_start': TariffType.AGENCY_START,
            'developer_pro': TariffType.DEVELOPER_PRO,
            'pro': TariffType.PRO,
            'premium': TariffType.PREMIUM
        }
        user.tariff = tariff_map.get(tariff, TariffType.FREE)
        if tariff != 'free':
            user.tariff_expires = get_tashkent_now() + timedelta(days=30)
        else:
            user.tariff_expires = None
        db.commit()
    db.close()
    
    if redirect_to == 'list':
        return redirect(url_for('admin_users'))
    return redirect(url_for('admin_user_detail', user_id=user_id))


@app.route('/admin/properties')
@admin_required
def admin_properties():
    db = get_db()
    
    status_filter = request.args.get('status', 'all')
    type_filter = request.args.get('type', 'all')
    district_filter = request.args.get('district', 'all')
    rooms_filter = request.args.get('rooms', 'all')
    source_filter = request.args.get('source', 'all')
    price_min = request.args.get('price_min', '')
    price_max = request.args.get('price_max', '')
    search_query = request.args.get('q', '').strip()
    sort_by = request.args.get('sort', 'created_at')
    sort_order = request.args.get('order', 'desc')
    
    query = db.query(Property)
    
    if status_filter == 'active':
        query = query.filter(Property.status == PropertyStatus.ACTIVE)
    elif status_filter == 'moderation':
        query = query.filter(Property.status == PropertyStatus.MODERATION)
    elif status_filter == 'archive':
        query = query.filter(Property.status == PropertyStatus.ARCHIVE)
    
    if type_filter == 'sale':
        query = query.filter(Property.property_type == PropertyType.SALE)
    elif type_filter == 'rent':
        query = query.filter(Property.property_type == PropertyType.RENT)
    
    if district_filter != 'all':
        query = query.filter(Property.district.ilike(f'%{district_filter}%'))
    
    if rooms_filter != 'all' and rooms_filter.isdigit():
        query = query.filter(Property.rooms == int(rooms_filter))
    
    if source_filter == 'olx':
        query = query.filter(Property.source == 'olx')
    elif source_filter == 'manual':
        query = query.filter(Property.source == 'manual')
    
    if price_min and price_min.isdigit():
        query = query.filter(Property.price >= int(price_min))
    if price_max and price_max.isdigit():
        query = query.filter(Property.price <= int(price_max))
    
    if search_query:
        search_pattern = f"%{search_query}%"
        if search_query.isdigit():
            query = query.filter(Property.id == int(search_query))
        else:
            query = query.filter(
                (Property.unique_id.ilike(search_pattern)) |
                (Property.residential_complex.ilike(search_pattern)) |
                (Property.address.ilike(search_pattern)) |
                (Property.olx_id.ilike(search_pattern)) |
                (Property.seller_name.ilike(search_pattern))
            )
    
    sort_columns = {
        'created_at': Property.created_at,
        'price': Property.price,
        'area': Property.area,
        'rooms': Property.rooms,
        'views': Property.views_count,
        'likes': Property.likes_count
    }
    sort_column = sort_columns.get(sort_by, Property.created_at)
    
    if sort_order == 'asc':
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())
    
    properties = query.all()
    
    all_districts = db.query(Property.district).distinct().filter(Property.district.isnot(None)).all()
    districts = sorted([d[0] for d in all_districts if d[0]])
    
    total_count = db.query(Property).count()
    active_count = db.query(Property).filter(Property.status == PropertyStatus.ACTIVE).count()
    moderation_count = db.query(Property).filter(Property.status == PropertyStatus.MODERATION).count()
    olx_count = db.query(Property).filter(Property.source == 'olx').count()
    
    db.close()
    
    return render_template('admin/properties.html', 
        properties=properties, 
        status_filter=status_filter,
        type_filter=type_filter,
        district_filter=district_filter,
        rooms_filter=rooms_filter,
        source_filter=source_filter,
        price_min=price_min,
        price_max=price_max,
        search_query=search_query,
        sort_by=sort_by,
        sort_order=sort_order,
        districts=districts,
        total_count=total_count,
        active_count=active_count,
        moderation_count=moderation_count,
        olx_count=olx_count
    )


@app.route('/admin/properties/<int:property_id>/approve', methods=['POST'])
@admin_required
def approve_property(property_id):
    db = get_db()
    prop = db.query(Property).filter(Property.id == property_id).first()
    if prop:
        prop.status = PropertyStatus.ACTIVE
        db.commit()
    db.close()
    return redirect(url_for('admin_properties'))


@app.route('/admin/properties/<int:property_id>/reject', methods=['POST'])
@admin_required
def reject_property(property_id):
    db = get_db()
    prop = db.query(Property).filter(Property.id == property_id).first()
    if prop:
        prop.status = PropertyStatus.ARCHIVE
        db.commit()
    db.close()
    return redirect(url_for('admin_properties'))


@app.route('/admin/properties/<int:property_id>')
@admin_required
def admin_property_detail(property_id):
    db = get_db()
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        db.close()
        return "Объект не найден", 404
    
    owner = db.query(User).filter(User.id == prop.owner_id).first()
    likes = db.query(Like).filter(Like.property_id == property_id).all()
    
    photo_ids = prop.photos.split(',') if prop.photos else []
    photos = []
    for pid in photo_ids:
        if pid:
            if pid.startswith('http://') or pid.startswith('https://'):
                photos.append(pid)
            else:
                photos.append(url_for('telegram_photo', file_id=pid))
    
    db.close()
    return render_template('admin/property_detail.html', prop=prop, owner=owner, likes=likes, photos=photos)


@app.route('/admin/matches')
@admin_required
def admin_matches():
    db = get_db()
    matches = db.query(Match).order_by(Match.created_at.desc()).all()
    db.close()
    return render_template('admin/matches.html', matches=matches)


@app.route('/admin/stats')
@admin_required
def admin_stats():
    db = get_db()
    
    today = get_tashkent_now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    daily_users = db.query(User).filter(User.created_at >= today).count()
    weekly_users = db.query(User).filter(User.created_at >= week_ago).count()
    monthly_users = db.query(User).filter(User.created_at >= month_ago).count()
    
    daily_properties = db.query(Property).filter(Property.created_at >= today).count()
    weekly_properties = db.query(Property).filter(Property.created_at >= week_ago).count()
    
    daily_matches = db.query(Match).filter(Match.created_at >= today).count()
    weekly_matches = db.query(Match).filter(Match.created_at >= week_ago).count()
    
    db.close()
    
    return render_template('admin/stats.html',
        daily_users=daily_users,
        weekly_users=weekly_users,
        monthly_users=monthly_users,
        daily_properties=daily_properties,
        weekly_properties=weekly_properties,
        daily_matches=daily_matches,
        weekly_matches=weekly_matches
    )


@app.route('/seller')
@login_required
def seller_dashboard():
    db = get_db()
    user = db.query(User).filter(User.id == session['user_id']).first()
    
    properties = db.query(Property).filter(Property.owner_id == user.id).all()
    total_views = sum(p.views_count for p in properties)
    total_likes = sum(p.likes_count for p in properties)
    
    matches = db.query(Match).filter(Match.seller_id == user.id).order_by(Match.created_at.desc()).all()
    
    pending_likes = db.query(Like).filter(
        Like.property_owner_id == user.id,
        Like.is_matched == False
    ).count()
    
    db.close()
    
    return render_template('seller/dashboard.html',
        user=user,
        properties=properties,
        total_views=total_views,
        total_likes=total_likes,
        matches_count=len(matches),
        pending_likes=pending_likes,
        matches=matches[:5]
    )


@app.route('/seller/properties')
@login_required
def seller_properties():
    db = get_db()
    user = db.query(User).filter(User.id == session['user_id']).first()
    properties = db.query(Property).filter(Property.owner_id == user.id).order_by(Property.created_at.desc()).all()
    db.close()
    return render_template('seller/properties.html', properties=properties)


@app.route('/seller/crm')
@login_required
def seller_crm():
    db = get_db()
    user = db.query(User).filter(User.id == session['user_id']).first()
    
    matches = db.query(Match).filter(Match.seller_id == user.id).order_by(Match.created_at.desc()).all()
    
    crm_data = []
    for match in matches:
        buyer = db.query(User).filter(User.id == match.buyer_id).first()
        prop = db.query(Property).filter(Property.id == match.property_id).first()
        crm_data.append({
            'match': match,
            'buyer': buyer,
            'property': prop
        })
    
    db.close()
    return render_template('seller/crm.html', crm_data=crm_data)


@app.route('/seller/crm/<int:match_id>/note', methods=['POST'])
@login_required
def update_match_note(match_id):
    note = request.form.get('note', '')
    db = get_db()
    match = db.query(Match).filter(Match.id == match_id).first()
    if match and match.seller_id == session['user_id']:
        match.note = note
        db.commit()
    db.close()
    return redirect(url_for('seller_crm'))


@app.route('/webapp/tariffs')
def webapp_tariffs():
    return render_template('tariffs.html')


@app.route('/webapp/advertising')
def webapp_advertising():
    return render_template('advertising.html')


def get_admin_permissions(admin_role):
    """Возвращает права доступа для роли администратора"""
    if admin_role == AdminRole.SUPER_ADMIN:
        return {
            'can_edit_tariff': True,
            'can_view_admins': True,
            'can_manage_admins': True,
            'can_delete_users': True,
            'can_parse': True,
            'can_manage_ads': True,
            'can_moderate': True,
            'role_name': 'Старший администратор'
        }
    elif admin_role == AdminRole.ADMIN:
        return {
            'can_edit_tariff': True,
            'can_view_admins': True,
            'can_manage_admins': False,
            'can_delete_users': False,
            'can_parse': False,
            'can_manage_ads': True,
            'can_moderate': True,
            'role_name': 'Администратор'
        }
    elif admin_role == AdminRole.OPERATOR:
        return {
            'can_edit_tariff': False,
            'can_view_admins': False,
            'can_manage_admins': False,
            'can_delete_users': False,
            'can_parse': False,
            'can_manage_ads': False,
            'can_moderate': True,
            'role_name': 'Оператор'
        }
    return {
        'can_edit_tariff': False,
        'can_view_admins': False,
        'can_manage_admins': False,
        'can_delete_users': False,
        'can_parse': False,
        'can_manage_ads': False,
        'can_moderate': False,
        'role_name': 'Нет доступа'
    }


@app.route('/webapp/admin')
def webapp_admin():
    tg_id = request.args.get('tg_id')
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    
    session['user_id'] = admin_user.id
    session['is_admin'] = True
    
    role_filter = request.args.get('role', 'all')
    tariff_filter = request.args.get('tariff', 'all')
    sort_by = request.args.get('sort', 'created_at')
    sort_order = request.args.get('order', 'desc')
    search_query = request.args.get('q', '').strip()
    
    query = db.query(User)
    
    if role_filter == 'buyer':
        query = query.filter(User.role == UserRole.BUYER)
    elif role_filter == 'seller':
        query = query.filter(User.role == UserRole.SELLER)
    
    if tariff_filter != 'all':
        tariff_map = {
            'free': TariffType.FREE,
            'agency_start': TariffType.AGENCY_START,
            'developer_pro': TariffType.DEVELOPER_PRO,
            'pro': TariffType.PRO,
            'premium': TariffType.PREMIUM
        }
        if tariff_filter in tariff_map:
            query = query.filter(User.tariff == tariff_map[tariff_filter])
    
    if search_query:
        search_pattern = f"%{search_query}%"
        if search_query.isdigit():
            query = query.filter(User.telegram_id == int(search_query))
        else:
            query = query.filter(
                (User.first_name.ilike(search_pattern)) |
                (User.last_name.ilike(search_pattern)) |
                (User.username.ilike(search_pattern)) |
                (User.phone.ilike(search_pattern)) |
                (User.company_name.ilike(search_pattern))
            )
    
    sort_columns = {
        'created_at': User.created_at,
        'telegram_id': User.telegram_id,
        'first_name': User.first_name,
        'tariff': User.tariff,
        'role': User.role,
        'balance': User.balance
    }
    sort_column = sort_columns.get(sort_by, User.created_at)
    
    if sort_order == 'asc':
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())
    
    users = query.all()
    
    total_count = db.query(User).count()
    buyers_count = db.query(User).filter(User.role == UserRole.BUYER).count()
    sellers_count = db.query(User).filter(User.role == UserRole.SELLER).count()
    admins_count = db.query(User).filter(User.is_admin == True).count()
    
    db.close()
    
    return render_template('webapp_admin.html',
        users=users,
        role_filter=role_filter,
        tariff_filter=tariff_filter,
        sort_by=sort_by,
        sort_order=sort_order,
        search_query=search_query,
        total_count=total_count,
        buyers_count=buyers_count,
        sellers_count=sellers_count,
        admins_count=admins_count,
        tg_id=tg_id,
        permissions=permissions,
        admin_user=admin_user
    )


@app.route('/webapp/admin/user/<int:user_id>/tariff', methods=['POST'])
def webapp_update_tariff(user_id):
    tg_id = request.form.get('tg_id')
    tariff = request.form.get('tariff')
    
    print(f"[DEBUG] Updating tariff for user {user_id}: tg_id={tg_id}, tariff={tariff}")
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin.admin_role)
    if not permissions['can_edit_tariff']:
        db.close()
        return "У вас нет прав для редактирования тарифов", 403
    
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        tariff_map = {
            'free': TariffType.FREE,
            'agency_start': TariffType.AGENCY_START,
            'developer_pro': TariffType.DEVELOPER_PRO,
            'pro': TariffType.PRO,
            'premium': TariffType.PREMIUM
        }
        old_tariff = user.tariff
        user.tariff = tariff_map.get(tariff, TariffType.FREE)
        if tariff != 'free':
            user.tariff_expires = get_tashkent_now() + timedelta(days=30)
        else:
            user.tariff_expires = None
        db.commit()
        print(f"[DEBUG] User {user_id} tariff changed from {old_tariff} to {user.tariff}")
    else:
        print(f"[DEBUG] User {user_id} not found!")
    db.close()
    
    return redirect(url_for('webapp_admin', tg_id=tg_id))


@app.route('/webapp/admin/user/<int:user_id>/role', methods=['POST'])
def webapp_update_role(user_id):
    tg_id = request.form.get('tg_id')
    role = request.form.get('role')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        role_map = {
            'buyer': UserRole.BUYER,
            'seller': UserRole.SELLER
        }
        user.role = role_map.get(role, UserRole.BUYER)
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_admin', tg_id=tg_id))


@app.route('/webapp/admin/user/<int:user_id>/edit')
def webapp_user_edit(user_id):
    tg_id = request.args.get('tg_id')
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin.admin_role)
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        db.close()
        return "Пользователь не найден", 404
    
    properties = db.query(Property).filter(Property.owner_id == user.id).order_by(Property.created_at.desc()).all()
    
    tariff_days_left = None
    tariff_expires_date = None
    if user.tariff_expires:
        now = get_tashkent_now()
        tariff_days_left = (user.tariff_expires - now).days
        tariff_expires_date = user.tariff_expires.strftime('%d.%m.%Y')
    
    db.close()
    
    return render_template('webapp_user_edit.html',
        user=user,
        tg_id=tg_id,
        permissions=permissions,
        admin_user=admin,
        properties=properties,
        tariff_days_left=tariff_days_left,
        tariff_expires_date=tariff_expires_date
    )


@app.route('/webapp/admin/user/<int:user_id>/save', methods=['POST'])
def webapp_user_save(user_id):
    tg_id = request.form.get('tg_id')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin.admin_role)
    user = db.query(User).filter(User.id == user_id).first()
    
    if user:
        role = request.form.get('role')
        tariff = request.form.get('tariff')
        
        role_map = {
            'buyer': UserRole.BUYER,
            'seller': UserRole.SELLER
        }
        user.role = role_map.get(role, UserRole.BUYER)
        
        if permissions['can_edit_tariff']:
            tariff_map = {
                'free': TariffType.FREE,
                'agency_start': TariffType.AGENCY_START,
                'developer_pro': TariffType.DEVELOPER_PRO,
                'pro': TariffType.PRO,
                'premium': TariffType.PREMIUM
            }
            old_tariff = user.tariff
            new_tariff = tariff_map.get(tariff, TariffType.FREE)
            user.tariff = new_tariff
            
            add_days = request.form.get('add_days')
            if add_days and add_days.isdigit() and int(add_days) > 0:
                days_to_add = int(add_days)
                if user.tariff_expires and user.tariff_expires > get_tashkent_now():
                    user.tariff_expires = user.tariff_expires + timedelta(days=days_to_add)
                else:
                    user.tariff_expires = get_tashkent_now() + timedelta(days=days_to_add)
            elif tariff == 'free':
                user.tariff_expires = None
            elif old_tariff == TariffType.FREE and new_tariff != TariffType.FREE:
                user.tariff_expires = get_tashkent_now() + timedelta(days=30)
        
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_admin', tg_id=tg_id))


@app.route('/webapp/admin/admins')
def webapp_admins():
    tg_id = request.args.get('tg_id')
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    if not permissions['can_view_admins']:
        db.close()
        return "У вас нет прав для просмотра администраторов", 403
    
    admins = db.query(User).filter(User.is_admin == True).order_by(User.created_at.desc()).all()
    db.close()
    
    return render_template('webapp_admins.html',
        admins=admins,
        tg_id=tg_id,
        permissions=permissions,
        admin_user=admin_user
    )


@app.route('/webapp/admin/user/<int:user_id>/set_admin', methods=['POST'])
def webapp_set_admin_role(user_id):
    tg_id = request.form.get('tg_id')
    admin_role = request.form.get('admin_role')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin.admin_role)
    if not permissions['can_manage_admins']:
        db.close()
        return "У вас нет прав для управления администраторами", 403
    
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        if admin_role == 'remove':
            user.is_admin = False
            user.admin_role = None
        else:
            role_map = {
                'super_admin': AdminRole.SUPER_ADMIN,
                'admin': AdminRole.ADMIN,
                'operator': AdminRole.OPERATOR
            }
            user.is_admin = True
            user.admin_role = role_map.get(admin_role, AdminRole.OPERATOR)
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_admins', tg_id=tg_id))


@app.route('/webapp/admin/user/<int:user_id>/block', methods=['POST'])
def webapp_block_user(user_id):
    tg_id = request.form.get('tg_id')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.id != admin.id:
        user.is_blocked = not user.is_blocked
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_user_edit', user_id=user_id, tg_id=tg_id))


@app.route('/webapp/admin/user/<int:user_id>/delete', methods=['POST'])
def webapp_delete_user(user_id):
    tg_id = request.form.get('tg_id')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin.admin_role)
    if not permissions['can_delete_users']:
        db.close()
        return "У вас нет прав для удаления пользователей", 403
    
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.id != admin.id:
        db.query(Like).filter(Like.user_id == user.id).delete()
        db.query(Like).filter(Like.property_owner_id == user.id).delete()
        db.query(Match).filter(Match.buyer_id == user.id).delete()
        db.query(Match).filter(Match.seller_id == user.id).delete()
        db.query(Offer).filter(Offer.buyer_id == user.id).delete()
        db.query(Offer).filter(Offer.seller_id == user.id).delete()
        db.query(Property).filter(Property.owner_id == user.id).delete()
        db.delete(user)
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_admin', tg_id=tg_id))


@app.route('/webapp/admin/moderation')
def webapp_moderation():
    tg_id = request.args.get('tg_id')
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    if not permissions['can_moderate']:
        db.close()
        return "У вас нет прав для модерации объявлений", 403
    
    properties = db.query(Property).options(
        joinedload(Property.owner)
    ).filter(
        Property.status == PropertyStatus.MODERATION
    ).order_by(Property.created_at.desc()).all()
    
    moderation_count = len(properties)
    db.close()
    
    return render_template('webapp_moderation.html',
        tg_id=tg_id,
        permissions=permissions,
        admin_user=admin_user,
        properties=properties,
        moderation_count=moderation_count
    )


@app.route('/webapp/admin/property/<int:property_id>/approve', methods=['POST'])
def webapp_approve_property(property_id):
    tg_id = request.form.get('tg_id')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin.admin_role)
    if not permissions['can_moderate']:
        db.close()
        return "У вас нет прав для модерации", 403
    
    prop = db.query(Property).filter(Property.id == property_id).first()
    if prop:
        prop.status = PropertyStatus.ACTIVE
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_moderation', tg_id=tg_id))


@app.route('/webapp/admin/property/<int:property_id>/reject', methods=['POST'])
def webapp_reject_property(property_id):
    tg_id = request.form.get('tg_id')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin.admin_role)
    if not permissions['can_moderate']:
        db.close()
        return "У вас нет прав для модерации", 403
    
    prop = db.query(Property).filter(Property.id == property_id).first()
    if prop:
        db.delete(prop)
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_moderation', tg_id=tg_id))


@app.route('/webapp/admin/tariffs')
def webapp_tariff_settings():
    tg_id = request.args.get('tg_id')
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    if not permissions['can_edit_tariff']:
        db.close()
        return "У вас нет прав для управления тарифами", 403
    
    tariffs = db.query(TariffSettings).order_by(TariffSettings.price.asc()).all()
    promo_codes = db.query(PromoCode).order_by(PromoCode.created_at.desc()).all()
    db.close()
    
    return render_template('webapp_tariff_settings.html',
        tg_id=tg_id,
        permissions=permissions,
        admin_user=admin_user,
        tariffs=tariffs,
        promo_codes=promo_codes
    )


@app.route('/webapp/admin/tariff/update', methods=['POST'])
def webapp_update_tariff_settings():
    tg_id = request.form.get('tg_id')
    tariff_type = request.form.get('tariff_type')
    price = request.form.get('price', 0)
    properties_limit = request.form.get('properties_limit', 2)
    likes_per_day = request.form.get('likes_per_day', 1)
    priority = request.form.get('priority_display') == 'on'
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin.admin_role)
    if not permissions['can_edit_tariff']:
        db.close()
        return "У вас нет прав", 403
    
    tariff = db.query(TariffSettings).filter(TariffSettings.tariff_type == tariff_type).first()
    if tariff:
        tariff.price = int(price)
        tariff.properties_limit = int(properties_limit)
        tariff.likes_per_day = int(likes_per_day)
        tariff.priority_display = priority
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_tariff_settings', tg_id=tg_id))


@app.route('/webapp/admin/promo/create', methods=['POST'])
def webapp_create_promo():
    tg_id = request.form.get('tg_id')
    code = request.form.get('code', '').strip().upper()
    tariff = request.form.get('tariff')
    discount_percent = request.form.get('discount_percent', 0)
    days_valid = request.form.get('days_valid', 30)
    max_uses = request.form.get('max_uses', 1)
    bonus_properties = request.form.get('bonus_properties', 0)
    bonus_likes = request.form.get('bonus_likes', 0)
    description = request.form.get('description', '')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin.admin_role)
    if not permissions['can_edit_tariff']:
        db.close()
        return "У вас нет прав", 403
    
    existing = db.query(PromoCode).filter(PromoCode.code == code).first()
    if not existing and code:
        promo = PromoCode(
            code=code,
            tariff=tariff,
            discount_percent=int(discount_percent),
            max_uses=int(max_uses),
            bonus_properties=int(bonus_properties) if bonus_properties else 0,
            bonus_likes=int(bonus_likes) if bonus_likes else 0,
            expires_at=get_tashkent_now() + timedelta(days=int(days_valid)),
            description=description,
            is_active=True
        )
        db.add(promo)
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_tariff_settings', tg_id=tg_id))


@app.route('/webapp/admin/promo/<int:promo_id>/toggle', methods=['POST'])
def webapp_toggle_promo(promo_id):
    tg_id = request.form.get('tg_id')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    promo = db.query(PromoCode).filter(PromoCode.id == promo_id).first()
    if promo:
        promo.is_active = not promo.is_active
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_tariff_settings', tg_id=tg_id))


@app.route('/webapp/admin/promo/<int:promo_id>/delete', methods=['POST'])
def webapp_delete_promo(promo_id):
    tg_id = request.form.get('tg_id')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    promo = db.query(PromoCode).filter(PromoCode.id == promo_id).first()
    if promo:
        db.delete(promo)
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_tariff_settings', tg_id=tg_id))


@app.route('/webapp/admin/properties')
def webapp_properties():
    tg_id = request.args.get('tg_id')
    
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    
    status_filter = request.args.get('status', 'all')
    type_filter = request.args.get('type', 'all')
    district_filter = request.args.get('district', 'all')
    rooms_filter = request.args.get('rooms', 'all')
    source_filter = request.args.get('source', 'all')
    search_query = request.args.get('q', '').strip()
    
    query = db.query(Property)
    
    if status_filter == 'active':
        query = query.filter(Property.status == PropertyStatus.ACTIVE)
    elif status_filter == 'moderation':
        query = query.filter(Property.status == PropertyStatus.MODERATION)
    elif status_filter == 'archive':
        query = query.filter(Property.status == PropertyStatus.ARCHIVE)
    
    if type_filter == 'sale':
        query = query.filter(Property.property_type == PropertyType.SALE)
    elif type_filter == 'rent':
        query = query.filter(Property.property_type == PropertyType.RENT)
    
    if district_filter != 'all':
        query = query.filter(Property.district.ilike(f'%{district_filter}%'))
    
    if rooms_filter != 'all' and rooms_filter.isdigit():
        query = query.filter(Property.rooms == int(rooms_filter))
    
    if source_filter == 'olx':
        query = query.filter(Property.source == 'olx')
    elif source_filter == 'manual':
        query = query.filter(Property.source == 'manual')
    
    if search_query:
        search_pattern = f"%{search_query}%"
        if search_query.isdigit():
            query = query.filter(Property.id == int(search_query))
        else:
            query = query.filter(
                (Property.unique_id.ilike(search_pattern)) |
                (Property.residential_complex.ilike(search_pattern)) |
                (Property.address.ilike(search_pattern)) |
                (Property.olx_id.ilike(search_pattern))
            )
    
    properties = query.order_by(Property.created_at.desc()).limit(100).all()
    
    all_districts = db.query(Property.district).distinct().filter(Property.district.isnot(None)).all()
    districts = sorted([d[0] for d in all_districts if d[0]])
    
    total_count = db.query(Property).count()
    active_count = db.query(Property).filter(Property.status == PropertyStatus.ACTIVE).count()
    moderation_count = db.query(Property).filter(Property.status == PropertyStatus.MODERATION).count()
    olx_count = db.query(Property).filter(Property.source == 'olx').count()
    
    db.close()
    
    return render_template('webapp_properties.html',
        tg_id=tg_id,
        permissions=permissions,
        admin_user=admin_user,
        properties=properties,
        status_filter=status_filter,
        type_filter=type_filter,
        district_filter=district_filter,
        rooms_filter=rooms_filter,
        source_filter=source_filter,
        search_query=search_query,
        districts=districts,
        total_count=total_count,
        active_count=active_count,
        moderation_count=moderation_count,
        olx_count=olx_count,
        now=datetime.utcnow()
    )


@app.route('/webapp/admin/properties/<int:property_id>/view')
def webapp_property_view(property_id):
    tg_id = request.args.get('tg_id')
    
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    prop = db.query(Property).filter(Property.id == property_id).first()
    
    if not prop:
        db.close()
        return "Объект не найден", 404
    
    owner = db.query(User).filter(User.id == prop.owner_id).first()
    photo_ids = prop.photos.split(',') if prop.photos else []
    photos = []
    for pid in photo_ids:
        if pid:
            if pid.startswith('http://') or pid.startswith('https://'):
                photos.append(pid)
            else:
                photos.append(url_for('telegram_photo', file_id=pid))
    
    db.close()
    
    return render_template('webapp_property_view.html',
        tg_id=tg_id,
        permissions=permissions,
        prop=prop,
        owner=owner,
        photos=photos
    )


@app.route('/webapp/admin/properties/<int:property_id>/edit')
def webapp_property_edit(property_id):
    tg_id = request.args.get('tg_id')
    
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    prop = db.query(Property).filter(Property.id == property_id).first()
    
    if not prop:
        db.close()
        return "Объект не найден", 404
    
    photo_ids = prop.photos.split(',') if prop.photos else []
    photos = []
    for pid in photo_ids:
        if pid:
            if pid.startswith('http://') or pid.startswith('https://'):
                photos.append(pid)
            else:
                photos.append(url_for('telegram_photo', file_id=pid))
    
    db.close()
    
    return render_template('webapp_property_edit.html',
        tg_id=tg_id,
        permissions=permissions,
        prop=prop,
        photos=photos
    )


@app.route('/webapp/admin/properties/<int:property_id>/update', methods=['POST'])
def webapp_property_update(property_id):
    tg_id = request.form.get('tg_id')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    prop = db.query(Property).filter(Property.id == property_id).first()
    if prop:
        prop.residential_complex = request.form.get('residential_complex', prop.residential_complex)
        prop.district = request.form.get('district', prop.district)
        prop.address = request.form.get('address', prop.address)
        prop.rooms = int(request.form.get('rooms', prop.rooms or 0)) if request.form.get('rooms') else prop.rooms
        prop.area = float(request.form.get('area', prop.area or 0)) if request.form.get('area') else prop.area
        prop.floor = int(request.form.get('floor', prop.floor or 0)) if request.form.get('floor') else prop.floor
        prop.total_floors = int(request.form.get('total_floors', prop.total_floors or 0)) if request.form.get('total_floors') else prop.total_floors
        prop.price = int(request.form.get('price', prop.price)) if request.form.get('price') else prop.price
        prop.description = request.form.get('description', prop.description)
        prop.phone = request.form.get('phone', prop.phone)
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_property_view', property_id=property_id, tg_id=tg_id))


@app.route('/webapp/admin/properties/<int:property_id>/delete', methods=['POST'])
def webapp_property_delete(property_id):
    tg_id = request.form.get('tg_id')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    prop = db.query(Property).filter(Property.id == property_id).first()
    if prop:
        db.delete(prop)
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_properties', tg_id=tg_id))


@app.route('/webapp/admin/properties/<int:property_id>/reactivate', methods=['POST'])
def webapp_reactivate_property(property_id):
    tg_id = request.form.get('tg_id')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    prop = db.query(Property).filter(Property.id == property_id).first()
    if prop:
        prop.status = PropertyStatus.ACTIVE
        prop.created_at = datetime.utcnow()
        prop.archived_at = None
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_properties', tg_id=tg_id))


@app.route('/webapp/admin/parser')
def webapp_parser():
    tg_id = request.args.get('tg_id')
    
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    
    if not permissions['can_parse']:
        db.close()
        return "У вас нет прав для доступа к парсингу", 403
    
    db.close()
    
    return render_template('webapp_parser.html',
        tg_id=tg_id,
        permissions=permissions,
        admin_user=admin_user,
        parse_history=[]
    )


@app.route('/webapp/admin/parser/single', methods=['POST'])
def webapp_parser_single():
    from olx_parser import OLXParser
    
    data = request.get_json()
    tg_id = data.get('tg_id')
    url = data.get('url', '')
    get_phone = data.get('get_phone', False)
    
    if not tg_id:
        return jsonify({'error': 'Telegram ID не указан'}), 400
    
    if not url or 'olx.uz' not in url:
        return jsonify({'error': 'Неверная ссылка OLX'}), 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return jsonify({'error': 'Доступ запрещён'}), 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    
    if not permissions['can_parse']:
        db.close()
        return jsonify({'error': 'У вас нет прав для парсинга'}), 403
    
    admin_user_id = admin_user.id
    db.close()
    
    try:
        parser = OLXParser()
        listing = parser.parse_listing(url, get_phone=get_phone)
        
        if listing.get('error') and not listing.get('title'):
            return jsonify({'error': f"Ошибка парсинга: {listing.get('error')}"}), 400
        
        db = get_db()
        
        olx_id = listing.get('olx_id')
        if olx_id:
            existing = db.query(Property).filter(Property.olx_id == olx_id).first()
            if existing:
                db.close()
                return jsonify({'error': 'Это объявление уже есть в базе', 'parsed': 1, 'added_to_db': 0, 'skipped_duplicates': 1, 'listings': [listing]}), 200
        
        try:
            price_str = listing.get('price', '0')
            price = int(price_str.replace(' ', '').replace(',', '')) if price_str else 0
        except:
            price = 0
        
        try:
            rooms_count = int(listing.get('rooms')) if listing.get('rooms') else None
        except:
            rooms_count = None
        
        try:
            area_val = float(listing.get('total_area')) if listing.get('total_area') else None
        except:
            area_val = None
        
        try:
            floor_val = int(listing.get('floor')) if listing.get('floor') else None
        except:
            floor_val = None
        
        try:
            total_floors_val = int(listing.get('total_floors')) if listing.get('total_floors') else None
        except:
            total_floors_val = None
        
        photos_list = listing.get('photos', [])
        photos_str = ','.join(photos_list[:10]) if photos_list else ''
        
        furnished_val = listing.get('furnished')
        has_furniture = furnished_val == 'Да' if furnished_val else False
        
        new_property = Property(
            owner_id=admin_user_id,
            property_type=PropertyType.SALE,
            district=listing.get('district') or listing.get('location'),
            address=listing.get('location'),
            rooms=rooms_count,
            floor=floor_val,
            total_floors=total_floors_val,
            area=area_val,
            price=price,
            photos=photos_str,
            description=listing.get('description'),
            status=PropertyStatus.ACTIVE,
            phone=listing.get('phone'),
            seller_name=listing.get('seller_name'),
            housing_type=listing.get('property_type'),
            building_type=listing.get('building_type'),
            renovation=listing.get('renovation'),
            layout=listing.get('layout'),
            has_furniture=has_furniture,
            source='olx',
            olx_id=olx_id,
            olx_url=url
        )
        
        db.add(new_property)
        db.commit()
        db.close()
        
        return jsonify({
            'parsed': 1,
            'added_to_db': 1,
            'skipped_duplicates': 0,
            'skipped_old': 0,
            'listings': [listing]
        })
        
    except Exception as e:
        return jsonify({'error': f'Ошибка: {str(e)}'}), 500


@app.route('/webapp/admin/parser/run', methods=['POST'])
def webapp_parser_run():
    from olx_parser import OLXParser
    
    data = request.get_json()
    tg_id = data.get('tg_id')
    
    if not tg_id:
        return jsonify({'error': 'Telegram ID не указан'}), 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return jsonify({'error': 'Доступ запрещён'}), 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    
    if not permissions['can_parse']:
        db.close()
        return jsonify({'error': 'У вас нет прав для парсинга'}), 403
    
    admin_user_id = admin_user.id
    db.close()
    
    deal_type = data.get('deal_type', 'sale')
    property_type_str = data.get('property_type', 'apartment')
    district = data.get('district', 'all')
    rooms = data.get('rooms', '')
    housing_type = data.get('housing_type', 'all')
    max_listings = data.get('max_listings', 50)
    max_days = data.get('max_days', 7)
    get_phone = data.get('get_phone', False)
    
    try:
        parser = OLXParser()
        
        result = parser.bulk_parse(
            deal_type=deal_type,
            property_type=property_type_str,
            district=district,
            rooms=rooms if rooms else None,
            housing_type=housing_type,
            max_pages=25,
            max_listings=min(max_listings, 1000),
            get_phone=get_phone,
            max_days=max_days if max_days > 0 else None
        )
        
        db = get_db()
        added_count = 0
        skipped_count = 0
        
        prop_type_enum = PropertyType.SALE if deal_type == 'sale' else PropertyType.RENT
        
        skipped_no_phone = 0
        for listing in result.get('listings', []):
            if listing.get('error') and not listing.get('title'):
                continue
            
            phone = listing.get('phone')
            if not phone:
                skipped_no_phone += 1
                continue
            
            olx_id = listing.get('olx_id')
            if olx_id:
                existing = db.query(Property).filter(Property.olx_id == olx_id).first()
                if existing:
                    skipped_count += 1
                    continue
            
            try:
                price_str = listing.get('price', '0')
                price = int(price_str.replace(' ', '').replace(',', '')) if price_str else 0
            except:
                price = 0
            
            try:
                rooms_count = int(listing.get('rooms')) if listing.get('rooms') else None
            except:
                rooms_count = None
            
            try:
                area_val = float(listing.get('total_area')) if listing.get('total_area') else None
            except:
                area_val = None
            
            try:
                floor_val = int(listing.get('floor')) if listing.get('floor') else None
            except:
                floor_val = None
            
            try:
                total_floors_val = int(listing.get('total_floors')) if listing.get('total_floors') else None
            except:
                total_floors_val = None
            
            photos_list = listing.get('photos', [])
            photos_str = ','.join(photos_list[:10]) if photos_list else ''
            
            furnished_val = listing.get('furnished')
            has_furniture = furnished_val == 'Да' if furnished_val else False
            
            new_property = Property(
                owner_id=admin_user_id,
                property_type=prop_type_enum,
                district=listing.get('district') or listing.get('location'),
                address=listing.get('location'),
                rooms=rooms_count,
                floor=floor_val,
                total_floors=total_floors_val,
                area=area_val,
                price=price if price > 0 else 1,
                description=listing.get('description'),
                photos=photos_str,
                status=PropertyStatus.ACTIVE,
                housing_type=listing.get('property_type'),
                building_type=listing.get('building_type'),
                renovation=listing.get('renovation'),
                layout=listing.get('layout'),
                has_furniture=has_furniture,
                phone=listing.get('phone'),
                olx_url=listing.get('url'),
                olx_id=olx_id,
                source='olx',
                seller_name=listing.get('seller_name')
            )
            
            db.add(new_property)
            added_count += 1
        
        db.commit()
        db.close()
        
        result['added_to_db'] = added_count
        result['skipped_duplicates'] = skipped_count
        result['skipped_no_phone'] = skipped_no_phone
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/webapp/admin/parser/run-stream')
def webapp_parser_run_stream():
    from olx_parser import OLXParser
    import json
    
    tg_id = request.args.get('tg_id')
    deal_type = request.args.get('deal_type', 'sale')
    property_type_str = request.args.get('property_type', 'apartment')
    district = request.args.get('district', 'all')
    rooms = request.args.get('rooms', '')
    housing_type = request.args.get('housing_type', 'all')
    max_listings = int(request.args.get('max_listings', 50))
    max_days = int(request.args.get('max_days', 7))
    get_phone = request.args.get('get_phone', 'false') == 'true'
    
    if not tg_id:
        def error_gen():
            yield f"data: {json.dumps({'error': 'Telegram ID не указан'})}\n\n"
        return Response(error_gen(), mimetype='text/event-stream')
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        def error_gen():
            yield f"data: {json.dumps({'error': 'Доступ запрещён'})}\n\n"
        return Response(error_gen(), mimetype='text/event-stream')
    
    permissions = get_admin_permissions(admin_user.admin_role)
    
    if not permissions['can_parse']:
        db.close()
        def error_gen():
            yield f"data: {json.dumps({'error': 'У вас нет прав для парсинга'})}\n\n"
        return Response(error_gen(), mimetype='text/event-stream')
    
    admin_user_id = admin_user.id
    db.close()
    
    def generate():
        parser = OLXParser()
        added_count = 0
        skipped_count = 0
        skipped_no_phone = 0
        
        prop_type_enum = PropertyType.SALE if deal_type == 'sale' else PropertyType.RENT
        
        try:
            for event in parser.parse_generator(
                deal_type=deal_type,
                property_type=property_type_str,
                district=district,
                rooms=rooms if rooms else None,
                housing_type=housing_type,
                max_listings=max_listings,
                get_phone=get_phone,
                max_days=max_days
            ):
                event_type = event.get('event')
                
                if event_type == 'start':
                    yield f"data: {json.dumps({'event': 'start', 'total': event['total'], 'current': 0, 'added': 0})}\n\n"
                
                elif event_type == 'skip':
                    yield f"data: {json.dumps({'event': 'progress', 'current': event['current'], 'total': event['total'], 'added': added_count, 'skipped_old': event.get('skipped_old', 0)})}\n\n"
                
                elif event_type == 'listing':
                    data = event['data']
                    phone = data.get('phone')
                    
                    if not phone:
                        skipped_no_phone += 1
                        yield f"data: {json.dumps({'event': 'progress', 'current': event['current'], 'total': event['total'], 'added': added_count})}\n\n"
                        continue
                    
                    olx_id = data.get('olx_id')
                    db_check = get_db()
                    
                    if olx_id:
                        existing = db_check.query(Property).filter(Property.olx_id == olx_id).first()
                        if existing:
                            skipped_count += 1
                            db_check.close()
                            yield f"data: {json.dumps({'event': 'progress', 'current': event['current'], 'total': event['total'], 'added': added_count, 'skipped_duplicates': skipped_count})}\n\n"
                            continue
                    
                    try:
                        price_str = data.get('price', '0')
                        price = int(price_str.replace(' ', '').replace(',', '')) if price_str else 0
                    except:
                        price = 0
                    
                    try:
                        rooms_count = int(data.get('rooms')) if data.get('rooms') else None
                    except:
                        rooms_count = None
                    
                    try:
                        area_val = float(data.get('total_area')) if data.get('total_area') else None
                    except:
                        area_val = None
                    
                    try:
                        floor_val = int(data.get('floor')) if data.get('floor') else None
                    except:
                        floor_val = None
                    
                    try:
                        total_floors_val = int(data.get('total_floors')) if data.get('total_floors') else None
                    except:
                        total_floors_val = None
                    
                    photos_list = data.get('photos', [])
                    photos_str = ','.join(photos_list[:10]) if photos_list else ''
                    
                    furnished_val = data.get('furnished')
                    has_furniture = furnished_val == 'Да' if furnished_val else False
                    
                    new_property = Property(
                        owner_id=admin_user_id,
                        property_type=prop_type_enum,
                        district=data.get('district') or data.get('location'),
                        address=data.get('location'),
                        rooms=rooms_count,
                        floor=floor_val,
                        total_floors=total_floors_val,
                        area=area_val,
                        price=price if price > 0 else 1,
                        description=data.get('description'),
                        photos=photos_str,
                        status=PropertyStatus.ACTIVE,
                        housing_type=data.get('property_type'),
                        building_type=data.get('building_type'),
                        renovation=data.get('renovation'),
                        layout=data.get('layout'),
                        has_furniture=has_furniture,
                        phone=phone,
                        olx_url=data.get('url'),
                        olx_id=olx_id,
                        source='olx',
                        seller_name=data.get('seller_name')
                    )
                    
                    db_check.add(new_property)
                    db_check.commit()
                    db_check.close()
                    
                    added_count += 1
                    yield f"data: {json.dumps({'event': 'progress', 'current': event['current'], 'total': event['total'], 'added': added_count})}\n\n"
                
                elif event_type == 'error':
                    yield f"data: {json.dumps({'event': 'progress', 'current': event['current'], 'total': event['total'], 'added': added_count, 'error': event.get('error')})}\n\n"
                
                elif event_type == 'complete':
                    yield f"data: {json.dumps({'event': 'complete', 'parsed': event['parsed'], 'added_to_db': added_count, 'skipped_duplicates': skipped_count, 'skipped_old': event.get('skipped_old', 0), 'skipped_no_phone': skipped_no_phone, 'total_found': event['total']})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'error': str(e)})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    })


@app.route('/webapp/admin/stats')
def webapp_stats():
    tg_id = request.args.get('tg_id')
    period = request.args.get('period', 'all')
    
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    
    now = get_tashkent_now()
    period_map = {
        '1h': timedelta(hours=1),
        '24h': timedelta(hours=24),
        '7d': timedelta(days=7),
        '30d': timedelta(days=30),
        'all': None
    }
    
    time_filter = period_map.get(period)
    
    if time_filter:
        since = now - time_filter
        total_users = db.query(User).filter(User.created_at >= since).count()
        total_properties = db.query(Property).filter(Property.created_at >= since).count()
        total_likes = db.query(Like).filter(Like.created_at >= since).count()
        total_matches = db.query(Match).filter(Match.created_at >= since).count()
    else:
        total_users = db.query(User).count()
        total_properties = db.query(Property).count()
        total_likes = db.query(Like).count()
        total_matches = db.query(Match).count()
    
    buyers_count = db.query(User).filter(User.role == UserRole.BUYER).count()
    sellers_count = db.query(User).filter(User.role == UserRole.SELLER).count()
    active_properties = db.query(Property).filter(Property.status == PropertyStatus.ACTIVE).count()
    
    db.close()
    
    return render_template('webapp_stats.html',
        tg_id=tg_id,
        permissions=permissions,
        admin_user=admin_user,
        period=period,
        total_users=total_users,
        total_properties=total_properties,
        total_likes=total_likes,
        total_matches=total_matches,
        buyers_count=buyers_count,
        sellers_count=sellers_count,
        active_properties=active_properties
    )


@app.route('/webapp/admin/check_user/<int:telegram_id>')
def webapp_check_user(telegram_id):
    tg_id = request.args.get('tg_id')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return jsonify({'error': 'Доступ запрещён'}), 403
    
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    db.close()
    
    if not user:
        return jsonify({'error': 'Пользователь с таким ID не найден в системе'})
    
    return jsonify({
        'id': user.id,
        'telegram_id': user.telegram_id,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'username': user.username,
        'is_admin': user.is_admin
    })


@app.route('/webapp/admin/add_admin', methods=['POST'])
def webapp_add_admin():
    tg_id = request.form.get('tg_id')
    new_admin_id = request.form.get('new_admin_id')
    admin_role = request.form.get('admin_role')
    
    db = get_db()
    admin = db.query(User).filter(User.telegram_id == int(tg_id)).first() if tg_id else None
    
    if not admin or not admin.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin.admin_role)
    if not permissions['can_manage_admins']:
        db.close()
        return "У вас нет прав для добавления администраторов", 403
    
    user = db.query(User).filter(User.telegram_id == int(new_admin_id)).first()
    if user and not user.is_admin:
        role_map = {
            'super_admin': AdminRole.SUPER_ADMIN,
            'admin': AdminRole.ADMIN,
            'operator': AdminRole.OPERATOR
        }
        user.is_admin = True
        user.admin_role = role_map.get(admin_role, AdminRole.OPERATOR)
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_admins', tg_id=tg_id))


@app.route('/api/districts')
def api_districts():
    db = get_db()
    districts = db.query(District).all()
    db.close()
    return jsonify([{'id': d.id, 'name': d.name} for d in districts])


@app.route('/api/complexes')
def api_complexes():
    db = get_db()
    complexes = db.query(ResidentialComplex).all()
    db.close()
    return jsonify([{'id': c.id, 'name': c.name, 'district': c.district} for c in complexes])


@app.route('/api/promo/check', methods=['POST'])
def check_promo():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    tg_id = data.get('tg_id')
    
    if not code:
        return jsonify({'valid': False, 'message': 'Введите промокод'})
    
    db = get_db()
    promo = db.query(PromoCode).filter(
        PromoCode.code == code,
        PromoCode.is_active == True
    ).first()
    
    if not promo:
        db.close()
        return jsonify({'valid': False, 'message': 'Промокод не найден или истёк'})
    
    if promo.expires_at and promo.expires_at < get_tashkent_now():
        db.close()
        return jsonify({'valid': False, 'message': 'Срок действия промокода истёк'})
    
    if promo.max_uses > 0 and promo.current_uses >= promo.max_uses:
        db.close()
        return jsonify({'valid': False, 'message': 'Промокод уже использован максимальное количество раз'})
    
    message = promo.description or 'Промокод принят!'
    if promo.discount_percent > 0:
        message = f'Скидка {promo.discount_percent}%! Напишите администратору для активации.'
    elif promo.bonus_days > 0:
        message = f'+{promo.bonus_days} дней бесплатно! Напишите администратору.'
    
    db.close()
    
    return jsonify({
        'valid': True,
        'message': message,
        'action': 'contact_admin',
        'discount': promo.discount_percent,
        'bonus_days': promo.bonus_days
    })


@app.route('/webapp/admin/ads')
def webapp_ads():
    tg_id = request.args.get('tg_id')
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    if not permissions.get('can_manage_ads'):
        db.close()
        return "У вас нет прав для управления рекламой", 403
    
    ads = db.query(Advertisement).order_by(Advertisement.created_at.desc()).all()
    ads_count = len(ads)
    
    db.close()
    
    return render_template('webapp_ads.html',
        ads=ads,
        ads_count=ads_count,
        tg_id=tg_id,
        permissions=permissions,
        admin_user=admin_user
    )


@app.route('/webapp/admin/ads/add', methods=['GET', 'POST'])
def webapp_ads_add():
    tg_id = request.args.get('tg_id') or request.form.get('tg_id')
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    if not permissions.get('can_manage_ads'):
        db.close()
        return "У вас нет прав для управления рекламой", 403
    
    if request.method == 'POST':
        ads_count = db.query(Advertisement).count()
        if ads_count >= 30:
            db.close()
            return "Достигнут лимит в 30 рекламных постов", 400
        
        title = request.form.get('title', '')
        description = request.form.get('description', '')
        media = request.form.get('media', '')
        media_type = request.form.get('media_type', 'photo')
        
        ad = Advertisement(
            title=title,
            description=description,
            media=media,
            media_type=media_type,
            is_active=True
        )
        db.add(ad)
        db.commit()
        db.close()
        
        return redirect(url_for('webapp_ads', tg_id=tg_id))
    
    db.close()
    return render_template('webapp_ads_edit.html',
        ad=None,
        tg_id=tg_id,
        permissions=permissions,
        admin_user=admin_user
    )


@app.route('/webapp/admin/ads/<int:ad_id>/edit', methods=['GET', 'POST'])
def webapp_ads_edit(ad_id):
    tg_id = request.args.get('tg_id') or request.form.get('tg_id')
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    if not permissions.get('can_manage_ads'):
        db.close()
        return "У вас нет прав для управления рекламой", 403
    
    ad = db.query(Advertisement).filter(Advertisement.id == ad_id).first()
    if not ad:
        db.close()
        return "Реклама не найдена", 404
    
    if request.method == 'POST':
        ad.title = request.form.get('title', '')
        ad.description = request.form.get('description', '')
        ad.media = request.form.get('media', '')
        ad.media_type = request.form.get('media_type', 'photo')
        ad.is_active = request.form.get('is_active') == 'on'
        db.commit()
        db.close()
        
        return redirect(url_for('webapp_ads', tg_id=tg_id))
    
    db.close()
    return render_template('webapp_ads_edit.html',
        ad=ad,
        tg_id=tg_id,
        permissions=permissions,
        admin_user=admin_user
    )


@app.route('/webapp/admin/ads/<int:ad_id>/delete', methods=['POST'])
def webapp_ads_delete(ad_id):
    tg_id = request.form.get('tg_id')
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    permissions = get_admin_permissions(admin_user.admin_role)
    if not permissions.get('can_manage_ads'):
        db.close()
        return "У вас нет прав для управления рекламой", 403
    
    ad = db.query(Advertisement).filter(Advertisement.id == ad_id).first()
    if ad:
        db.delete(ad)
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_ads', tg_id=tg_id))


@app.route('/webapp/admin/ads/<int:ad_id>/toggle', methods=['POST'])
def webapp_ads_toggle(ad_id):
    tg_id = request.form.get('tg_id')
    if not tg_id:
        return "Telegram ID не указан", 400
    
    db = get_db()
    admin_user = db.query(User).filter(User.telegram_id == int(tg_id)).first()
    
    if not admin_user or not admin_user.is_admin:
        db.close()
        return "Доступ запрещён", 403
    
    ad = db.query(Advertisement).filter(Advertisement.id == ad_id).first()
    if ad:
        ad.is_active = not ad.is_active
        db.commit()
    db.close()
    
    return redirect(url_for('webapp_ads', tg_id=tg_id))


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
