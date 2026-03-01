import sys
import os
import logging
import traceback

from src.paths import user_data_dir, migrate_old_data


def setup_logging():
    """Configure logging to file in user data directory."""
    log_file = os.path.join(user_data_dir(), 'folderflow.log')
    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    # Also log to stderr when running from a terminal
    if sys.stderr and hasattr(sys.stderr, 'write'):
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        logging.getLogger().addHandler(console)

    logging.info("FolderFlow starting. Data dir: %s", user_data_dir())


def global_exception_handler(exc_type, exc_value, exc_tb):
    """Catch unhandled exceptions, log them, and show a dialog."""
    # Ignore KeyboardInterrupt
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logging.critical("Unhandled exception:\n%s", error_msg)

    # Try to show a Qt error dialog if possible
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance()
        if app:
            QMessageBox.critical(
                None,
                "FolderFlow - Error Fatal",
                f"La aplicacion encontro un error inesperado.\n\n"
                f"{exc_type.__name__}: {exc_value}\n\n"
                f"Revisa el log en:\n{os.path.join(user_data_dir(), 'folderflow.log')}",
            )
    except Exception:
        pass  # If Qt itself is broken, at least the log file has the info


def main():
    migrate_old_data()
    setup_logging()
    sys.excepthook = global_exception_handler

    try:
        from PyQt6.QtWidgets import QApplication
        from src.ui import SyncAppMainWindow

        app = QApplication(sys.argv)
        window = SyncAppMainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception:
        logging.critical("Fatal error during startup:\n%s", traceback.format_exc())
        raise


if __name__ == '__main__':
    main()
