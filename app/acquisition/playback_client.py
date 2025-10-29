"""
Cliente de reproducción que simula streaming leyendo un CSV grabado.
Permite diagnosticar problemas de visualización sin depender del hardware.
"""

import pandas as pd
import time
import threading
from pathlib import Path
from typing import Optional, Callable
from collections import deque
import logging

LOGGER = logging.getLogger(__name__)


class PlaybackClient:
    """
    Simula un cliente MSCL leyendo datos desde un CSV pregrabado.
    Reproduce los datos a la velocidad original para simular tiempo real.
    """
    
    def __init__(self, csv_path: str, sample_rate_hz: float = 256.0):
        """
        Args:
            csv_path: Ruta al archivo CSV con los datos grabados
            sample_rate_hz: Frecuencia de muestreo original
        """
        self.csv_path = Path(csv_path)
        self.sample_rate_hz = sample_rate_hz
        self.sample_period_s = 1.0 / sample_rate_hz  # Tiempo entre muestras
        
        # Cargar datos del CSV
        LOGGER.info(f"Loading data from {self.csv_path}...")
        self.df = pd.read_csv(self.csv_path)
        LOGGER.info(f"Loaded {len(self.df)} samples from CSV")
        
        # Estado de reproducción
        self._current_index = 0
        self._is_playing = False
        self._playback_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Callback para enviar datos
        self._data_callback: Optional[Callable] = None
    
    def set_data_callback(self, callback: Callable):
        """
        Configura la función callback que recibirá los datos simulados.
        
        Args:
            callback: Función que recibe (timestamp, x, y, z, sensor_id)
        """
        self._data_callback = callback
    
    def start_playback(self, loop: bool = True, speed_multiplier: float = 1.0):
        """
        Inicia la reproducción de datos.
        
        Args:
            loop: Si True, vuelve a empezar al llegar al final
            speed_multiplier: Multiplicador de velocidad (1.0 = tiempo real, 2.0 = doble velocidad)
        """
        if self._is_playing:
            LOGGER.warning("Playback already running")
            return
        
        LOGGER.info(f"Starting playback - {len(self.df)} samples @ {self.sample_rate_hz}Hz (speed: {speed_multiplier}x)")
        self._is_playing = True
        self._stop_event.clear()
        
        self._playback_thread = threading.Thread(
            target=self._playback_loop,
            args=(loop, speed_multiplier),
            daemon=True
        )
        self._playback_thread.start()
    
    def stop_playback(self):
        """Detiene la reproducción."""
        if not self._is_playing:
            return
        
        LOGGER.info("Stopping playback...")
        self._is_playing = False
        self._stop_event.set()
        
        if self._playback_thread:
            self._playback_thread.join(timeout=2.0)
        
        LOGGER.info("Playback stopped")
    
    def reset(self):
        """Reinicia la reproducción desde el principio."""
        self._current_index = 0
        LOGGER.info("Playback reset to beginning")
    
    def _playback_loop(self, loop: bool, speed_multiplier: float):
        """
        Loop principal de reproducción (ejecuta en thread separado).
        """
        adjusted_period = self.sample_period_s / speed_multiplier
        
        while not self._stop_event.is_set():
            # Verificar si llegamos al final
            if self._current_index >= len(self.df):
                if loop:
                    LOGGER.info("Reached end of data, looping back to start")
                    self._current_index = 0
                else:
                    LOGGER.info("Reached end of data, stopping playback")
                    break
            
            # Leer siguiente muestra
            row = self.df.iloc[self._current_index]
            
            # Extraer datos (asumiendo columnas del CSV de aceleración)
            # Formato esperado: timestamp, node_id, channel_id, x, y, z
            try:
                timestamp = row['timestamp']
                sensor_id = str(int(row['node_id']))
                x = float(row['x'])
                y = float(row['y'])
                z = float(row['z'])
                
                # Enviar datos al callback
                if self._data_callback:
                    self._data_callback(timestamp, x, y, z, sensor_id)
                
            except Exception as e:
                LOGGER.error(f"Error processing row {self._current_index}: {e}")
            
            # Avanzar índice
            self._current_index += 1
            
            # Log progreso cada 1000 muestras
            if self._current_index % 1000 == 0:
                progress_pct = (self._current_index / len(self.df)) * 100
                LOGGER.info(f"Playback progress: {self._current_index}/{len(self.df)} ({progress_pct:.1f}%)")
            
            # Esperar tiempo entre muestras (simular tiempo real)
            time.sleep(adjusted_period)
        
        self._is_playing = False


class RecordingSession:
    """
    Gestiona la grabación de datos del acelerómetro a CSV.
    """
    
    def __init__(self, output_dir: str = "data/playback"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self._buffer = deque()
        self._is_recording = False
        self._start_time = None
        self._sample_count = 0
    
    def start_recording(self, duration_seconds: int = 120):
        """
        Inicia grabación con duración específica.
        
        Args:
            duration_seconds: Duración de la grabación en segundos
        """
        LOGGER.info(f"Starting recording session - duration: {duration_seconds}s")
        self._is_recording = True
        self._start_time = time.time()
        self._buffer.clear()
        self._sample_count = 0
        
        # Programar detención automática
        stop_timer = threading.Timer(duration_seconds, self.stop_recording)
        stop_timer.daemon = True
        stop_timer.start()
    
    def add_sample(self, timestamp: float, x: float, y: float, z: float, sensor_id: str):
        """Agrega una muestra al buffer de grabación."""
        if not self._is_recording:
            return
        
        self._buffer.append({
            'timestamp': timestamp,
            'node_id': sensor_id,
            'x': x,
            'y': y,
            'z': z
        })
        self._sample_count += 1
        
        # Log progreso cada 1000 muestras
        if self._sample_count % 1000 == 0:
            elapsed = time.time() - self._start_time
            LOGGER.info(f"Recording: {self._sample_count} samples in {elapsed:.1f}s")
    
    def stop_recording(self) -> Optional[Path]:
        """
        Detiene la grabación y guarda a CSV.
        
        Returns:
            Path al archivo CSV generado, o None si no hay datos
        """
        if not self._is_recording:
            LOGGER.warning("No recording in progress")
            return None
        
        self._is_recording = False
        
        if len(self._buffer) == 0:
            LOGGER.warning("No data recorded")
            return None
        
        # Generar nombre de archivo con timestamp
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"recording_{timestamp_str}.csv"
        
        # Convertir buffer a DataFrame y guardar
        LOGGER.info(f"Saving {len(self._buffer)} samples to {output_file}...")
        df = pd.DataFrame(list(self._buffer))
        df.to_csv(output_file, index=False)
        
        duration = time.time() - self._start_time
        LOGGER.info(f"Recording saved: {len(self._buffer)} samples in {duration:.1f}s -> {output_file}")
        
        return output_file
    
    @property
    def is_recording(self) -> bool:
        """Retorna True si hay grabación activa."""
        return self._is_recording
