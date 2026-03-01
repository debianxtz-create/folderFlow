import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QFileDialog, 
                             QComboBox, QSpinBox, QMessageBox, QDialog, QListWidget, QListWidgetItem,
                             QTabWidget, QTextEdit, QSystemTrayIcon, QMenu, QStyle, QCheckBox, QFrame)
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
    sync_progress = pyqtSignal(str, str) # level, message
    progress_update = pyqtSignal(int, int, str) # current, total, filename

class CloudFolderPickerDialog(QDialog):
    def __init__(self, auth, parent=None):
        super(CloudFolderPickerDialog, self).__init__(parent)
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
            if not self.drive_service:
                return # Should not happen as load_folders checked it, but for safety
            
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
        
        self.setWindowTitle("Folder Flow")
        self.setMinimumSize(500, 800)
        
        icon_path = resource_path('folderFlow-icon.png')
        self.setWindowIcon(QIcon(icon_path))
        
        # Signals initialization
        self.signals = WorkerSignals()
        self.signals.sync_finished.connect(self._on_sync_finished)
        self.signals.sync_progress.connect(self.log_message)
        self.signals.progress_update.connect(self._update_progress_ui)
        
        # Intercept print
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
        text = " ".join(map(str, args))
        self._original_print(text)
        level = "INFO"
        message = text
        if text.startswith("ERROR:"):
            level = "ERROR"
            message = text[6:].strip()
        elif text.startswith("WARNING:"):
            level = "WARNING"
            message = text[8:].strip()
        elif text.startswith("INFO:"):
            level = "INFO"
            message = text[5:].strip()
            
        self.signals.sync_progress.emit(level, message)

    def log_message(self, level, message):
        """Añade texto al visor de logs con colores."""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        color = "#ffffff"
        if level == "ERROR": color = "#f38ba8"
        elif level == "WARNING": color = "#f9e2af"
        
        html_msg = f'<span style="color: #6c7086;">{timestamp}</span> <span style="color: {color};">{message}</span>'
        self.text_logs.append(html_msg)
        
    def _update_progress_ui(self, current, total, filename):
        self.lbl_progress_val.setText(f"{current}/{total}")
        self.lbl_sync_state.setText(f"Sync state: Processing {filename}")

    def _status_callback(self, level, data):
        if level == 'PROGRESS':
            self.signals.progress_update.emit(data['current'], data['total'], data['file'])
        else:
            self.signals.sync_progress.emit(level, str(data))

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow, QWidget#MainContent {
                background-color: #11111b;
            }
            QWidget {
                background-color: transparent;
                color: #cdd6f4;
                font-family: 'Segoe UI', 'Inter', sans-serif;
                font-size: 14px;
            }
            QTabWidget::pane {
                border: none;
                background: #11111b;
            }
            QTabBar::tab {
                background: #181825;
                color: #a6adc8;
                padding: 14px 28px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 4px;
                font-weight: bold;
                font-size: 15px;
            }
            QTabBar::tab:selected {
                background: #1e1e2e;
                color: #89b4fa;
                border-bottom: 2px solid #89b4fa;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: none;
                border-radius: 8px;
                padding: 12px 18px;
                font-weight: bold;
                font-size: 15px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
            QPushButton#ActionBtn {
                background-color: #89b4fa;
                color: #11111b;
            }
            QPushButton#ActionBtn:hover {
                background-color: #b4befe;
            }
            QPushButton#DangerBtn {
                color: #f38ba8;
            }
            QPushButton#HeaderBtn {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 10px;
                padding: 5px;
            }
            QPushButton#HeaderBtn:hover {
                background-color: #313244;
            }
            QTextEdit {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #313244;
                border-radius: 10px;
                padding: 10px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
            }
            QComboBox, QSpinBox {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 6px;
                padding: 6px;
                font-size: 14px;
            }
            #StatusCard {
                background-color: #1e1e2e;
                border-radius: 15px;
                padding: 18px;
            }
            #LogCard {
                background-color: #1e1e2e;
                border-radius: 15px;
                padding: 18px;
            }
            QLabel#HeaderTitle {
                font-size: 30px;
                font-weight: bold;
                color: #ffffff;
            }
            QLabel#CardTitle {
                font-size: 22px;
                font-weight: bold;
                color: #ffffff;
                margin-bottom: 12px;
            }
            QLabel#StatusInfo {
                font-size: 15px;
                color: #bac2de;
                padding: 4px 0px;
            }
        """)

    def init_ui(self):
        self.main_widget = QWidget()
        self.main_widget.setObjectName("MainContent")
        self.setCentralWidget(self.main_widget)
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # Header
        header = QHBoxLayout()
        title = QLabel("Folder Flow")
        title.setObjectName("HeaderTitle")
        header.addWidget(title)
        header.addStretch()
        
        self.btn_stop_main = QPushButton()
        self.btn_stop_main.setObjectName("HeaderBtn")
        self.btn_stop_main.setFixedSize(35, 35)
        self.btn_stop_main.clicked.connect(self.toggle_scheduler)
        
        self.btn_settings_main = QPushButton()
        self.btn_settings_main.setObjectName("HeaderBtn")
        self.btn_settings_main.setFixedSize(35, 35)
        self.btn_settings_main.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.btn_settings_main.setToolTip("Ajustes")
        self.btn_settings_main.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        
        header.addWidget(self.btn_stop_main)
        header.addWidget(self.btn_settings_main)
        main_layout.addLayout(header)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # --- TAB 1: MONITOR ---
        self.tab_monitor = QWidget()
        monitor_layout = QVBoxLayout(self.tab_monitor)
        monitor_layout.setSpacing(15)
        monitor_layout.setContentsMargins(0, 10, 0, 0)

        # Status Card
        status_card = QFrame()
        status_card.setObjectName("StatusCard")
        status_card.setFrameShape(QFrame.Shape.StyledPanel)
        sc_layout = QVBoxLayout(status_card)
        
        lbl_status_title = QLabel("Status")
        lbl_status_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_status_title.setObjectName("CardTitle")
        sc_layout.addWidget(lbl_status_title)

        # Status Grid Infos
        self.lbl_logged_user = QLabel("✅ Logged in as: -")
        self.lbl_local_path_disp = QLabel("📁 Local: -")
        self.lbl_cloud_path_disp = QLabel("☁️ Drive: -")
        self.lbl_mode_disp = QLabel("🔄 Mode: -")
        self.lbl_interval_disp = QLabel("⏱️ Interval: -")
        
        progress_layout = QHBoxLayout()
        progress_layout.addWidget(QLabel("📊 Progress:"))
        self.lbl_progress_val = QLabel("0/0")
        self.lbl_progress_val.setStyleSheet("font-weight: bold; color: #89b4fa;")
        progress_layout.addWidget(self.lbl_progress_val)
        progress_layout.addStretch()
        
        self.lbl_sync_state = QLabel("Sync state: Idle")
        self.lbl_sync_state.setStyleSheet("font-style: italic; color: #a6adc8; font-size: 11px;")
        self.lbl_sync_state.setWordWrap(True)

        for lbl in [self.lbl_logged_user, self.lbl_local_path_disp, self.lbl_cloud_path_disp, 
                    self.lbl_mode_disp, self.lbl_interval_disp]:
            lbl.setObjectName("StatusInfo")
            sc_layout.addWidget(lbl)
        
        sc_layout.addLayout(progress_layout)
        sc_layout.addWidget(self.lbl_sync_state)
        monitor_layout.addWidget(status_card)

        # Log Card
        log_card = QFrame()
        log_card.setObjectName("LogCard")
        lc_layout = QVBoxLayout(log_card)
        
        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("Sync Log"))
        log_header.addStretch()
        
        self.combo_log_filter = QComboBox()
        self.combo_log_filter.addItems(["All", "Errors", "Warnings", "Info"])
        self.combo_log_filter.setFixedWidth(100)
        log_header.addWidget(self.combo_log_filter)
        
        btn_clear_logs = QPushButton("🗑 Clear")
        btn_clear_logs.setStyleSheet("color: #89b4fa; background: transparent; font-size: 12px;")
        btn_clear_logs.clicked.connect(lambda: self.text_logs.clear())
        log_header.addWidget(btn_clear_logs)
        lc_layout.addLayout(log_header)

        self.text_logs = QTextEdit()
        self.text_logs.setReadOnly(True)
        lc_layout.addWidget(self.text_logs)
        monitor_layout.addWidget(log_card)
        
        btn_sync_now = QPushButton("🚀 Sync Now")
        btn_sync_now.setObjectName("ActionBtn")
        btn_sync_now.clicked.connect(self.start_manual_sync)
        monitor_layout.addWidget(btn_sync_now)

        self.tabs.addTab(self.tab_monitor, "Monitor")

        # --- TAB 2: CONFIG --- (Minimalist update)
        self.tab_config = QWidget()
        config_layout = QVBoxLayout(self.tab_config)
        config_layout.setContentsMargins(10, 20, 10, 20)
        config_layout.setSpacing(15)

        # Re-using previous setting widgets but styled
        s_auth = QHBoxLayout()
        s_auth.addWidget(QLabel("Account:"))
        btn_auth = QPushButton("Login")
        btn_auth.clicked.connect(self.authenticate_drive)
        btn_logout = QPushButton("Logout")
        btn_logout.setObjectName("DangerBtn")
        btn_logout.clicked.connect(self.logout_drive)
        s_auth.addStretch()
        s_auth.addWidget(btn_auth)
        s_auth.addWidget(btn_logout)
        config_layout.addLayout(s_auth)

        # Local
        s_local = QVBoxLayout()
        s_local.addWidget(QLabel("Local Folder:"))
        row_local = QHBoxLayout()
        self.lbl_local_folder = QLabel("Not selected")
        self.lbl_local_folder.setWordWrap(True)
        btn_local = QPushButton("Select...")
        btn_local.clicked.connect(self.select_local_folder)
        row_local.addWidget(self.lbl_local_folder, 1)
        row_local.addWidget(btn_local)
        s_local.addLayout(row_local)
        config_layout.addLayout(s_local)

        # Cloud
        s_cloud = QVBoxLayout()
        s_cloud.addWidget(QLabel("Cloud Folder:"))
        row_cloud = QHBoxLayout()
        self.lbl_cloud_folder = QLabel("Not selected")
        self.lbl_cloud_folder.setWordWrap(True)
        btn_cloud = QPushButton("Select...")
        btn_cloud.clicked.connect(self.set_cloud_id)
        row_cloud.addWidget(self.lbl_cloud_folder, 1)
        row_cloud.addWidget(btn_cloud)
        s_cloud.addLayout(row_cloud)
        config_layout.addLayout(s_cloud)

        # Mode
        s_mode = QHBoxLayout()
        s_mode.addWidget(QLabel("Sync Mode:"))
        self.combo_direction = QComboBox()
        self.combo_direction.addItems(["Bidirectional", "Local to Cloud", "Cloud to Local"])
        s_mode.addWidget(self.combo_direction)
        config_layout.addLayout(s_mode)

        # Interval
        s_int = QHBoxLayout()
        s_int.addWidget(QLabel("Interval:"))
        self.spin_freq = QSpinBox()
        self.spin_freq.setRange(1, 1440)
        self.combo_unit = QComboBox()
        self.combo_unit.addItems(["minutes", "seconds"])
        s_int.addWidget(self.spin_freq)
        s_int.addWidget(self.combo_unit)
        s_int.addStretch()
        config_layout.addLayout(s_int)
        
        self.chk_autostart = QCheckBox("Start with system")
        config_layout.addWidget(self.chk_autostart)

        config_layout.addStretch()
        btn_save = QPushButton("Save Settings")
        btn_save.setObjectName("ActionBtn")
        btn_save.clicked.connect(self.save_settings)
        config_layout.addWidget(btn_save)

        config_layout.addSpacing(20)
        btn_reset = QPushButton("⚠️ Reset Application")
        btn_reset.setObjectName("DangerBtn")
        btn_reset.clicked.connect(self.reset_application)
        config_layout.addWidget(btn_reset)

        self.tabs.addTab(self.tab_config, "Settings")

    def toggle_scheduler(self):
        if self.scheduler.is_running():
            self.scheduler.stop()
            self.log_message("WARNING", "Auto-sync paused.")
        else:
            self.scheduler.start()
            self.log_message("INFO", "Auto-sync resumed.")
        self.update_scheduler_btn_state()

    def update_scheduler_btn_state(self):
        if self.scheduler.is_running():
            self.btn_stop_main.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
            self.btn_stop_main.setToolTip("Pausar Sincronización")
        else:
            self.btn_stop_main.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            self.btn_stop_main.setToolTip("Reanudar Sincronización")

    def init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = resource_path('folderFlow-icon.png')
        self.tray_icon.setIcon(QIcon(icon_path))
        
        tray_menu = QMenu()
        show_action = tray_menu.addAction("Show App")
        show_action.triggered.connect(self.show_normal)
        sync_action = tray_menu.addAction("Sync Now")
        sync_action.triggered.connect(self.start_manual_sync)
        quit_action = tray_menu.addAction("Quit")
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
        folder = QFileDialog.getExistingDirectory(self, "Select Local Folder")
        if folder:
            self.lbl_local_folder.setText(folder)
            self.lbl_local_path_disp.setText(f"📁 Local: {os.path.basename(folder)}")
            self.config_manager.set('local_folder', folder)

    def set_cloud_id(self):
        if not self.auth.creds or not self.auth.creds.valid:
            QMessageBox.warning(self, "Auth Required", "Please login to Google Drive first.")
            return
            
        dialog = CloudFolderPickerDialog(self.auth, self)
        if dialog.exec():
            folder_id = dialog.selected_folder_id
            folder_name = dialog.selected_folder_name
            self.lbl_cloud_folder.setText(folder_name)
            self.lbl_cloud_path_disp.setText(f"☁️ Drive: {folder_name}")
            self.config_manager.set('remote_folder_id', folder_id)
            self.config_manager.set('remote_folder_name', folder_name)

    def authenticate_drive(self):
        try:
            self.auth.authenticate()
            email = self.auth.get_user_email()
            self.lbl_logged_user.setText(f"✅ Logged in as: {email}")
            QMessageBox.information(self, "Auth", "Google Drive connected successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def logout_drive(self):
        if self.auth.logout():
            self.lbl_logged_user.setText("❌ Logged out")
            QMessageBox.information(self, "Logout", "Disconnected from Google Drive.")
        else:
            QMessageBox.warning(self, "Error", "Could not complete logout.")

    def load_settings(self):
        folder = self.config_manager.get('local_folder')
        if folder:
            self.lbl_local_folder.setText(folder)
            self.lbl_local_path_disp.setText(f"📁 Local: {os.path.basename(folder)}")
        else:
            self.lbl_local_folder.setText("No seleccionada")
            self.lbl_local_path_disp.setText("📁 Local: No seleccionada")
            
        r_folder = self.config_manager.get('remote_folder_id')
        r_name = self.config_manager.get('remote_folder_name')
        if r_folder:
            name_display = r_name if r_name else "Definida"
            self.lbl_cloud_folder.setText(f"Carpeta Nube: {name_display} (ID: {r_folder[:8]}...)" if len(r_folder) >= 8 else f"Carpeta Nube: {name_display} (ID: {r_folder})")
            self.lbl_cloud_path_disp.setText(f"☁️ Drive: {name_display}")
        else:
            self.lbl_cloud_folder.setText("No seleccionada")
            self.lbl_cloud_path_disp.setText("☁️ Drive: No seleccionada")
        
        freq = self.config_manager.get('sync_frequency_minutes') or 15
        unit = self.config_manager.get('sync_time_unit') or 'minutes'
        self.spin_freq.setValue(int(freq))
        self.combo_unit.setCurrentText(unit if unit == 'seconds' else 'minutes')
        self.lbl_interval_disp.setText(f"⏱️ Interval: {freq} {unit}")
        
        mode = self.config_manager.get('sync_direction') or 'bidirectional'
        mode_idx = 0
        if mode == 'local_to_cloud': mode_idx = 1
        elif mode == 'cloud_to_local': mode_idx = 2
        self.combo_direction.setCurrentIndex(mode_idx)
        self.lbl_mode_disp.setText(f"🔄 Mode: {mode.replace('_', ' ').title()}")

        self.chk_autostart.setChecked(is_autostart_enabled())
        
        if self.auth.creds:
            email = self.auth.get_user_email()
            self.lbl_logged_user.setText(f"✅ Logged in as: {email}") if email else self.lbl_logged_user.setText("✅ Logged in")
        else:
            self.lbl_logged_user.setText("❌ Logged out")

    def save_settings(self):
        unit = self.combo_unit.currentText()
        freq = self.spin_freq.value()
        self.config_manager.set('sync_frequency_minutes', freq)
        self.config_manager.set('sync_time_unit', unit)
        self.lbl_interval_disp.setText(f"⏱️ Interval: {freq} {unit}")
        
        mode = "bidirectional"
        idx = self.combo_direction.currentIndex()
        if idx == 1: mode = "local_to_cloud"
        elif idx == 2: mode = "cloud_to_local"
        self.config_manager.set('sync_direction', mode)
        self.lbl_mode_disp.setText(f"🔄 Mode: {mode.replace('_', ' ').title()}")
        
        autostart = self.chk_autostart.isChecked()
        self.config_manager.set('autostart', autostart)
        if autostart: enable_autostart()
        else: disable_autostart()
        
        self.scheduler.update_frequency(freq, unit)
        QMessageBox.information(self, "Success", "Settings saved.")
        self.update_scheduler_btn_state()

    def reset_application(self):
        reply = QMessageBox.question(
            self, "Confirm Reset",
            "This will clear all settings, file tracking, and logout.\n"
            "Local files will NOT be deleted. Do you want to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 1. Stop scheduler
            self.scheduler.stop()
            
            # 2. Clear tracker DB
            from src.tracker import SyncTracker
            tracker = SyncTracker()
            tracker.clear_all_states()
            
            # 3. Reset config
            self.config_manager.reset_config()
            
            # 4. Logout
            self.auth.logout()

            # 5. Disable autostart
            disable_autostart()
            
            # 6. Reload UI
            self.load_settings()
            self.update_scheduler_btn_state()
            self.text_logs.clear()
            self.lbl_sync_state.setText("Sync state: Reset completed")
            
            QMessageBox.information(self, "Reset", "Application has been reset to its initial state.")

    def start_manual_sync(self):
        self.lbl_sync_state.setText("Sync state: Starting...")
        self.tray_icon.showMessage("Folder Flow", "Iniciando sincronización manual...")
        threading.Thread(target=self._run_sync_thread, daemon=True).start()

    def _run_sync_thread(self):
        try:
            success = self.scheduler.trigger_sync_with_result(status_callback=self._status_callback)
            self.signals.sync_finished.emit(success, "Manual sync completed.")
        except Exception as e:
            self.signals.sync_finished.emit(False, str(e))
            
    def _on_sync_finished(self, success, message):
        if success:
            self.lbl_sync_state.setText("Sync state: Idle (Last success moments ago)")
            self.tray_icon.showMessage("Folder Flow", "Sincronización finalizada correctamente.")
        else:
            self.lbl_sync_state.setText(f"Sync state: Error")
            self.log_message("ERROR", f"Sync failed: {message}")
            self.tray_icon.showMessage("Folder Flow", f"Error en sincronización: {message}", QSystemTrayIcon.MessageIcon.Critical)

    def closeEvent(self, event):
        if self.tray_icon.isVisible():
            self.hide()
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
