import sqlite3
import os
import csv

DB_PATH = "store_data.db"
# Updated to the real POS file you discovered!
POS_FILE = "/Users/anshikasingh/Documents/VITB/Resume Projects/Purplle Hackathon/Brigade_Bangalore_10_April_26 (1)bc6219c.csv"

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
            # Find the actual column names (they might differ slightly from the PDF)
            headers = reader.fieldnames
            
            # Map the columns flexibly based on what the real CSV uses
            tx_col = next((h for h in headers if 'transaction' in h.lower() or 'id' in h.lower()), headers[0])
            store_col = next((h for h in headers if 'store' in h.lower()), headers[1] if len(headers)>1 else None)
            time_col = next((h for h in headers if 'time' in h.lower() or 'date' in h.lower()), headers[2] if len(headers)>2 else None)
            amt_col = next((h for h in headers if 'amount' in h.lower() or 'total' in h.lower() or 'price' in h.lower()), headers[3] if len(headers)>3 else None)
            
            for row in reader:
                c.execute('''
                    INSERT OR IGNORE INTO pos_transactions 
                    (transaction_id, store_id, timestamp, amount)
                    VALUES (?, ?, ?, ?)
                ''', (row.get(tx_col), row.get(store_col, 'STORE_BLR_002'), row.get(time_col), row.get(amt_col, 0.0)))
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
            event_data['visitor_id'], event_data['event_type'].value, 
            event_data['timestamp'].isoformat(), event_data['zone_id'], 
            event_data['dwell_ms'], event_data['is_staff'], event_data['confidence']
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False
    finally:
        conn.close()
