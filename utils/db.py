import sqlite3
import os
import json
from utils.security import encrypt, decrypt

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'config.db')

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    # Tabela principal de usuários (token criptografado)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            tokens TEXT,  -- JSON criptografado com lista de tokens
            default_token_index INTEGER DEFAULT 0,
            chat_id INTEGER,
            farm_chat_id INTEGER,
            auto_farming INTEGER DEFAULT 0,
            farm_interval INTEGER DEFAULT 120,
            farm_message TEXT,
            sleep_mode INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Tabela de tarefas agendadas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_type TEXT,  -- 'clean', 'farm', 'backup', 'voice'
            params TEXT,     -- JSON com parâmetros
            cron_expression TEXT,  -- ou intervalo em segundos
            next_run TIMESTAMP,
            active INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    # Tabela de logs de atividades
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        data = dict(row)
        # Descriptografa tokens
        if data['tokens']:
            data['tokens'] = json.loads(decrypt(data['tokens']))
        else:
            data['tokens'] = []
        return data
    return None

def save_user(user_id, data):
    conn = get_connection()
    cursor = conn.cursor()
    # Criptografa tokens antes de salvar
    tokens_enc = encrypt(json.dumps(data.get('tokens', [])))
    cursor.execute('''
        INSERT OR REPLACE INTO users (
            user_id, tokens, default_token_index, chat_id, farm_chat_id,
            auto_farming, farm_interval, farm_message, sleep_mode, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (
        user_id,
        tokens_enc,
        data.get('default_token_index', 0),
        data.get('chat_id'),
        data.get('farm_chat_id'),
        data.get('auto_farming', 0),
        data.get('farm_interval', 120),
        data.get('farm_message', ''),
        data.get('sleep_mode', 0)
    ))
    conn.commit()
    conn.close()