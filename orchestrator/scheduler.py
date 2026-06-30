import time
from datetime import datetime
from main import main

POLL_SECONDS = 60

while True:
    try:
        print(f"\n[{datetime.now()}] Revisando procesos...")
        main()

    except Exception as e:
        print(f"Error scheduler: {e}")

    time.sleep(POLL_SECONDS)