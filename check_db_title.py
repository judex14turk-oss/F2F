from models import init_db, SessionLocal, Property
import sys

def check_latest_property():
    session = SessionLocal()
    try:
        # Get latest property
        prop = session.query(Property).order_by(Property.id.desc()).first()
        if prop:
            print(f"ID: {prop.id}")
            print(f"OLX Title: '{prop.olx_title}'")
            print(f"Residential Complex: '{prop.residential_complex}'")
            print(f"District: '{prop.district}'")
            print(f"Source: '{prop.source}'")
        else:
            print("No properties found.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    check_latest_property()
