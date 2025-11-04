"""
Coordinador de streaming thread-safe para datos de acelerómetro.

Maneja buffers circulares por sensor para desacoplar:
- Hardware MSCL (thread dedicado productor)
- Procesamiento FFT (thread procesador)
- Dash UI (thread consumidor)
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class AccelSample:
    """Muestra individual de acelerómetro con timestamp."""
    timestamp: float  # Epoch Unix en segundos
    sensor_id: str
    x: float  # Aceleración en g
    y: float
    z: float


class SensorBuffer:
    """Buffer circular thread-safe para un sensor específico."""
    
    def __init__(self, sensor_id: str, duration_sec: int = 60, sample_rate_hz: int = 256):
        """
        Args:
            sensor_id: Identificador único del sensor
            duration_sec: Duración del buffer en segundos (default 60s)
            sample_rate_hz: Frecuencia de muestreo en Hz (default 256Hz)
        """
        self.sensor_id = sensor_id
        self.duration_sec = duration_sec
        self.sample_rate_hz = sample_rate_hz
        
        # Buffer circular: mantiene últimos N segundos automáticamente
        max_samples = duration_sec * sample_rate_hz
        self.buffer: deque[AccelSample] = deque(maxlen=max_samples)
        
        # Lock para acceso thread-safe
        self.lock = Lock()
        
        # Estadísticas
        self.total_samples_received = 0
        self.last_sample_time = 0.0
        
        logger.info(
            f"[BUFFER] SensorBuffer creado para {sensor_id}: "
            f"capacidad={max_samples} samples ({duration_sec}s @ {sample_rate_hz}Hz)"
        )
    
    def add_sample(self, sample: AccelSample) -> None:
        """
        Añade muestra al buffer (thread-safe).
        Si el buffer está lleno, descarta la muestra más antigua automáticamente.
        """
        with self.lock:
            self.buffer.append(sample)
            self.total_samples_received += 1
            self.last_sample_time = time.time()
    
    def add_samples_batch(self, samples: List[AccelSample]) -> None:
        """Añade múltiples muestras eficientemente (thread-safe)."""
        with self.lock:
            self.buffer.extend(samples)
            self.total_samples_received += len(samples)
            if samples:
                self.last_sample_time = time.time()
    
    def get_latest(self, n_samples: Optional[int] = None) -> List[AccelSample]:
        """
        Obtiene las últimas N muestras (thread-safe).
        
        Args:
            n_samples: Número de muestras a obtener. Si None, retorna todas.
        
        Returns:
            Lista de muestras (copia para evitar race conditions)
        """
        with self.lock:
            if n_samples is None:
                return list(self.buffer)
            else:
                # Obtener últimas n_samples, o todas si hay menos
                return list(self.buffer)[-n_samples:]
    
    def get_time_range(self, start_time: float, end_time: float) -> List[AccelSample]:
        """
        Obtiene muestras en un rango de tiempo (thread-safe).
        
        Args:
            start_time: Timestamp inicial (epoch Unix)
            end_time: Timestamp final (epoch Unix)
        
        Returns:
            Lista de muestras en el rango especificado
        """
        with self.lock:
            return [
                sample for sample in self.buffer
                if start_time <= sample.timestamp <= end_time
            ]
    
    def get_stats(self) -> Dict:
        """Obtiene estadísticas del buffer (thread-safe)."""
        with self.lock:
            current_size = len(self.buffer)
            is_full = current_size >= self.buffer.maxlen if self.buffer.maxlen else False
            
            return {
                "sensor_id": self.sensor_id,
                "current_samples": current_size,
                "max_samples": self.buffer.maxlen,
                "is_full": is_full,
                "fill_percentage": (current_size / self.buffer.maxlen * 100) if self.buffer.maxlen else 0,
                "total_received": self.total_samples_received,
                "last_sample_age_sec": time.time() - self.last_sample_time if self.last_sample_time > 0 else None,
            }
    
    def clear(self) -> None:
        """Limpia el buffer (thread-safe)."""
        with self.lock:
            self.buffer.clear()
            logger.info(f"[CLEAN] Buffer limpiado para sensor {self.sensor_id}")


class StreamingCoordinator:
    """
    Coordinador central para streaming de datos de múltiples sensores.
    
    Proporciona acceso thread-safe a buffers circulares por sensor,
    desacoplando producción (hardware MSCL), procesamiento (FFT) y
    consumo (Dash UI).
    """
    
    def __init__(self, buffer_duration_sec: int = 60, sample_rate_hz: int = 256):
        """
        Args:
            buffer_duration_sec: Duración del buffer por sensor (default 60s)
            sample_rate_hz: Frecuencia de muestreo (default 256Hz)
        """
        self.buffer_duration_sec = buffer_duration_sec
        self.sample_rate_hz = sample_rate_hz
        
        # Diccionario de buffers por sensor (thread-safe en creación)
        self._buffers: Dict[str, SensorBuffer] = {}
        self._buffers_lock = Lock()
        
        logger.info(
            f"[COORDINATOR] StreamingCoordinator inicializado: "
            f"buffer={buffer_duration_sec}s, fs={sample_rate_hz}Hz"
        )
    
    def _get_or_create_buffer(self, sensor_id: str) -> SensorBuffer:
        """Obtiene buffer existente o crea uno nuevo (thread-safe)."""
        # Doble verificación para minimizar locks
        if sensor_id in self._buffers:
            return self._buffers[sensor_id]
        
        with self._buffers_lock:
            # Verificar de nuevo dentro del lock
            if sensor_id not in self._buffers:
                self._buffers[sensor_id] = SensorBuffer(
                    sensor_id=sensor_id,
                    duration_sec=self.buffer_duration_sec,
                    sample_rate_hz=self.sample_rate_hz,
                )
            return self._buffers[sensor_id]
    
    def add_sample(self, sensor_id: str, timestamp: float, x: float, y: float, z: float) -> None:
        """
        Añade una muestra de aceleración (llamado desde thread de hardware).
        
        Args:
            sensor_id: ID del sensor
            timestamp: Timestamp Unix epoch en segundos
            x, y, z: Aceleraciones en g
        """
        buffer = self._get_or_create_buffer(sensor_id)
        sample = AccelSample(timestamp=timestamp, sensor_id=sensor_id, x=x, y=y, z=z)
        buffer.add_sample(sample)
    
    def add_samples_batch(
        self, 
        sensor_id: str, 
        samples: List[Tuple[float, float, float, float]]
    ) -> None:
        """
        Añade múltiples muestras eficientemente (llamado desde thread de hardware).
        
        Args:
            sensor_id: ID del sensor
            samples: Lista de tuplas (timestamp, x, y, z)
        """
        buffer = self._get_or_create_buffer(sensor_id)
        accel_samples = [
            AccelSample(timestamp=ts, sensor_id=sensor_id, x=x, y=y, z=z)
            for ts, x, y, z in samples
        ]
        buffer.add_samples_batch(accel_samples)
    
    def get_latest_data(self, sensor_id: str, n_samples: Optional[int] = None) -> List[AccelSample]:
        """
        Obtiene las últimas N muestras de un sensor (llamado desde Dash UI).
        
        Args:
            sensor_id: ID del sensor
            n_samples: Número de muestras a obtener. Si None, retorna todas.
        
        Returns:
            Lista de muestras (puede estar vacía si el sensor no existe)
        """
        buffer = self._buffers.get(sensor_id)
        if buffer is None:
            logger.warning(f"⚠️ Sensor {sensor_id} no encontrado en StreamingCoordinator")
            return []
        return buffer.get_latest(n_samples)
    
    def get_time_range(
        self, 
        sensor_id: str, 
        start_time: float, 
        end_time: float
    ) -> List[AccelSample]:
        """
        Obtiene muestras en un rango de tiempo específico.
        
        Args:
            sensor_id: ID del sensor
            start_time: Timestamp inicial (epoch Unix)
            end_time: Timestamp final (epoch Unix)
        
        Returns:
            Lista de muestras en el rango
        """
        buffer = self._buffers.get(sensor_id)
        if buffer is None:
            return []
        return buffer.get_time_range(start_time, end_time)
    
    def get_all_sensor_ids(self) -> List[str]:
        """Retorna lista de IDs de sensores activos."""
        with self._buffers_lock:
            return list(self._buffers.keys())
    
    def get_stats(self, sensor_id: Optional[str] = None) -> Dict:
        """
        Obtiene estadísticas de buffers.
        
        Args:
            sensor_id: ID específico o None para todos los sensores
        
        Returns:
            Dict con estadísticas
        """
        if sensor_id is not None:
            buffer = self._buffers.get(sensor_id)
            if buffer is None:
                return {"error": f"Sensor {sensor_id} no encontrado"}
            return buffer.get_stats()
        else:
            # Estadísticas de todos los sensores
            with self._buffers_lock:
                return {
                    sid: buffer.get_stats()
                    for sid, buffer in self._buffers.items()
                }
    
    def clear_sensor(self, sensor_id: str) -> None:
        """Limpia buffer de un sensor específico."""
        buffer = self._buffers.get(sensor_id)
        if buffer:
            buffer.clear()
    
    def clear_all(self) -> None:
        """Limpia todos los buffers."""
        with self._buffers_lock:
            for buffer in self._buffers.values():
                buffer.clear()
            logger.info("[CLEAN] Todos los buffers limpiados")
    
    def reconfigure_sensor(self, sensor_id: str, sample_rate_hz: int) -> None:
        """
        Reconfigura un sensor con nueva frecuencia de muestreo.
        Recrea el buffer con la nueva configuración.
        
        Args:
            sensor_id: ID del sensor a reconfigurar
            sample_rate_hz: Nueva frecuencia de muestreo en Hz
        """
        with self._buffers_lock:
            # Eliminar buffer anterior si existe
            if sensor_id in self._buffers:
                logger.info(f"[COORDINATOR] Reconfigurando sensor {sensor_id}: {sample_rate_hz}Hz")
                del self._buffers[sensor_id]
            
            # Crear nuevo buffer con nueva frecuencia
            self._buffers[sensor_id] = SensorBuffer(
                sensor_id=sensor_id,
                duration_sec=self.buffer_duration_sec,
                sample_rate_hz=sample_rate_hz,
            )
            logger.info(f"[COORDINATOR] Buffer recreado para {sensor_id} @ {sample_rate_hz}Hz")


__all__ = ["StreamingCoordinator", "SensorBuffer", "AccelSample"]
