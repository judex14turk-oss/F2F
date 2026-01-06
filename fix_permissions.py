import sys
import os

# Add current directory to path to find models
sys.path.append(os.getcwd())

from models import SessionLocal, User, AdminRole

def fix_admin_permissions():
    db = SessionLocal()
    try:
        username = 'InvictumMurad'
        user = db.query(User).filter(User.username == username).first()
        
        if not user:
            print(f"User {username} not found!")
            return
            
        print(f"Found user: {user.username} (ID: {user.id})")
        print(f"Current role: {user.admin_role}")
        print(f"Is admin: {user.is_admin}")
        
        # Update to SUPER_ADMIN
        user.is_admin = True
        user.admin_role = AdminRole.SUPER_ADMIN
        
        db.commit()
        print(f"Successfully updated {username} to SUPER_ADMIN")
        
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_admin_permissions()
