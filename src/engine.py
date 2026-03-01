import os
import hashlib
import io
import threading
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
        self._stop_requested = False
        self._lock = threading.Lock()
        
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

    def rfc3339_to_epoch(self, rfc_str):
        """Convierte un timestamp RFC 3339 a epoch float."""
        from datetime import datetime
        try:
            # Google Drive format: 2023-05-24T10:00:00.000Z
            s = rfc_str.replace('Z', '+00:00')
            if '.' in s:
                return datetime.fromisoformat(s).timestamp()
            else:
                # Handle cases without milliseconds
                return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z").timestamp()
        except:
            return 0.0

    def get_remote_files(self, folder_id, current_path=""):
        """Obtiene la lista de archivos de Google Drive recursivamente con paginación robusta."""
        self._init_drive_service()
        remote_files = {}
        query = f"'{folder_id}' in parents and trashed = false"
        
        try:
            page_token = None
            page_count = 0
            while True:
                page_count += 1
                results = self.drive_service.files().list(
                    q=query,
                    pageSize=1000,
                    pageToken=page_token,
                    fields="nextPageToken, files(id, name, modifiedTime, md5Checksum, mimeType)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    spaces='drive'
                ).execute()
                
                items = results.get('files', [])
                for item in items:
                    item_name = item.get('name', 'untitled')
                    item_path = os.path.join(current_path, item_name) if current_path else item_name
                    item_path = item_path.replace('\\', '/')
                    
                    if item.get('mimeType') == 'application/vnd.google-apps.folder':
                        sub_files = self.get_remote_files(item['id'], item_path)
                        if sub_files is None: 
                            return None
                        remote_files.update(sub_files)
                    else:
                        item['relative_path'] = item_path
                        remote_files[item_path] = item
                
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
            
            if not current_path:
                print(f"DEBUG: Escaneo remoto finalizado. Carpetas/Paginas procesadas: {page_count}. Total archivos encontrados: {len(remote_files)}")
            return remote_files
        except Exception as e:
            print(f"Error listando Drive (folder_id={folder_id}): {e}")
            return None

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
            results = self.drive_service.files().list(
                q=query, 
                fields="files(id)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            items = results.get('files', [])
            
            if items:
                current_parent_id = items[0]['id']
            else:
                current_parent_id = self._create_remote_folder(part, current_parent_id)
                if not current_parent_id:
                    return None
        return current_parent_id

    def sync(self, status_callback=None):
        """Ejecuta el ciclo principal de sincronización según la dirección configurada."""
        self._init_drive_service()
        local_folder = self.config.get('local_folder')
        remote_folder_id = self.config.get('remote_folder_id')
        direction = self.config.get('sync_direction') # cloud_to_local, local_to_cloud, bidirectional

        if not local_folder or not remote_folder_id:
            if status_callback: status_callback('ERROR', "Configuración incompleta: Faltan carpetas.")
            print("ERROR: Configuración incompleta: Faltan carpetas.")
            return False

        if status_callback: status_callback('INFO', f"Iniciando Sincronización [{direction}]...")
        print(f"INFO: Iniciando Sincronización [{direction}]...")
        
        with self._lock:
            local_files = self.get_local_files(local_folder)
            remote_files = self.get_remote_files(remote_folder_id)
            
            if remote_files is None:
                if status_callback: status_callback('ERROR', "Falla al obtener archivos remotos. Abortando para evitar borrados accidentales.")
                print("ERROR: Falla al obtener archivos remotos. Abortando.")
                return False
            
            print(f"DEBUG: Archivos locales detectados: {len(local_files)}")
            print(f"DEBUG: Archivos remotos detectados: {len(remote_files)}")
        
        # -- Detección de Renombrado en la Nube (Cloud -> Local) --
        remote_by_id = {info['id']: path for path, info in remote_files.items()}
        all_states = self.tracker.get_all_states()
        for rel_path, drive_id, last_l_mtime, last_d_mtime, last_md5 in all_states:
            if drive_id in remote_by_id:
                new_remote_path = remote_by_id[drive_id].replace('\\', '/')
                if new_remote_path != rel_path:
                    old_local = os.path.join(local_folder, rel_path)
                    new_local = os.path.join(local_folder, new_remote_path)
                    if os.path.exists(old_local):
                        if status_callback: status_callback('INFO', f"Renombrado remoto: {rel_path} -> {new_remote_path}")
                        print(f"INFO: Renombrado remoto: {rel_path} -> {new_remote_path}")
                        try:
                            os.makedirs(os.path.dirname(new_local), exist_ok=True)
                            os.rename(old_local, new_local)
                            self.tracker.delete_file_state(rel_path)
                            self.tracker.upsert_file_state(new_remote_path, drive_id, os.stat(new_local).st_mtime, last_d_mtime, last_md5)
                            if rel_path in local_files:
                                info = local_files.pop(rel_path)
                                info['path'] = new_local
                                local_files[new_remote_path] = info
                        except Exception as e:
                            print(f"ERROR: No se pudo renombrar local: {e}")

        # -- Detección de Renombrado Local (Local -> Cloud) --
        new_local_candidates = [p for p in local_files if self.tracker.get_file_state(p) is None]
        missing_remote_states = [s for s in all_states if s[0] not in local_files and s[1] in remote_by_id]
        
        for new_p in new_local_candidates:
            new_md5 = self.calculate_md5(local_files[new_p]['path'])
            if not new_md5: continue
            for old_p, d_id, last_l, last_d, last_md5 in missing_remote_states:
                if new_md5 == last_md5:
                    if status_callback: status_callback('INFO', f"Renombrado local: {old_p} -> {new_p}")
                    print(f"INFO: Renombrado local: {old_p} -> {new_p}")
                    try:
                        self.drive_service.files().update(fileId=d_id, body={'name': os.path.basename(new_p)}).execute()
                        self.tracker.delete_file_state(old_p)
                        self.tracker.upsert_file_state(new_p, d_id, local_files[new_p]['mtime'], last_d, last_md5)
                        if old_p in remote_files:
                            info = remote_files.pop(old_p)
                            info['name'] = os.path.basename(new_p)
                            remote_files[new_p] = info
                        break
                    except Exception as e:
                        print(f"ERROR: No se pudo renombrar en Drive: {e}")

        all_paths = list(set(local_files.keys()).union(set(remote_files.keys())))
        total_files = len(all_paths)
        processed_files = 0
        self._stop_requested = False

        for rel_path in all_paths:
            if self._stop_requested:
                if status_callback: status_callback('WARNING', "Sincronización cancelada por el usuario.")
                print("WARNING: Sincronización cancelada por el usuario.")
                return False
                
            processed_files += 1
            # Normalizamos separadores (Windows -> /) para que cuadren
            rel_path_norm = rel_path.replace('\\', '/')
            
            if status_callback:
                status_callback('PROGRESS', {
                    'current': processed_files,
                    'total': total_files,
                    'file': rel_path_norm
                })

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
                        if status_callback: status_callback('WARNING', f"Detectado borrado remoto: {rel_path_norm}")
                        print(f"WARNING: Detectado borrado remoto: {rel_path_norm}")
                        try:
                            os.remove(local_info['path'])
                            self.tracker.delete_file_state(rel_path_norm)
                        except Exception as e:
                            if status_callback: status_callback('ERROR', f"Error borrando localmente {rel_path_norm}: {e}")
                            print(f"ERROR: Error borrando localmente {rel_path_norm}: {e}")
                    else:
                        # Nuevo local
                        upload_needed = True
                
                elif remote_exists and not local_exists:
                    if state and state['local_mtime']:
                        # Borrado localmente
                        if status_callback: status_callback('WARNING', f"Detectado borrado local: {rel_path_norm}")
                        print(f"WARNING: Detectado borrado local: {rel_path_norm}")
                        # Habría que borrar en Google Drive (usar files().delete)
                        try:
                            self.drive_service.files().delete(fileId=remote_info['id']).execute()
                            self.tracker.delete_file_state(rel_path_norm)
                        except Exception as e:
                            if status_callback: status_callback('ERROR', f"Error borrando de Drive {rel_path_norm}: {e}")
                            print(f"ERROR: Error borrando de Drive {rel_path_norm}: {e}")
                    else:
                        # Nuevo en la nube
                        download_needed = True
                
                elif local_exists and remote_exists:
                    local_md5 = self.calculate_md5(local_info['path'])
                    remote_md5 = remote_info.get('md5Checksum')
                    
                    if local_md5 != remote_md5:
                        # Conflicto: Gana el más nuevo
                        remote_epoch = self.rfc3339_to_epoch(remote_info.get('modifiedTime'))
                        local_epoch = local_info['mtime']
                        
                        if local_epoch > remote_epoch + 1: # 1s margen de error
                            upload_needed = True
                        elif remote_epoch > local_epoch + 1:
                            download_needed = True

            # -- Ejecución de Operaciones --
            if upload_needed:
                action = "Actualizando" if remote_exists else "Subiendo nuevo"
                if status_callback: status_callback('INFO', f"{action}: {rel_path_norm}")
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
                action = "Actualizando local" if local_exists else "Descargando nuevo"
                if status_callback: status_callback('INFO', f"{action}: {rel_path_norm}")
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

        if status_callback: status_callback('INFO', "Sincronización finalizada.")
        print("INFO: Sincronización finalizada.")
        return True

    def stop(self):
        """Solicita la detención de la sincronización en curso."""
        self._stop_requested = True
