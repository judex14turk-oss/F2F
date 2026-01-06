import os
import sys
from dotenv import load_dotenv

load_dotenv()

from models import SessionLocal, Property

olx_id = "4fHQr"

db = SessionLocal()
prop = db.query(Property).filter(Property.olx_id == olx_id).first()

if prop:
    print(f"Property found!")
    print(f"ID: {prop.id}")
    print(f"OLX ID: {prop.olx_id}")
    print(f"Title: {prop.olx_title or 'N/A'}")
    print(f"Rooms: {prop.rooms}")
    print(f"Area: {prop.area}")
    print(f"Floor: {prop.floor}")
    print(f"Total Floors: {prop.total_floors}")
    print(f"Price: {prop.price}")
    print(f"District: {prop.district}")
    print(f"Created: {prop.created_at}")
    print(f"Source: {prop.source}")
else:
    print(f"Property with OLX ID '{olx_id}' not found in database")
    print("\nSearching all OLX properties...")
    all_olx = db.query(Property).filter(Property.source == 'olx').order_by(Property.created_at.desc()).limit(5).all()
    print(f"\nLast 5 OLX properties:")
    for p in all_olx:
        print(f"  - ID: {p.id}, OLX_ID: {p.olx_id}, Rooms: {p.rooms}, Area: {p.area}, Title: {(p.olx_title or '')[:50]}")

db.close()
