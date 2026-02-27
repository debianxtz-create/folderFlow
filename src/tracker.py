import sqlite3
import os

from src.paths import user_data_dir

DB_FILE = os.path.join(user_data_dir(), 'sync.db')

class SyncTracker:
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.init_db()

    def init_db(self):
        cursor = self.conn.cursor()
        # id: Identificador auto-incremental
        # relative_path: Ruta del archivo relativa a la carpeta base local
        # drive_id: ID devuelto por Google Drive
        # local_mtime: Última fecha de modificación local registrada en epoch
        # drive_mtime: Última fecha de modificación remota devuelta por Drive RFC 3339 convertida
        # md5_checksum: Hash del archivo para validar si el contenido ha cambiado sin depender solo de la fecha
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                relative_path TEXT UNIQUE NOT NULL,
                drive_id TEXT,
                local_mtime REAL,
                drive_mtime TEXT,
                md5_checksum TEXT
            )
        ''')
        self.conn.commit()

    def get_file_state(self, relative_path):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM file_state WHERE relative_path = ?', (relative_path,))
        row = cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'relative_path': row[1],
                'drive_id': row[2],
                'local_mtime': row[3],
                'drive_mtime': row[4],
                'md5_checksum': row[5]
            }
        return None

    def upsert_file_state(self, relative_path, drive_id=None, local_mtime=None, drive_mtime=None, md5_checksum=None):
        """Inserta o actualiza el registro de un archivo."""
        existing = self.get_file_state(relative_path)
        cursor = self.conn.cursor()
        if existing:
            # Mantener los valores anteriores si no se proveen nuevos
            d_id = drive_id if drive_id is not None else existing['drive_id']
            l_mt = local_mtime if local_mtime is not None else existing['local_mtime']
            d_mt = drive_mtime if drive_mtime is not None else existing['drive_mtime']
            md5 = md5_checksum if md5_checksum is not None else existing['md5_checksum']
            
            cursor.execute('''
                UPDATE file_state 
                SET drive_id = ?, local_mtime = ?, drive_mtime = ?, md5_checksum = ?
                WHERE relative_path = ?
            ''', (d_id, l_mt, d_mt, md5, relative_path))
        else:
            cursor.execute('''
                INSERT INTO file_state (relative_path, drive_id, local_mtime, drive_mtime, md5_checksum)
                VALUES (?, ?, ?, ?, ?)
            ''', (relative_path, drive_id, local_mtime, drive_mtime, md5_checksum))
        self.conn.commit()

    def delete_file_state(self, relative_path):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM file_state WHERE relative_path = ?', (relative_path,))
        self.conn.commit()
    
    def get_all_states(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT relative_path, drive_id, local_mtime, drive_mtime, md5_checksum FROM file_state')
        return cursor.fetchall()

    def close(self):
        self.conn.close()
