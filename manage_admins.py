import sys
from models import init_db, SessionLocal, User, AdminRole

def list_users(session):
    users = session.query(User).all()
    print("\n👥 Список пользователей:")
    print(f"{'ID':<5} {'TG ID':<15} {'Имя':<20} {'Роль':<15} {'Админ-роль'}")
    print("-" * 70)
    for user in users:
        admin_role_val = user.admin_role.value if user.admin_role else 'None'
        print(f"{user.id:<5} {user.telegram_id:<15} {user.first_name or 'No Name':<20} {user.role.value:<15} {admin_role_val}")
    return users

def promote_user(session, user_id):
    user = session.query(User).filter(User.id == user_id).first()
    if user:
        user.is_admin = True
        user.admin_role = AdminRole.SUPER_ADMIN
        session.commit()
        print(f"\n✅ Пользователь {user.first_name} (ID: {user.id}) теперь SUPER_ADMIN!")
    else:
        print("\n❌ Пользователь не найден")

def main():
    init_db()
    session = SessionLocal()
    
    try:
        users = list_users(session)
        
        print("\nВведите ID пользователя (из первой колонки), чтобы сделать его Старшим Администратором")
        print("Или нажмите Enter для выхода")
        
        choice = input("ID > ")
        if choice.isdigit():
            promote_user(session, int(choice))
            
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    main()
