import sys
from models import init_db, SessionLocal, User, AdminRole
from app import get_admin_permissions

def diagnose():
    print("--- DIAGNOSTIC START ---")
    session = SessionLocal()
    try:
        # Find all admins
        admins = session.query(User).filter(User.is_admin == True).all()
        print(f"Found {len(admins)} admins in DB.")
        
        for admin in admins:
            print(f"\nUser ID: {admin.id}, Name: {admin.first_name}")
            print(f"  Telegram ID: {admin.telegram_id}")
            print(f"  DB Role Value (raw): {admin.admin_role}")
            print(f"  DB Role Type: {type(admin.admin_role)}")
            
            # Check string conversion
            role_str = str(admin.admin_role)
            print(f"  str(role): '{role_str}'")
            
            # Test permissions
            perms = get_admin_permissions(admin.admin_role, telegram_id=admin.telegram_id)
            print(f"  get_admin_permissions result:")
            print(f"    role_name: {perms.get('role_name')}")
            print(f"    can_parse: {perms.get('can_parse')}")
            
            if perms.get('role_name') == 'Нет доступа':
                print("  [FAIL] Permission denied for this user.")
            else:
                print("  [PASS] User has access.")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()
    print("\n--- DIAGNOSTIC END ---")

if __name__ == "__main__":
    diagnose()
