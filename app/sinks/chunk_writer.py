"""Real-time chunk writer that creates time-based chunks in parallel with main CSV."""
from __future__ import annotations

import csv
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)


class RealtimeChunkWriter:
    """
    Genera chunks en tiempo real escribiendo en paralelo al CSV principal.

    Estrategia optimizada:
    - Acumula samples en buffer
    - Escribe chunk cuando buffer alcanza el tamaño de 2 minutos de datos
    - NO parsea timestamps (usa contador de samples @ frecuencia conocida)
    """

    def __init__(
        self,
        base_dir: Path,
        sensor_id: str,
        chunk_duration_minutes: float = 2.0,
        sample_rate_hz: float = 256.0,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.sensor_id = sensor_id
        self.chunk_duration_minutes = chunk_duration_minutes
        self.sample_rate_hz = sample_rate_hz

        # Calcular samples por chunk
        self.samples_per_chunk = int(chunk_duration_minutes * 60.0 * sample_rate_hz)

        # Directorio de chunks
        self.chunks_dir = self.base_dir / sensor_id / "chunks"
        self.chunks_dir.mkdir(parents=True, exist_ok=True)

        # Estado
        self._lock = threading.Lock()
        self._current_chunk_buffer: List[List] = []
        self._chunk_number = 0
        self._session_start_time: datetime | None = None
        self._headers: List[str] | None = None

        # Estadísticas
        self._chunks_created = 0
        self._total_samples_written = 0

        logger.info(f"[CHUNK WRITER] Inicializado para {sensor_id}, chunks de {chunk_duration_minutes} min ({self.samples_per_chunk:,} samples @ {sample_rate_hz} Hz)")

    def start_session(self, session_start: datetime) -> None:
        """Iniciar nueva sesión de captura."""
        with self._lock:
            self._session_start_time = session_start
            self._current_chunk_buffer.clear()
            self._chunk_number = 0
            self._chunks_created = 0
            self._total_samples_written = 0
            self._headers = None

        logger.info(f"[CHUNK WRITER] Sesión iniciada para {self.sensor_id}")

    def append_samples(self, records: List[List]) -> None:
        """Agregar muestras al buffer y escribir chunk si está completo.

        Args:
            records: Lista de records en formato [timestamp_local, timestamp_utc, stay_id, sensor_id, ...]
        """
        if not records:
            return

        with self._lock:
            # Guardar headers si es la primera vez
            if self._headers is None:
                # Inferir headers desde el número de columnas del primer record
                # Típicamente: timestamp_local, timestamp_utc, stay_id, sensor_id, fs_hz, ax_g, ay_g, az_g, is_valid
                self._headers = ["timestamp_local", "timestamp_utc", "stay_id", "sensor_id", "fs_hz", "ax_g", "ay_g", "az_g", "is_valid"]

            # Agregar records al buffer
            self._current_chunk_buffer.extend(records)

            # Verificar si el buffer ha alcanzado el tamaño de un chunk
            if len(self._current_chunk_buffer) >= self.samples_per_chunk:
                self._write_chunk()

    def _write_chunk(self) -> None:
        """Escribir chunk actual al disco (debe llamarse dentro del lock)."""
        if not self._current_chunk_buffer:
            return

        # Calcular minutos de inicio y fin
        min_inicio = self._chunk_number * self.chunk_duration_minutes
        min_fin = min_inicio + self.chunk_duration_minutes

        # Crear nombre de archivo
        if self._session_start_time:
            timestamp_str = self._session_start_time.strftime("%Y%m%d_%H%M%S")
        else:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

        filename = f"sensor_{self.sensor_id}_acceleration_{timestamp_str}_{int(min_inicio):03d}-{int(min_fin):03d}min.csv"
        filepath = self.chunks_dir / filename

        # Escribir chunk
        try:
            with filepath.open('w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Escribir header
                if self._headers:
                    writer.writerow(self._headers)

                # Escribir samples (solo las del chunk actual)
                samples_to_write = self._current_chunk_buffer[:self.samples_per_chunk]
                writer.writerows(samples_to_write)

            samples_written = len(samples_to_write)
            self._total_samples_written += samples_written
            self._chunks_created += 1

            # Obtener timestamps para logging
            first_ts = samples_to_write[0][1] if samples_to_write else "N/A"  # timestamp_utc
            last_ts = samples_to_write[-1][1] if samples_to_write else "N/A"

            logger.info(
                f"[CHUNK WRITER] Chunk #{self._chunk_number} guardado: {filename} "
                f"({samples_written:,} samples, {min_inicio:.0f}-{min_fin:.0f} min) "
                f"[Rango: {first_ts} -> {last_ts}]"
            )

            # Remover samples escritas del buffer y preparar para siguiente chunk
            self._current_chunk_buffer = self._current_chunk_buffer[self.samples_per_chunk:]
            self._chunk_number += 1

        except Exception as e:
            logger.error(f"[CHUNK WRITER] Error escribiendo chunk: {e}", exc_info=True)

    def finalize_session(self) -> None:
        """Finalizar sesión y escribir el último chunk si hay datos pendientes."""
        with self._lock:
            # Escribir chunk final con cualquier dato pendiente
            if self._current_chunk_buffer:
                # Para el último chunk, escribir todos los datos restantes
                samples_remaining = len(self._current_chunk_buffer)

                min_inicio = self._chunk_number * self.chunk_duration_minutes
                # Calcular minutos reales basado en samples
                min_fin = min_inicio + (samples_remaining / self.sample_rate_hz / 60.0)

                if self._session_start_time:
                    timestamp_str = self._session_start_time.strftime("%Y%m%d_%H%M%S")
                else:
                    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

                filename = f"sensor_{self.sensor_id}_acceleration_{timestamp_str}_{int(min_inicio):03d}-{int(min_fin):03d}min.csv"
                filepath = self.chunks_dir / filename

                try:
                    with filepath.open('w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)

                        if self._headers:
                            writer.writerow(self._headers)

                        writer.writerows(self._current_chunk_buffer)

                    self._total_samples_written += samples_remaining
                    self._chunks_created += 1

                    logger.info(
                        f"[CHUNK WRITER] Chunk final guardado: {filename} "
                        f"({samples_remaining:,} samples)"
                    )

                except Exception as e:
                    logger.error(f"[CHUNK WRITER] Error escribiendo chunk final: {e}")

        logger.info(
            f"[CHUNK WRITER] Sesión finalizada - {self._chunks_created} chunks creados, "
            f"{self._total_samples_written:,} samples totales"
        )

        # Reset estado
        with self._lock:
            self._session_start_time = None
            self._current_chunk_buffer.clear()
            self._chunk_number = 0
            self._headers = None


__all__ = ["RealtimeChunkWriter"]
