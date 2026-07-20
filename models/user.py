from utils.db import get_user, save_user

class User:
    def __init__(self, user_id):
        self.user_id = user_id
        self.data = get_user(user_id) or {}
    
    def save(self):
        save_user(self.user_id, self.data)
    
    def get_token(self, index=None):
        if index is None:
            index = self.data.get('default_token_index', 0)
        tokens = self.data.get('tokens', [])
        if tokens and index < len(tokens):
            return tokens[index]
        return None
    
    def add_token(self, token):
        tokens = self.data.get('tokens', [])
        tokens.append(token)
        self.data['tokens'] = tokens
        self.save()
    
    def remove_token(self, index):
        tokens = self.data.get('tokens', [])
        if tokens and index < len(tokens):
            del tokens[index]
            self.data['tokens'] = tokens
            self.save()