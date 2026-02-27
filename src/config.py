import json
import os

from src.paths import user_data_dir


CONFIG_FILE = os.path.join(user_data_dir(), 'config.json')

DEFAULT_CONFIG = {
    'local_folder': '',
    'remote_folder_id': '',
    'remote_folder_name': '',
    'sync_direction': 'bidirectional',  # local_to_cloud, cloud_to_local, bidirectional
    'sync_frequency_minutes': 15,
    'sync_time_unit': 'minutes', # 'minutes' or 'seconds'
    'autostart': True,  # Inicio con el sistema operativo
    'last_sync': None
}

class ConfigManager:
    _shared_state = {}

    def __init__(self):
        self.__dict__ = self._shared_state
        if not hasattr(self, 'config'):
            self.config = DEFAULT_CONFIG.copy()
            self.load_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded = json.load(f)
                    self.config.update(loaded)
            except Exception as e:
                print(f"Error cargando config: {e}")

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error guardando config: {e}")

    def get(self, key):
        return self.config.get(key)
    
    def set(self, key, value):
        self.config[key] = value
        self.save_config()
