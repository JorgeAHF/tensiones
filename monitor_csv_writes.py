"""
Script para monitorear en tiempo real los logs de CSV writes.
Extrae solo los logs relevantes para diagnóstico de pérdida de datos.
Compatible con Windows.
"""
import time
from datetime import datetime
from pathlib import Path

def monitor_logs():
    """Monitorea el log file y muestra solo líneas relevantes."""
    log_file = Path("data/logs/mscl_tension.log")

    if not log_file.exists():
        print(f"Error: {log_file} no existe")
        return

    print(f"Monitoreando {log_file}...")
    print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    print("Esperando logs de CSV writes...")
    print()

    try:
        # Abrir archivo y posicionarse al final
        # errors='replace' maneja caracteres inválidos sin fallar
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            # Ir al final del archivo
            f.seek(0, 2)  # 2 = SEEK_END

            while True:
                line = f.readline()
                if line:
                    # Filtrar solo líneas relevantes
                    if any(pattern in line for pattern in [
                        "CSV WRITE",
                        "CSV SKIP",
                        "STATE CHANGE",
                        "lost="
                    ]):
                        print(line.rstrip())
                else:
                    # No hay nuevas líneas, esperar un poco
                    time.sleep(0.1)

    except KeyboardInterrupt:
        print()
        print("="*80)
        print(f"Fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("Monitoreo detenido por el usuario.")

if __name__ == "__main__":
    monitor_logs()
