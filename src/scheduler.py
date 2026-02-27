import schedule
import time
import threading
from src.engine import SyncEngine
from src.config import ConfigManager

class SyncScheduler:
    def __init__(self):
        self.config = ConfigManager()
        self.engine = SyncEngine()
        self._running = False
        self._thread = None

    def _run_schedule(self):
        while self._running:
            schedule.run_pending()
            time.sleep(1)

    def trigger_sync(self):
        print("[Scheduler] Ejecutando sincronización automática...")
        try:
            self.engine.sync()
            self.config.set('last_sync', time.time())
        except Exception as e:
            print(f"[Scheduler] Error en sync: {e}")

    def trigger_sync_with_result(self):
        """Versión de trigger_sync que devuelve éxito/falla para la UI manual."""
        print("[Scheduler] Ejecutando sincronización manual...")
        try:
            success = self.engine.sync()
            if success:
                self.config.set('last_sync', time.time())
            return success
        except Exception as e:
            print(f"[Scheduler] Error en sync: {e}")
            raise e

    def start(self):
        if self._running:
            return

        freq = int(self.config.get('sync_frequency_minutes') or 15)
        unit = self.config.get('sync_time_unit') or 'minutes'
        
        print(f"[Scheduler] Iniciado. Frecuencia: {freq} {unit}.")
        
        schedule.clear()
        if unit == 'seconds':
            schedule.every(freq).seconds.do(self.trigger_sync)
        else:
            schedule.every(freq).minutes.do(self.trigger_sync)
        
        self._running = True
        self._thread = threading.Thread(target=self._run_schedule, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            # We don't join immediately to avoid blocking UI during fast toggles, daemon threads will die anyway
            self._thread = None
        schedule.clear()
        print("[Scheduler] Detenido.")

    def update_frequency(self, new_freq, unit='minutes'):
        self.config.set('sync_frequency_minutes', new_freq)
        self.config.set('sync_time_unit', unit)
        if self._running:
            self.stop()
            self.start()

    def is_running(self):
        return self._running
