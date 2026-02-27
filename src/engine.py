import os
import hashlib
import io
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from src.auth import GoogleAuth
from src.tracker import SyncTracker
from src.config import ConfigManager

class SyncEngine:
    def __init__(self):
        self.auth = GoogleAuth()
        self.drive_service = None # Carga diferida
        self.tracker = SyncTracker()
        self.config = ConfigManager()
        
    def _init_drive_service(self):
        if not self.drive_service:
            self.drive_service = self.auth.get_drive_service()

    def get_local_files(self, local_folder):
        """Escanea el directorio local y retorna un dict con metadatos."""
        local_files = {}
        for root, _, files in os.walk(local_folder):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, local_folder)
                # Omitir archivos ocultos o de sistema si es necesario
                if file.startswith('.') or rel_path.startswith('.'):
                    continue
                
                stat = os.stat(full_path)
                local_files[rel_path] = {
                    'path': full_path,
                    'mtime': stat.st_mtime,
                    'size': stat.st_size
                }
        return local_files

    def calculate_md5(self, filepath):
        """Calcula el hash MD5 local para verificar cambios de contenido."""
        hash_md5 = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except:
            return None

    def get_remote_files(self, folder_id, current_path=""):
        """Obtiene la lista de archivos de Google Drive recursivamente."""
        self._init_drive_service()
        remote_files = {}
        query = f"'{folder_id}' in parents and trashed = false"
        
        try:
            results = self.drive_service.files().list(
                q=query,
                pageSize=1000,
                fields="nextPageToken, files(id, name, modifiedTime, md5Checksum, mimeType)"
            ).execute()
            
            items = results.get('files', [])
            for item in items:
                item_path = os.path.join(current_path, item['name']) if current_path else item['name']
                # Normalizar path para comparación multiplataforma
                item_path = item_path.replace('\\', '/')
                
                if item['mimeType'] == 'application/vnd.google-apps.folder':
                    # Llamada recursiva
                    sub_files = self.get_remote_files(item['id'], item_path)
                    remote_files.update(sub_files)
                else:
                    remote_files[item_path] = item
                    # Guardamos también el ID del padre (para subidas futuras de este archivo no funciona directo, mejor lo resolvemos luego)
                    # Añadimos relative_path al item por conveniencia
                    item['relative_path'] = item_path
                    
            return remote_files
        except Exception as e:
            print(f"Error listando Drive recursivamente: {e}")
            return {}

    def _create_remote_folder(self, folder_name, parent_id):
        """Crea una carpeta en Google Drive y devuelve su ID."""
        self._init_drive_service()
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        try:
            folder = self.drive_service.files().create(body=file_metadata, fields='id').execute()
            print(f"Subcarpeta remota creada: {folder_name} (ID: {folder.get('id')})")
            return folder.get('id')
        except Exception as e:
            print(f"Error creando carpeta remota {folder_name}: {e}")
            return None

    def _upload_file(self, local_filepath, remote_filename, parent_id, drive_file_id=None):
        """Sube un archivo nuevo o actualiza uno existente en Google Drive."""
        self._init_drive_service()
        file_metadata = {'name': remote_filename}
        
        # Determinar el mimetype, fallback genérico
        # Se asume que el modulo mimetypes se podría importar si se desea precisión, pero Drive API auto-detecta razonablemente bien
        media = MediaFileUpload(local_filepath, resumable=True)
        
        try:
            if drive_file_id:
                # Actualizar archivo existente
                file = self.drive_service.files().update(
                    fileId=drive_file_id,
                    media_body=media,
                    fields='id, modifiedTime, md5Checksum'
                ).execute()
                print(f"Archivo actualizado: {remote_filename}")
            else:
                # Subir nuevo archivo
                file_metadata['parents'] = [parent_id]
                file = self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, modifiedTime, md5Checksum'
                ).execute()
                print(f"Archivo subido: {remote_filename}")
            return file
        except Exception as e:
            print(f"Error subiendo {remote_filename}: {e}")
            return None

    def _download_file(self, drive_file_id, local_filepath):
        """Descarga un archivo desde Google Drive al disco local."""
        self._init_drive_service()
        
        # Asegurar que el directorio local existe
        os.makedirs(os.path.dirname(local_filepath), exist_ok=True)
        
        request = self.drive_service.files().get_media(fileId=drive_file_id)
        fh = io.FileIO(local_filepath, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        try:
            while done is False:
                status, done = downloader.next_chunk()
            print(f"Archivo descargado exitosamente: {local_filepath}")
            return True
        except Exception as e:
            print(f"Error descargando {local_filepath}: {e}")
            return False

    def _resolve_remote_parent_id(self, local_rel_path, root_folder_id):
        """Busca o crea la estructura de carpetas en Drive para alojar un archivo."""
        parts = os.path.dirname(local_rel_path).replace('\\', '/').split('/')
        current_parent_id = root_folder_id
        
        if not parts or parts[0] == '':
            return current_parent_id
            
        for part in parts:
            query = f"'{current_parent_id}' in parents and name = '{part}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            results = self.drive_service.files().list(q=query, fields="files(id)").execute()
            items = results.get('files', [])
            
            if items:
                current_parent_id = items[0]['id']
            else:
                current_parent_id = self._create_remote_folder(part, current_parent_id)
                if not current_parent_id:
                    return None
        return current_parent_id

    def sync(self):
        """Ejecuta el ciclo principal de sincronización según la dirección configurada."""
        self._init_drive_service()
        local_folder = self.config.get('local_folder')
        remote_folder_id = self.config.get('remote_folder_id')
        direction = self.config.get('sync_direction') # cloud_to_local, local_to_cloud, bidirectional

        if not local_folder or not remote_folder_id:
            print("Configuración incompleta: Faltan carpetas.")
            return False

        print(f"Iniciando Sincronización [{direction}]...")
        
        local_files = self.get_local_files(local_folder)
        remote_files = self.get_remote_files(remote_folder_id)
        
        all_paths = set(local_files.keys()).union(set(remote_files.keys()))
        
        for rel_path in all_paths:
            # Normalizamos separadores (Windows -> /) para que cuadren
            rel_path_norm = rel_path.replace('\\', '/')
            
            local_info = local_files.get(rel_path)
            remote_info = remote_files.get(rel_path_norm)
            state = self.tracker.get_file_state(rel_path_norm)
            
            local_exists = local_info is not None
            remote_exists = remote_info is not None
            
            upload_needed = False
            download_needed = False
            
            if direction == 'local_to_cloud':
                if local_exists:
                    if not remote_exists:
                        upload_needed = True
                    else:
                        local_md5 = self.calculate_md5(local_info['path'])
                        if local_md5 != remote_info.get('md5Checksum'):
                            upload_needed = True
                elif remote_exists and state:
                    # El archivo fue borrado localmente, podríamos borrarlo en la nube,
                    # pbt por ahora en este flujo de backup básico simplemente ignoramos borrado.
                    pass
            
            elif direction == 'cloud_to_local':
                if remote_exists:
                    if not local_exists:
                        download_needed = True
                    else:
                        local_md5 = self.calculate_md5(local_info['path'])
                        if local_md5 != remote_info.get('md5Checksum'):
                            # Asumimos que la nube manda
                            download_needed = True
            
            elif direction == 'bidirectional':
                if local_exists and not remote_exists:
                    if state and state['drive_id']:
                        # Borrado en la nube
                        print(f"Detectado borrado remoto: {rel_path_norm}")
                        os.remove(local_info['path'])
                        self.tracker.delete_file_state(rel_path_norm)
                    else:
                        # Nuevo local
                        upload_needed = True
                
                elif remote_exists and not local_exists:
                    if state and state['local_mtime']:
                        # Borrado localmente
                        print(f"Detectado borrado local: {rel_path_norm}")
                        # Habría que borrar en Google Drive (usar files().delete)
                        try:
                            self.drive_service.files().delete(fileId=remote_info['id']).execute()
                            self.tracker.delete_file_state(rel_path_norm)
                        except Exception as e:
                            print(f"Error borrando de Drive {rel_path_norm}: {e}")
                    else:
                        # Nuevo en la nube
                        download_needed = True
                
                elif local_exists and remote_exists:
                    local_md5 = self.calculate_md5(local_info['path'])
                    remote_md5 = remote_info.get('md5Checksum')
                    
                    if local_md5 != remote_md5:
                        # Conflicto, resolver por fecha
                        # Convertimos mtime a str comparable superficialmente o simplemente usamos el state
                        if state:
                            if local_info['mtime'] > state['local_mtime'] + 2: # +2 para margen de error filesystem
                                upload_needed = True
                            else:
                                download_needed = True
                        else:
                            # Sin state, subimos local (arbitrario)
                            upload_needed = True

            # -- Ejecución de Operaciones --
            if upload_needed:
                parent_id = self._resolve_remote_parent_id(rel_path_norm, remote_folder_id)
                if parent_id:
                    file_id_to_update = remote_info['id'] if remote_info else None
                    filename_only = os.path.basename(rel_path_norm)
                    res = self._upload_file(local_info['path'], filename_only, parent_id, file_id_to_update)
                    if res:
                        self.tracker.upsert_file_state(
                            relative_path=rel_path_norm,
                            drive_id=res.get('id'),
                            local_mtime=os.stat(local_info['path']).st_mtime,
                            drive_mtime=res.get('modifiedTime'),
                            md5_checksum=res.get('md5Checksum')
                        )
            
            elif download_needed:
                local_path = os.path.join(local_folder, rel_path_norm)
                res = self._download_file(remote_info['id'], local_path)
                if res:
                    # Se descargó, recalculamos MD5 local para igualarlo al remoto (o confiamos en el del api)
                    local_md5 = self.calculate_md5(local_path)
                    self.tracker.upsert_file_state(
                        relative_path=rel_path_norm,
                        drive_id=remote_info['id'],
                        local_mtime=os.stat(local_path).st_mtime,
                        drive_mtime=remote_info.get('modifiedTime'),
                        md5_checksum=local_md5
                    )

        print("Sincronización finalizada.")
        return True
