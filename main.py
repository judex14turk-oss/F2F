import asyncio
import threading
import os
from bot import main as bot_main
from app import app
from models import init_db

def run_flask():
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def run_bot():
    asyncio.run(bot_main())

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    run_bot()
