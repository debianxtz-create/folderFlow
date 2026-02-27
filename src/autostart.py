import os
import sys

# Name of the application as it will appear in the startup entries
APP_NAME = "FolderFlow"

def is_windows() -> bool:
    return sys.platform == 'win32'

def is_linux() -> bool:
    return sys.platform.startswith('linux')

def get_executable_path() -> str:
    """Returns the absolute path to the current executable."""
    if getattr(sys, 'frozen', False):
        return sys.executable
    # If running from source, we don't usually want to add 'python main.py' to startup directly,
    # but for testing, it could be possible. Generally, this feature makes sense for the frozen app.
    return os.path.abspath(sys.argv[0])

def enable_autostart():
    """Habilita el inicio automatico de la aplicacion al iniciar sesion."""
    exec_path = get_executable_path()

    if is_windows():
        try:
            import winreg
            # HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE
            )
            # Use quotes around the path to handle spaces
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exec_path}"')
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Error habilitando autostart en Windows: {e}")

    elif is_linux():
        try:
            # Create a .desktop file in ~/.config/autostart/
            autostart_dir = os.path.expanduser("~/.config/autostart")
            os.makedirs(autostart_dir, exist_ok=True)
            desktop_file_path = os.path.join(autostart_dir, f"{APP_NAME.lower()}.desktop")

            desktop_content = f"""[Desktop Entry]
Type=Application
Exec={exec_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name={APP_NAME}
Comment=FolderFlow Auto-start
"""
            with open(desktop_file_path, "w") as f:
                f.write(desktop_content)
            
            # Ensure it is executable
            os.chmod(desktop_file_path, 0o755)
        except Exception as e:
            print(f"Error habilitando autostart en Linux: {e}")

def disable_autostart():
    """Deshabilita el inicio automatico de la aplicacion al iniciar sesion."""
    if is_windows():
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, APP_NAME)
            winreg.CloseKey(key)
        except FileNotFoundError:
            # Key doesn't exist, which is fine
            pass
        except Exception as e:
            print(f"Error deshabilitando autostart en Windows: {e}")

    elif is_linux():
        try:
            autostart_dir = os.path.expanduser("~/.config/autostart")
            desktop_file_path = os.path.join(autostart_dir, f"{APP_NAME.lower()}.desktop")
            if os.path.exists(desktop_file_path):
                os.remove(desktop_file_path)
        except Exception as e:
            print(f"Error deshabilitando autostart en Linux: {e}")

def is_autostart_enabled() -> bool:
    """Verifica si el inicio automatico esta habilitado en el sistema."""
    if is_windows():
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ
            )
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return value is not None
        except FileNotFoundError:
            return False
        except Exception:
            return False

    elif is_linux():
        autostart_dir = os.path.expanduser("~/.config/autostart")
        desktop_file_path = os.path.join(autostart_dir, f"{APP_NAME.lower()}.desktop")
        return os.path.exists(desktop_file_path)
    
    return False
