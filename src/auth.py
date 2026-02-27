import os
import sys
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.paths import resource_path, user_data_dir


class GoogleAuth:
    # If modifying these scopes, delete the file token.json.
    SCOPES = ['https://www.googleapis.com/auth/drive']

    def __init__(self, token_path=None, credentials_path=None):
        if token_path is None:
            token_path = os.path.join(user_data_dir(), 'token.json')
        if credentials_path is None:
            # credentials.json is a read-only bundled resource
            credentials_path = resource_path('credentials.json')
        self.token_path = token_path
        self.credentials_path = credentials_path
        self.creds = None
        self.load_credentials()

    def load_credentials(self):
        """Intenta cargar credenciales guardadas si existen."""
        if os.path.exists(self.token_path):
            try:
                self.creds = Credentials.from_authorized_user_file(self.token_path, self.SCOPES)
            except Exception as e:
                print(f"Error cargando token guardado: {e}")
                self.creds = None
        return self.creds

    def authenticate(self):
        """Maneja el flujo de OAuth2 para obtener o renovar credenciales."""
        self.load_credentials()

        
        # If there are no (valid) credentials available, let the user log in.
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(f"No se encontró el archivo de credenciales de Google API: {self.credentials_path}. Por favor, descárgalo de tu consola de Google Cloud.")
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, self.SCOPES)
                self.creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(self.token_path, 'w') as token:
                token.write(self.creds.to_json())
        
        return self.creds

    def logout(self):
        """Cierra sesión eliminando el token guardado."""
        self.creds = None
        if os.path.exists(self.token_path):
            try:
                os.remove(self.token_path)
                return True
            except Exception as e:
                print(f"Error eliminando token: {e}")
                return False
        return True

    def get_drive_service(self):
        """Devuelve una instancia del servicio de Google Drive."""
        if not self.creds:
            self.authenticate()
        return build('drive', 'v3', credentials=self.creds)

if __name__ == '__main__':
    # Prueba rápida del token si se ejecuta este script directamente
    try:
        auth = GoogleAuth()
        service = auth.get_drive_service()
        print("¡Autenticación exitosa! Servicio de Drive listo.")
    except Exception as e:
        print(f"Error de autenticación: {e}")
