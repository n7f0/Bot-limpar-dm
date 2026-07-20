import json
from utils.db import get_connection

class User:
    def __init__(self, user_id):
        self.user_id = user_id
        self.data = self._load()
    
    def _load(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (self.user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            data = dict(row)
            if data.get('tokens'):
                data['tokens'] = json.loads(data['tokens'])
            else:
                data['tokens'] = []
            return data
        return {'tokens': [], 'default_token_index': 0}
    
    def save(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (
                user_id, tokens, default_token_index, chat_id, farm_chat_id,
                auto_farming, farm_interval, farm_message, sleep_mode, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            self.user_id,
            json.dumps(self.data.get('tokens', [])),
            self.data.get('default_token_index', 0),
            self.data.get('chat_id'),
            self.data.get('farm_chat_id'),
            self.data.get('auto_farming', 0),
            self.data.get('farm_interval', 120),
            self.data.get('farm_message', ''),
            self.data.get('sleep_mode', 0)
        ))
        conn.commit()
        conn.close()
    
    def get_token(self, index=None):
        if index is None:
            index = self.data.get('default_token_index', 0)
        tokens = self.data.get('tokens', [])
        if tokens and index < len(tokens):
            return tokens[index]
        return None