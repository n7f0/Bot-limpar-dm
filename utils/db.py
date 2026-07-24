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
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    return {'tokens': [], 'active_token_index': 0, 'channel_id': None, 'webhook_url': None, 'stats_cleared': 0, 'stats_farmed': 0}

def save_user_data(user_id: int, **kwargs):
    data = get_user_data(user_id)
    data.update(kwargs)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (
            user_id, tokens, active_token_index, channel_id, webhook_url, stats_cleared, stats_farmed, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        user_id, json.dumps(data.get('tokens', [])), data.get('active_token_index', 0),
        data.get('channel_id'), data.get('webhook_url'), data.get('stats_cleared', 0), data.get('stats_farmed', 0)
    ))
    conn.commit()
    conn.close()

def reset_user_data(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
