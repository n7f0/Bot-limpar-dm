# utils/db.py (modificado)
import sqlite3
import os
import json

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'config.db')

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            tokens TEXT DEFAULT '[]',
            active_token_index INTEGER DEFAULT 0,
            channel_id INTEGER,
            webhook_url TEXT,
            stats_cleared INTEGER DEFAULT 0,
            stats_farmed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            presence_type INTEGER DEFAULT 0,
            presence_name TEXT DEFAULT '',
            presence_state TEXT DEFAULT '',
            presence_url TEXT DEFAULT '',
            presence_large_image TEXT DEFAULT '',
            presence_large_text TEXT DEFAULT '',
            presence_small_image TEXT DEFAULT '',
            presence_small_text TEXT DEFAULT ''
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS persistent_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_type TEXT,
            payload TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_user_data(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        data = dict(row)
        data['tokens'] = json.loads(data['tokens'])
        return data
    # retorna com defaults incluindo presence
    return {
        'tokens': [],
        'active_token_index': 0,
        'channel_id': None,
        'webhook_url': None,
        'stats_cleared': 0,
        'stats_farmed': 0,
        'presence_type': 0,
        'presence_name': '',
        'presence_state': '',
        'presence_url': '',
        'presence_large_image': '',
        'presence_large_text': '',
        'presence_small_image': '',
        'presence_small_text': ''
    }

def save_user_data(user_id: int, **kwargs):
    data = get_user_data(user_id)
    data.update(kwargs)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (
            user_id, tokens, active_token_index, channel_id, webhook_url, stats_cleared, stats_farmed, updated_at,
            presence_type, presence_name, presence_state, presence_url,
            presence_large_image, presence_large_text, presence_small_image, presence_small_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        json.dumps(data.get('tokens', [])),
        data.get('active_token_index', 0),
        data.get('channel_id'),
        data.get('webhook_url'),
        data.get('stats_cleared', 0),
        data.get('stats_farmed', 0),
        data.get('presence_type', 0),
        data.get('presence_name', ''),
        data.get('presence_state', ''),
        data.get('presence_url', ''),
        data.get('presence_large_image', ''),
        data.get('presence_large_text', ''),
        data.get('presence_small_image', ''),
        data.get('presence_small_text', '')
    ))
    conn.commit()
    conn.close()

def reset_user_data(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()