import sys
from models import init_db, SessionLocal, User, AdminRole

def fix_admins():
    init_db()
    session = SessionLocal()
    try:
        # Find all admins
        admins = session.query(User).filter(User.is_admin == True).all()
        print(f"Found {len(admins)} admins.")
        
        for admin in admins:
            print(f"Checking user {admin.id} ({admin.first_name})...")
            print(f"  Current Role Value: {admin.admin_role}")
            
            # FORCE UPDATE
            # Assign the Enum object directly
            admin.admin_role = AdminRole.SUPER_ADMIN
            session.commit()
            print(f"  -> Updated to SUPER_ADMIN")
            
        # Verify
        print("\nVerifying...")
        admins = session.query(User).filter(User.is_admin == True).all()
        for admin in admins:
            print(f"User {admin.id}: Role is now {admin.admin_role}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    fix_admins()
