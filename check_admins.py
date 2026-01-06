from models import init_db, SessionLocal, User, AdminRole

def check_admins():
    init_db()
    session = SessionLocal()
    try:
        admins = session.query(User).filter(User.is_admin == True).all()
        print(f"Found {len(admins)} admins:")
        for admin in admins:
            print(f"ID: {admin.id}, TG_ID: {admin.telegram_id}, Name: {admin.first_name} {admin.last_name}, Role: {admin.admin_role}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    check_admins()
