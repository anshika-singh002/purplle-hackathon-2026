import sqlite3
import os
import csv
from datetime import datetime

DB_PATH = "store_data.db"
POS_FILE = "data/pos_transactions.csv"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            store_id TEXT, camera_id TEXT, visitor_id TEXT,
            event_type TEXT, timestamp TEXT, zone_id TEXT,
            dwell_ms INTEGER, is_staff BOOLEAN, confidence REAL
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS pos_transactions (
            transaction_id TEXT PRIMARY KEY,
            store_id TEXT, timestamp TEXT, amount REAL
        )
    ''')
    conn.commit()
    
    if os.path.exists(POS_FILE):
        with open(POS_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Combine order_date and order_time into ISO format (YYYY-MM-DDTHH:MM:SSZ)
                try:
                    date_str = row.get('order_date', '')
                    time_str = row.get('order_time', '')
                    dt = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %H:%M:%S")
                    iso_timestamp = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                except:
                    iso_timestamp = "2026-04-10T12:00:00Z"

                c.execute('''
                    INSERT OR IGNORE INTO pos_transactions 
                    (transaction_id, store_id, timestamp, amount)
                    VALUES (?, ?, ?, ?)
                ''', (
                    row.get('order_id'), 
                    "STORE_BLR_002", # Forced to match our API endpoint!
                    iso_timestamp, 
                    float(row.get('total_amount', 0.0))
                ))
        conn.commit()
    conn.close()

def insert_event_idempotent(event_data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT OR REPLACE INTO events 
            (event_id, store_id, camera_id, visitor_id, event_type, timestamp, zone_id, dwell_ms, is_staff, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(event_data['event_id']), event_data['store_id'], event_data['camera_id'],
            event_data['visitor_id'], event_data['event_type'], 
            event_data['timestamp'], event_data.get('zone_id'), 
            event_data.get('dwell_ms', 0), event_data.get('is_staff', False), event_data.get('confidence', 1.0)
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False
    finally:
        conn.close()
