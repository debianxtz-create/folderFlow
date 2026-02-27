import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QFileDialog, 
                             QComboBox, QSpinBox, QMessageBox, QDialog, QListWidget, QListWidgetItem,
                             QTabWidget, QTextEdit, QSystemTrayIcon, QMenu, QStyle, QCheckBox)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QObject
import threading

from src.config import ConfigManager
from src.auth import GoogleAuth
from src.scheduler import SyncScheduler
from src.paths import resource_path
from src.autostart import enable_autostart, disable_autostart, is_autostart_enabled

class WorkerSignals(QObject):
    sync_finished = pyqtSignal(bool, str)
    sync_progress = pyqtSignal(str)

class CloudFolderPickerDialog(QDialog):
    def __init__(self, auth, parent=None):
        super().__init__(parent)
        self.auth = auth
        self.drive_service = None
        self.selected_folder_id = None
        self.selected_folder_name = None
        self.current_parent = 'root'
        self.history = [] # Para navegar atrás
        
        self.setWindowTitle("Seleccionar Carpeta de Google Drive")
        self.setMinimumSize(400, 300)
        self.init_ui()
        self.load_folders()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Header (Botón atrás + path actual)
        header_layout = QHBoxLayout()
        self.btn_back = QPushButton("⬅️ Atrás")
        self.btn_back.clicked.connect(self.go_back)
        self.btn_back.setEnabled(False)
        self.lbl_current_path = QLabel("Raíz")
        
        header_layout.addWidget(self.btn_back)
        header_layout.addWidget(self.lbl_current_path)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # Lista de carpetas
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.folder_double_clicked)
        layout.addWidget(self.list_widget)
        
        # Botones de acción
        btn_layout = QHBoxLayout()
        btn_select = QPushButton("Seleccionar esta carpeta")
        btn_select.clicked.connect(self.accept_selection)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_select)
        layout.addLayout(btn_layout)

    def load_folders(self):
        if not self.drive_service:
            try:
                self.drive_service = self.auth.get_drive_service()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"No se pudo conectar a Drive: {e}")
                self.reject()
                return

        self.list_widget.clear()
        self.list_widget.addItem(QListWidgetItem("Cargando..."))
        QApplication.processEvents()

        try:
            query = f"'{self.current_parent}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            results = self.drive_service.files().list(
                q=query,
                pageSize=1000,
                fields="files(id, name)",
                orderBy="name"
            ).execute()
            
            items = results.get('files', [])
            self.list_widget.clear()
            
            if not items:
                self.list_widget.addItem(QListWidgetItem("(Carpeta vacía)"))
                self.list_widget.item(0).setFlags(Qt.ItemFlag.NoItemFlags)
            else:
                for item in items:
                    list_item = QListWidgetItem(f"📁 {item['name']}")
                    list_item.setData(Qt.ItemDataRole.UserRole, item['id'])
                    list_item.setData(Qt.ItemDataRole.UserRole + 1, item['name'])
                    self.list_widget.addItem(list_item)
                    
            self.btn_back.setEnabled(len(self.history) > 0)
            
        except Exception as e:
            self.list_widget.clear()
            QMessageBox.warning(self, "Error", f"Error cargando carpetas: {e}")

    def folder_double_clicked(self, item):
        folder_id = item.data(Qt.ItemDataRole.UserRole)
        folder_name = item.data(Qt.ItemDataRole.UserRole + 1)
        if folder_id:
            self.history.append((self.current_parent, self.lbl_current_path.text()))
            self.current_parent = folder_id
            self.lbl_current_path.setText(folder_name)
            self.load_folders()

    def go_back(self):
        if self.history:
            prev_parent, prev_path = self.history.pop()
            self.current_parent = prev_parent
            self.lbl_current_path.setText(prev_path)
            self.load_folders()

    def accept_selection(self):
        # Seleccionar la carpeta actual navegada, o el item seleccionado
        selected_items = self.list_widget.selectedItems()
        if selected_items and selected_items[0].data(Qt.ItemDataRole.UserRole):
            self.selected_folder_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
            self.selected_folder_name = selected_items[0].data(Qt.ItemDataRole.UserRole + 1)
        else:
            # Si no hay nada seleccionado, es la carpeta en la que estamos parados
            self.selected_folder_id = self.current_parent
            self.selected_folder_name = self.lbl_current_path.text()
            
        self.accept()

class SyncAppMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.auth = GoogleAuth()
        self.scheduler = SyncScheduler()
        
        self.setWindowTitle("FolderFlow")
        self.setMinimumSize(600, 450)
        
        icon_path = resource_path('folderFlow-icon.png')
        self.setWindowIcon(QIcon(icon_path))
        
        # Signals initialization
        self.signals = WorkerSignals()
        self.signals.sync_finished.connect(self._on_sync_finished)
        self.signals.sync_progress.connect(self.log_message)
        
        # Override print to capture engine logs visually (simple approach)
        self._original_print = print
        import builtins
        builtins.print = self._custom_print

        self.init_ui()
        self.apply_styles()
        self.init_tray_icon()
        self.load_settings()
        
        # Iniciar scheduler en background con la freq guardada
        self.scheduler.start()
        self.update_scheduler_btn_state()

    def _custom_print(self, *args, **kwargs):
        """Intercepta los prints para mandarlos al log visual además de la consola."""
        text = " ".join(map(str, args))
        self._original_print(text)
        # Usar signals para interactuar con la UI desde otros hilos donde ocurren los prints
        self.signals.sync_progress.emit(text)

    def log_message(self, text):
        """Añade texto al visor de logs."""
        if hasattr(self, 'text_logs'):
            import datetime
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            self.text_logs.append(f"[{timestamp}] {text}")

    def apply_styles(self):
        # A sleek dark theme with vibrant accents
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e2e;
            }
            QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Segoe UI', 'Inter', sans-serif;
                font-size: 13px;
            }
            QLabel {
                padding: 2px;
            }
            QTabWidget::pane {
                border: 1px solid #313244;
                background: #1e1e2e;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #181825;
                color: #a6adc8;
                padding: 10px 20px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #313244;
                color: #cdd6f4;
                border-bottom: 2px solid #89b4fa;
                font-weight: bold;
            }
            QTabBar::tab:hover:!selected {
                background: #252538;
            }
            QPushButton {
                background-color: #89b4fa;
                color: #11111b;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #b4befe;
            }
            QPushButton:pressed {
                background-color: #74c7ec;
            }
            QPushButton:disabled {
                background-color: #45475a;
                color: #a6adc8;
            }
            QPushButton#ActionBtn {
                background-color: #a6e3a1;
                font-size: 14px;
            }
            QPushButton#ActionBtn:hover {
                background-color: #94e2d5;
            }
            QPushButton#DangerBtn {
                background-color: #f38ba8;
            }
            QPushButton#DangerBtn:hover {
                background-color: #eba0ac;
            }
            QTextEdit {
                background-color: #11111b;
                color: #a6e3a1;
                border: 1px solid #313244;
                border-radius: 6px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
            QComboBox, QSpinBox {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 6px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #313244;
                selection-background-color: #45475a;
            }
        """)

    def init_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tabs.setContentsMargins(10, 10, 10, 10)

        # --- TAB 1: ESTADO Y LOGS ---
        self.tab_logs = QWidget()
        logs_layout = QVBoxLayout(self.tab_logs)
        logs_layout.setSpacing(15)
        logs_layout.setContentsMargins(15, 15, 15, 15)
        
        # Removed Branding Header

        # Status Header
        status_layout = QHBoxLayout()
        self.lbl_auth_status = QLabel("Estado: No Autenticado")
        self.lbl_auth_status.setStyleSheet("font-weight: bold; font-size: 14px;")
        status_layout.addWidget(self.lbl_auth_status)
        
        # Scheduler Toggle
        self.btn_toggle_scheduler = QPushButton("Pausar Sincronizador")
        self.btn_toggle_scheduler.clicked.connect(self.toggle_scheduler)
        status_layout.addStretch()
        status_layout.addWidget(self.btn_toggle_scheduler)
        logs_layout.addLayout(status_layout)
        
        # Logs View
        self.text_logs = QTextEdit()
        self.text_logs.setReadOnly(True)
        lbl_hist = QLabel("Terminal de Actividad:")
        lbl_hist.setStyleSheet("color: #bac2de; font-weight: bold; margin-top: 10px;")
        logs_layout.addWidget(lbl_hist)
        logs_layout.addWidget(self.text_logs)
        
        # Sync Now button on logs page too
        btn_sync_now_logs = QPushButton("🚀 Sincronizar Ahora")
        btn_sync_now_logs.setObjectName("ActionBtn")
        btn_sync_now_logs.clicked.connect(self.start_manual_sync)
        logs_layout.addWidget(btn_sync_now_logs)
        
        self.tabs.addTab(self.tab_logs, "Monitor")


        # --- TAB 2: CONFIGURACIÓN ---
        self.tab_config = QWidget()
        config_layout = QVBoxLayout(self.tab_config)
        config_layout.setSpacing(15)
        config_layout.setContentsMargins(20, 20, 20, 20)
        
        # 1. Autenticación
        auth_layout = QHBoxLayout()
        btn_auth = QPushButton("Conectar Google Drive")
        btn_auth.clicked.connect(self.authenticate_drive)
        btn_logout = QPushButton("Cerrar Sesión")
        btn_logout.setObjectName("DangerBtn")
        btn_logout.clicked.connect(self.logout_drive)
        auth_layout.addWidget(QLabel("🔑 Cuenta de Google:"))
        auth_layout.addStretch()
        auth_layout.addWidget(btn_auth)
        auth_layout.addWidget(btn_logout)
        config_layout.addLayout(auth_layout)

        # 2. Carpeta Local
        local_layout = QHBoxLayout()
        self.lbl_local_folder = QLabel("Carpeta Local: No seleccionada")
        self.lbl_local_folder.setWordWrap(True)
        btn_local = QPushButton("Seleccionar...")
        btn_local.clicked.connect(self.select_local_folder)
        local_layout.addWidget(QLabel("💻 Carpeta Local:"))
        local_layout.addWidget(self.lbl_local_folder, 1)
        local_layout.addWidget(btn_local)
        config_layout.addLayout(local_layout)

        # 3. Carpeta Nube
        cloud_layout = QHBoxLayout()
        self.lbl_cloud_folder = QLabel("Carpeta Nube: No definida")
        self.lbl_cloud_folder.setWordWrap(True)
        btn_cloud = QPushButton("Seleccionar Nube...")
        btn_cloud.clicked.connect(self.set_cloud_id)
        cloud_layout.addWidget(QLabel("☁️ Carpeta Nube:"))
        cloud_layout.addWidget(self.lbl_cloud_folder, 1)
        cloud_layout.addWidget(btn_cloud)
        config_layout.addLayout(cloud_layout)

        # 4. Dirección de Sync
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("🔄 Dirección:"))
        self.combo_direction = QComboBox()
        self.combo_direction.addItems([
            "Bidireccional (Recomendado)", 
            "Local a Nube (Backup)", 
            "Nube a Local (Restore)"
        ])
        dir_layout.addWidget(self.combo_direction)
        dir_layout.addStretch()
        config_layout.addLayout(dir_layout)

        # 5. Frecuencia
        freq_layout = QHBoxLayout()
        freq_layout.addWidget(QLabel("⏱️ Cada:"))
        self.spin_freq = QSpinBox()
        self.spin_freq.setRange(1, 1440)
        self.spin_freq.setValue(15)
        self.combo_unit = QComboBox()
        self.combo_unit.addItems(["minutos", "segundos"])
        
        freq_layout.addWidget(self.spin_freq)
        freq_layout.addWidget(self.combo_unit)
        freq_layout.addStretch()
        config_layout.addLayout(freq_layout)

        # 5.5. Opciones del sistema (Autostart)
        sys_layout = QHBoxLayout()
        self.chk_autostart = QCheckBox("Iniciar automáticamente al encender el equipo")
        sys_layout.addWidget(self.chk_autostart)
        sys_layout.addStretch()
        config_layout.addLayout(sys_layout)

        # 6. Botones de Acción
        action_layout = QHBoxLayout()
        btn_save = QPushButton("💾 Guardar Configuración")
        btn_save.setObjectName("ActionBtn")
        btn_save.clicked.connect(self.save_settings)
        action_layout.addStretch()
        action_layout.addWidget(btn_save)
        config_layout.addLayout(action_layout)
        
        # LinkedIn Link
        linkedin_layout = QHBoxLayout()
        linkedin_layout.addStretch()
        linkedin_label = QLabel('<a href="https://www.linkedin.com/in/dialp/" style="color: #89b4fa; text-decoration: none;">Linkedin</a>')
        linkedin_label.setOpenExternalLinks(True)
        linkedin_layout.addWidget(linkedin_label)
        config_layout.addLayout(linkedin_layout)
        config_layout.addStretch()

        self.tabs.addTab(self.tab_config, "Ajustes")
        
        # Initial auth check
        if self.auth.creds and (self.auth.creds.valid or getattr(self.auth.creds, 'refresh_token', False)):
            self.lbl_auth_status.setText("Estado: Conectado a Drive ✔️")
            self.lbl_auth_status.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 14px;")
        else:
            self.lbl_auth_status.setText("Estado: Desconectado ❌")
            self.lbl_auth_status.setStyleSheet("color: #f38ba8; font-weight: bold; font-size: 14px;")

    def init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        # Application icon
        icon_path = resource_path('folderFlow-icon.png')
        icon = QIcon(icon_path)
        self.tray_icon.setIcon(icon)
        
        # Create tray menu
        tray_menu = QMenu()
        show_action = tray_menu.addAction("Mostrar Aplicación")
        show_action.triggered.connect(self.show_normal)
        
        sync_action = tray_menu.addAction("Sincronizar Ahora")
        sync_action.triggered.connect(self.start_manual_sync)
        
        quit_action = tray_menu.addAction("Salir Completamente")
        quit_action.triggered.connect(self.quit_app)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()
        
    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger or reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_normal()
            
    def show_normal(self):
        self.show()
        self.activateWindow()
        
    def quit_app(self):
        self.scheduler.stop()
        QApplication.quit()

    def select_local_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta Local")
        if folder:
            self.lbl_local_folder.setText(f"Carpeta Local: {folder}")
            self.config_manager.set('local_folder', folder)

    def set_cloud_id(self):
        if not self.auth.creds or not self.auth.creds.valid:
            QMessageBox.warning(self, "No Autenticado", "Por favor, conecta Google Drive primero.")
            return
            
        dialog = CloudFolderPickerDialog(self.auth, self)
        if dialog.exec():
            folder_id = dialog.selected_folder_id
            folder_name = dialog.selected_folder_name
            self.lbl_cloud_folder.setText(f"Carpeta Nube: {folder_name} (ID: {folder_id[:8]}...)")
            self.config_manager.set('remote_folder_id', folder_id)
            self.config_manager.set('remote_folder_name', folder_name)

    def authenticate_drive(self):
        try:
            self.auth.authenticate()
            self.lbl_auth_status.setText("Estado: Conectado a Google Drive ✔️")
            self.lbl_auth_status.setStyleSheet("color: green;")
            QMessageBox.information(self, "Autenticación", "Conexión exitosa con Google Drive.")
        except Exception as e:
            QMessageBox.critical(self, "Error de Autenticación", str(e))

    def logout_drive(self):
        if self.auth.logout():
            self.lbl_auth_status.setText("Estado: Desconectado ❌ (Requiere Login)")
            self.lbl_auth_status.setStyleSheet("color: orange;")
            QMessageBox.information(self, "Sesión Cerrada", "Se ha cerrado la sesión de Google Drive.")
        else:
            QMessageBox.warning(self, "Error", "No se pudo cerrar la sesión completamente.")

    def load_settings(self):
        folder = self.config_manager.get('local_folder')
        if folder:
            self.lbl_local_folder.setText(f"Carpeta Local: {folder}")
            
        r_folder = self.config_manager.get('remote_folder_id')
        r_name = self.config_manager.get('remote_folder_name')
        if r_folder:
            name_display = r_name if r_name else "Definida"
            self.lbl_cloud_folder.setText(f"Carpeta Nube: {name_display} (ID: {r_folder[:8]}...)")
        
        freq = self.config_manager.get('sync_frequency_minutes')
        unit = self.config_manager.get('sync_time_unit') or 'minutos'
        if freq:
            self.spin_freq.setValue(int(freq))
            if unit == 'segundos' or unit == 'seconds':
                self.combo_unit.setCurrentText('segundos')
            else:
                self.combo_unit.setCurrentText('minutos')
                
        # Cargar estado real de autostart
        self.chk_autostart.setChecked(is_autostart_enabled())

    def save_settings(self):
        # Convert internal values
        unit = 'seconds' if self.combo_unit.currentText() == 'segundos' else 'minutes'
        self.config_manager.set('sync_frequency_minutes', self.spin_freq.value())
        self.config_manager.set('sync_time_unit', unit)
        
        direction = self.combo_direction.currentText()
        if "Bidireccional" in direction:
            mode = "bidirectional"
        elif "Local" in direction and "Nube" in direction:
            mode = "local_to_cloud" if "Local a" in direction else "cloud_to_local"
        self.config_manager.set('sync_direction', mode)
        
        # Guardar y aplicar configuración de inicio automático
        autostart = self.chk_autostart.isChecked()
        self.config_manager.set('autostart', autostart)
        if autostart:
            enable_autostart()
        else:
            disable_autostart()
        
        self.scheduler.update_frequency(self.spin_freq.value(), unit)
        QMessageBox.information(self, "Éxito", "Configuración guardada correctamente y sincronizador actualizado.")
        self.update_scheduler_btn_state()

    def toggle_scheduler(self):
        if self.scheduler.is_running():
            self.scheduler.stop()
            self.log_message("Sincronizador automático pausado.")
        else:
            self.scheduler.start()
            self.log_message("Sincronizador automático reanudado.")
        self.update_scheduler_btn_state()

    def update_scheduler_btn_state(self):
        if self.scheduler.is_running():
            self.btn_toggle_scheduler.setText("Pausar Sincronizador ⏸️")
        else:
            self.btn_toggle_scheduler.setText("Reanudar Sincronizador ▶️")

    def start_manual_sync(self):
        self.lbl_auth_status.setText("Estado: Sincronizando...")
        self.lbl_auth_status.setStyleSheet("color: blue;")
        # No rededclaramos signals si ya existen
        threading.Thread(target=self._run_sync_thread, daemon=True).start()

    def _run_sync_thread(self):
        try:
            # Aquí idealmente se inyectaría una callback de progreso al engine
            # Por simplicidad ahora solo triggereamos y notificamos al final
            success = self.scheduler.trigger_sync_with_result() # Modificación ligera al scheduler necesaria
            self.signals.sync_finished.emit(success, "Sincronización manual terminada.")
        except Exception as e:
            self.signals.sync_finished.emit(False, str(e))
            
    def _on_sync_finished(self, success, message):
        if success:
            self.lbl_auth_status.setText("Estado: Sincronización finalizada ✔️")
            self.lbl_auth_status.setStyleSheet("color: green;")
        else:
            self.lbl_auth_status.setText(f"Estado: Error en Sincronización ❌")
            self.lbl_auth_status.setStyleSheet("color: red;")
            # You might want to log the error instead of interrupting with a messagebox if in background
            self.log_message(f"FALLA: {message}")

    def closeEvent(self, event):
        # Override close to minimize to tray instead
        if self.tray_icon.isVisible():
            self.hide()
            self.tray_icon.showMessage(
                "FolderFlow",
                "La aplicación sigue ejecutándose en segundo plano.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
            event.ignore()
        else:
            self.scheduler.stop()
            super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    app.setDesktopFileName("com.dialp.folderflow")
    icon_path = resource_path('folderFlow-icon.png')
    app.setWindowIcon(QIcon(icon_path))
    
    window = SyncAppMainWindow()
    window.show()
    sys.exit(app.exec())
