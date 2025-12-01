"""Generador de chunks basado en timer - NO interfiere con escritura principal."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TimedChunkGenerator:
    """
    Genera chunks cada N minutos copiando del CSV principal.

    Diseño optimizado:
    - Thread separado con timer
    - NO procesa samples individuales
    - Solo copia líneas del CSV periódicamente
    - Mínimo overhead, máxima velocidad
    """

    def __init__(
        self,
        csv_path: Path,
        chunks_dir: Path,
        sensor_id: str,
        chunk_interval_minutes: float = 2.0,
    ):
        self.csv_path = csv_path
        self.chunks_dir = Path(chunks_dir)
        self.sensor_id = sensor_id
        self.chunk_interval_sec = chunk_interval_minutes * 60.0

        self.chunks_dir.mkdir(parents=True, exist_ok=True)

        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._last_line_read = 0
        self._chunk_number = 0
        self._session_start: datetime | None = None

    def start(self, session_start: datetime) -> None:
        """Iniciar generación de chunks."""
        self._session_start = session_start
        self._last_line_read = 0
        self._chunk_number = 0
        self._stop_event.clear()

        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name=f"ChunkGen-{self.sensor_id}"
        )
        self._worker_thread.start()
        logger.info(f"[CHUNK GEN] Iniciado para {self.sensor_id} (intervalo: {self.chunk_interval_sec/60:.1f} min)")

    def _worker_loop(self) -> None:
        """Loop que genera chunks cada N minutos."""
        next_chunk_time = time.time() + self.chunk_interval_sec

        while not self._stop_event.is_set():
            # Esperar hasta el próximo chunk
            wait_time = max(0, next_chunk_time - time.time())
            if self._stop_event.wait(min(wait_time, 1.0)):
                break

            # Generar chunk si es tiempo
            if time.time() >= next_chunk_time:
                try:
                    self._generate_chunk()
                    next_chunk_time = time.time() + self.chunk_interval_sec
                except Exception as e:
                    logger.error(f"[CHUNK GEN] Error: {e}", exc_info=True)

        # Generar último chunk al detener
        try:
            self._generate_chunk()
        except Exception as e:
            logger.error(f"[CHUNK GEN] Error en chunk final: {e}")

    def _generate_chunk(self) -> None:
        """Genera un chunk copiando líneas del CSV principal."""
        if not self.csv_path.exists():
            return

        try:
            # Leer TODO el CSV de una vez (rápido)
            with self.csv_path.open('r', encoding='utf-8') as f:
                all_lines = f.readlines()

            total_lines = len(all_lines)

            # Verificar si hay líneas nuevas
            if total_lines <= self._last_line_read + 1:  # +1 por header
                logger.debug(f"[CHUNK GEN] No hay líneas nuevas (total={total_lines}, last={self._last_line_read})")
                return

            # Extraer header y líneas nuevas
            header = all_lines[0]
            new_lines = all_lines[self._last_line_read + 1:total_lines]

            if not new_lines:
                return

            # Crear nombre de chunk
            min_inicio = self._chunk_number * (self.chunk_interval_sec / 60)
            min_fin = min_inicio + (self.chunk_interval_sec / 60)

            timestamp_str = self._session_start.strftime("%Y%m%d_%H%M%S") if self._session_start else datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"sensor_{self.sensor_id}_acceleration_{timestamp_str}_{int(min_inicio):03d}-{int(min_fin):03d}min.csv"
            filepath = self.chunks_dir / filename

            # Escribir chunk (una sola operación de escritura)
            with filepath.open('w', encoding='utf-8') as f:
                f.write(header)
                f.writelines(new_lines)

            samples_written = len(new_lines)
            self._last_line_read = total_lines - 1
            self._chunk_number += 1

            # Obtener timestamps del chunk
            first_ts = new_lines[0].split(',')[1] if len(new_lines) > 0 and ',' in new_lines[0] else "N/A"
            last_ts = new_lines[-1].split(',')[1] if len(new_lines) > 0 and ',' in new_lines[-1] else "N/A"

            logger.info(
                f"[CHUNK GEN] ✅ Chunk #{self._chunk_number-1}: {filename} "
                f"({samples_written:,} muestras, {min_inicio:.0f}-{min_fin:.0f} min) "
                f"[{first_ts[:19]} → {last_ts[:19]}]"
            )

        except Exception as e:
            logger.error(f"[CHUNK GEN] Error generando chunk: {e}", exc_info=True)

    def stop(self) -> None:
        """Detener generación de chunks."""
        if self._worker_thread and self._worker_thread.is_alive():
            self._stop_event.set()
            self._worker_thread.join(timeout=3.0)

        logger.info(f"[CHUNK GEN] Detenido para {self.sensor_id} (chunks generados: {self._chunk_number})")


__all__ = ["TimedChunkGenerator"]
