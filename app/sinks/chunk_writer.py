"""Real-time chunk writer that creates time-based chunks by copying from main CSV."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from datetime import datetime
import logging
import csv

logger = logging.getLogger(__name__)


class RealtimeChunkWriter:
    """
    Genera chunks en tiempo real copiando del archivo CSV principal.

    Estrategia:
    - Durante adquisición: escribir SOLO al CSV principal (rápido)
    - Cada N minutos: thread separado copia líneas del CSV principal a un chunk
    - NO bloquea la adquisición (usa thread independiente)
    """

    def __init__(
        self,
        base_dir: Path,
        sensor_id: str,
        chunk_duration_minutes: float = 2.0,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.sensor_id = sensor_id
        self.chunk_duration_sec = chunk_duration_minutes * 60.0

        # Directorio de chunks
        self.chunks_dir = self.base_dir / sensor_id / "chunks"
        self.chunks_dir.mkdir(parents=True, exist_ok=True)

        # Control de thread
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

        # Estado
        self._session_start_time: datetime | None = None
        self._main_csv_path: Path | None = None
        self._last_line_read = 0  # Línea donde terminó el último chunk
        self._chunk_number = 0

        # Estadísticas
        self._chunks_created = 0
        self._total_samples_written = 0

        logger.info(f"[CHUNK WRITER] Inicializado para {sensor_id}, chunks de {chunk_duration_minutes} min (modo copia)")

    def start_session(self, session_start: datetime, main_csv_path: Path) -> None:
        """Iniciar nueva sesión de captura.

        Args:
            session_start: Timestamp de inicio de sesión
            main_csv_path: Path al archivo CSV principal que se está escribiendo
        """
        self._session_start_time = session_start
        self._main_csv_path = main_csv_path
        self._last_line_read = 0
        self._chunk_number = 0
        self._chunks_created = 0
        self._total_samples_written = 0

        # Iniciar thread worker
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name=f"ChunkWriter-{sensor_id}"
        )
        self._worker_thread.start()

        logger.info(f"[CHUNK WRITER] Sesión iniciada para {self.sensor_id}, monitoreando {main_csv_path.name}")

    def _worker_loop(self) -> None:
        """Loop principal que crea chunks cada N minutos."""
        logger.info(f"[CHUNK WRITER] Worker thread iniciado para {self.sensor_id}")

        next_chunk_time = time.time() + self.chunk_duration_sec

        while not self._stop_event.is_set():
            # Esperar hasta el próximo chunk (con timeout para poder detener)
            wait_time = max(0, next_chunk_time - time.time())
            if self._stop_event.wait(min(wait_time, 1.0)):
                # Stop event activado
                break

            # Verificar si es hora de crear chunk
            if time.time() >= next_chunk_time:
                try:
                    self._create_chunk()
                    self._chunk_number += 1
                    next_chunk_time = time.time() + self.chunk_duration_sec
                except Exception as e:
                    logger.error(f"[CHUNK WRITER] Error creando chunk: {e}", exc_info=True)

        logger.info(f"[CHUNK WRITER] Worker thread finalizado para {self.sensor_id}")

    def _create_chunk(self) -> None:
        """Crea un chunk copiando líneas del CSV principal."""
        if not self._main_csv_path or not self._main_csv_path.exists():
            logger.debug(f"[CHUNK WRITER] CSV principal no existe aún: {self._main_csv_path}")
            return

        # Leer todas las líneas del CSV principal
        try:
            with self._main_csv_path.open('r', encoding='utf-8') as f:
                all_lines = f.readlines()
        except Exception as e:
            logger.warning(f"[CHUNK WRITER] No se pudo leer CSV principal: {e}")
            return

        # Calcular cuántas líneas copiar (desde última línea leída)
        total_lines = len(all_lines)
        if total_lines <= self._last_line_read + 1:  # +1 por header
            logger.debug(f"[CHUNK WRITER] No hay líneas nuevas para chunk #{self._chunk_number}")
            return

        # Líneas para este chunk (incluyendo header)
        header = all_lines[0]
        chunk_lines = all_lines[self._last_line_read + 1:total_lines]  # +1 para saltar header

        if not chunk_lines:
            return

        # Actualizar contador
        self._last_line_read = total_lines - 1  # -1 porque es índice base-0

        # Obtener timestamps del chunk para logging
        first_line_fields = chunk_lines[0].strip().split(',')
        last_line_fields = chunk_lines[-1].strip().split(',')

        first_sample_ts = first_line_fields[1] if len(first_line_fields) > 1 else "N/A"
        last_sample_ts = last_line_fields[1] if len(last_line_fields) > 1 else "N/A"

        # Calcular minutos de inicio y fin
        min_inicio = self._chunk_number * (self.chunk_duration_sec / 60)
        min_fin = min_inicio + (self.chunk_duration_sec / 60)

        # Crear nombre de archivo
        if self._session_start_time:
            timestamp_str = self._session_start_time.strftime("%Y%m%d_%H%M%S")
        else:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

        filename = f"{self.sensor_id}_acceleration_{timestamp_str}_{int(min_inicio):03d}-{int(min_fin):03d}min.csv"
        filepath = self.chunks_dir / filename

        # Escribir chunk
        try:
            with filepath.open('w', encoding='utf-8') as f:
                f.write(header)
                f.writelines(chunk_lines)

            samples_written = len(chunk_lines)
            self._total_samples_written += samples_written
            self._chunks_created += 1

            logger.info(
                f"[CHUNK WRITER] Chunk #{self._chunk_number} guardado: {filename} "
                f"({samples_written:,} muestras, {int(min_inicio)}-{int(min_fin)} min) "
                f"[Rango: {first_sample_ts} -> {last_sample_ts}]"
            )

        except Exception as e:
            logger.error(f"[CHUNK WRITER] Error escribiendo chunk: {e}")

    def finalize_session(self) -> None:
        """Finalizar sesión y escribir el último chunk si hay datos pendientes."""
        # Detener worker thread
        if self._worker_thread and self._worker_thread.is_alive():
            self._stop_event.set()
            self._worker_thread.join(timeout=3.0)

        # Crear chunk final con cualquier dato pendiente
        try:
            self._create_chunk()
        except Exception as e:
            logger.error(f"[CHUNK WRITER] Error creando chunk final: {e}")

        logger.info(
            f"[CHUNK WRITER] Sesión finalizada - {self._chunks_created} chunks creados, "
            f"{self._total_samples_written:,} muestras totales"
        )

        # Reset estado
        self._session_start_time = None
        self._main_csv_path = None
        self._last_line_read = 0
        self._chunk_number = 0


__all__ = ["RealtimeChunkWriter"]
