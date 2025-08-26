import json
import os

class Config:
    def __init__(self, config_file='config/default_config.json'):
        self.config_file = config_file
        self.settings = self.load_config()
        self.load_credentials()

    def load_config(self):
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")
        
        with open(self.config_file, 'r') as file:
            return json.load(file)
            
    def load_credentials(self):
        """Load credentials from separate credentials file and merge with config"""
        credentials_file = "config/credentials.json"
        if os.path.exists(credentials_file):
            try:
                with open(credentials_file, 'r') as file:
                    credentials = json.load(file)
                    
                # Add API key to gemini config if present
                if 'api_key' in credentials and credentials['api_key']:
                    if 'gemini' in self.settings:
                        self.settings['gemini']['api_key'] = credentials['api_key']
            except Exception as e:
                print(f"Warning: Could not load credentials: {str(e)}")

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value

    def save(self):
        with open(self.config_file, 'w') as file:
            json.dump(self.settings, file, indent=4)