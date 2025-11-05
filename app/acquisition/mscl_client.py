"""MSCL client abstraction, demo and HTTP stub implementations."""
from __future__ import annotations

import base64
import contextlib
import json
import http.client
import logging
import math
import random
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SensorInfo:
    sensor_id: str
    stay_id: str
    sample_rate_hz: float
    axes: List[str]
    battery_percent: Optional[float] = None


@dataclass
class Sample:
    sensor_id: str
    stay_id: str
    fs_hz: float
    timestamp: float
    acceleration_g: np.ndarray


@dataclass
class GatewayStatus:
    host: Optional[str]
    port: Optional[int]
    connected: bool
    message: str = ""


class MSCLClient:
    """Abstract client that wraps MSCL operations."""

    def connect_gateway(self, host: str, port: int) -> GatewayStatus:  # pragma: no cover - interface
        raise NotImplementedError

    def disconnect_gateway(self) -> GatewayStatus:  # pragma: no cover - interface
        raise NotImplementedError

    def gateway_status(self) -> GatewayStatus:  # pragma: no cover - interface
        raise NotImplementedError

    def list_nodes(self) -> List[SensorInfo]:  # pragma: no cover - interface
        raise NotImplementedError

    def configure_node(
        self,
        sensor_id: str,
        sample_rate_hz: float,
        axes: Iterable[str],
        data_format: str = "float",
        sampling_mode: str = "continuous",
        duration_seconds: Optional[int] = None,
    ) -> None:  # pragma: no cover
        raise NotImplementedError

    def start_streaming(self, sensor_id: str, callback: Callable[[Sample], None]) -> None:  # pragma: no cover
        raise NotImplementedError

    def stop_streaming(self, sensor_id: str) -> None:  # pragma: no cover
        raise NotImplementedError


class DemoMSCLClient(MSCLClient):
    """Demo client that synthesizes accelerometer signals."""

    def __init__(self, sensors: List[SensorInfo], noise_level: float = 0.02) -> None:
        self._sensors = {info.sensor_id: info for info in sensors}
        self._threads: Dict[str, threading.Thread] = {}
        self._stops: Dict[str, threading.Event] = {}
        self._callbacks: Dict[str, Callable[[Sample], None]] = {}
        self._noise_level = noise_level
        self._phase: Dict[str, float] = {info.sensor_id: 0.0 for info in sensors}
        self._gateway_host: Optional[str] = None
        self._gateway_port: Optional[int] = None
        self._connected = False

    def connect_gateway(self, host: str, port: int) -> GatewayStatus:
        self._gateway_host = host
        self._gateway_port = port
        self._connected = True
        logger.info("Connected to demo gateway at %s:%s", host, port)
        return GatewayStatus(host=host, port=port, connected=True, message="Demo gateway conectado")

    def disconnect_gateway(self) -> GatewayStatus:
        for sensor_id in list(self._threads):
            self.stop_streaming(sensor_id)
        logger.info("Disconnected from demo gateway")
        self._connected = False
        status = GatewayStatus(host=self._gateway_host, port=self._gateway_port, connected=False, message="Demo gateway desconectado")
        self._gateway_host = None
        self._gateway_port = None
        return status

    def gateway_status(self) -> GatewayStatus:
        return GatewayStatus(host=self._gateway_host, port=self._gateway_port, connected=self._connected)

    def list_nodes(self) -> List[SensorInfo]:
        if not self._connected:
            logger.debug("Demo gateway not connected; returning empty node list")
            return []
        return list(self._sensors.values())

    def configure_node(
        self,
        sensor_id: str,
        sample_rate_hz: float,
        axes: Iterable[str],
        data_format: str = "float",
        sampling_mode: str = "continuous",
        duration_seconds: Optional[int] = None,
    ) -> None:
        info = self._sensors.get(sensor_id)
        if info is None:
            raise KeyError(f"Unknown sensor {sensor_id}")
        info.sample_rate_hz = sample_rate_hz
        info.axes = list(axes)
        logger.info(
            "Configured demo sensor %s fs=%.2f axes=%s format=%s mode=%s",
            sensor_id,
            sample_rate_hz,
            axes,
            data_format,
            sampling_mode,
        )

    def start_streaming(self, sensor_id: str, callback: Callable[[Sample], None]) -> None:
        if not self._connected:
            logger.warning("Cannot start streaming for %s without gateway connection", sensor_id)
            return
        if sensor_id in self._threads:
            logger.warning("Sensor %s already streaming", sensor_id)
            return
        stop_event = threading.Event()
        self._stops[sensor_id] = stop_event
        info = self._sensors[sensor_id]

        def run() -> None:
            logger.info("Demo stream started for %s", sensor_id)
            dt = 1.0 / info.sample_rate_hz
            t = time.time()
            f1 = random.uniform(1.5, 3.5)
            while not stop_event.is_set():
                samples = []
                for _ in range(int(info.sample_rate_hz)):
                    t += dt
                    base_signal = math.sin(2 * math.pi * f1 * t)
                    noise = np.random.normal(scale=self._noise_level, size=3)
                    accel = np.array([
                        base_signal + noise[0],
                        0.5 * base_signal + noise[1],
                        0.2 * base_signal + noise[2],
                    ])
                    samples.append(accel)
                batch = np.stack(samples)
                sample = Sample(
                    sensor_id=info.sensor_id,
                    stay_id=info.stay_id,
                    fs_hz=info.sample_rate_hz,
                    timestamp=time.time(),
                    acceleration_g=batch,
                )
                callback(sample)
            logger.info("Demo stream stopped for %s", sensor_id)

        thread = threading.Thread(target=run, name=f"DemoStream-{sensor_id}", daemon=True)
        thread.start()
        self._threads[sensor_id] = thread
        self._callbacks[sensor_id] = callback

    def stop_streaming(self, sensor_id: str) -> None:
        event = self._stops.get(sensor_id)
        if event is None:
            return
        event.set()
        thread = self._threads.get(sensor_id)
        if thread is not None:
            thread.join(timeout=1.0)
        self._threads.pop(sensor_id, None)
        self._stops.pop(sensor_id, None)
        self._callbacks.pop(sensor_id, None)


class HttpMSCLClient(MSCLClient):
    """HTTP-based client with automatic reconnection.

    This class is designed as a lightweight stub around a hypothetical
    REST gateway that exposes MSCL operations. When the remote service is
    reachable, the client translates the high level API into HTTP
    requests. If the connection drops, it will try to transparently
    reconnect before issuing new requests.
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        base_path: str = "/api/mscl",
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_ssl: bool = False,
        request_timeout: float = 5.0,
        max_retries: int = 3,
        reconnect_backoff: float = 1.0,
        poll_interval: float = 0.5,
    ) -> None:
        self._host = host
        self._port = port
        self._base_path = base_path.rstrip("/")
        self._username = username
        self._password = password
        self._use_ssl = use_ssl
        self._timeout = request_timeout
        self._max_retries = max(0, max_retries)
        self._reconnect_backoff = max(0.1, reconnect_backoff)
        self._poll_interval = max(0.1, poll_interval)
        self._connection: Optional[http.client.HTTPConnection] = None
        self._gateway_status = GatewayStatus(host=None, port=None, connected=False)
        self._lock = threading.Lock()
        self._streams: Dict[str, threading.Thread] = {}
        self._stream_stops: Dict[str, threading.Event] = {}

    # ------------------------------------------------------------------
    # Helpers
    def _connection_class(self) -> type[http.client.HTTPConnection]:
        return http.client.HTTPSConnection if self._use_ssl else http.client.HTTPConnection

    def _close_connection(self) -> None:
        with self._lock:
            if self._connection is not None:
                logger.debug("Closing HTTP connection to MSCL gateway")
                with contextlib.suppress(Exception):
                    self._connection.close()
                self._connection = None

    def _auth_header(self) -> Dict[str, str]:
        if not self._username:
            return {}
        credentials = f"{self._username}:{self._password or ''}".encode("utf-8")
        token = base64.b64encode(credentials).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    def _update_status(self, *, connected: bool, message: str = "") -> GatewayStatus:
        status = GatewayStatus(
            host=self._host,
            port=self._port,
            connected=connected,
            message=message,
        )
        self._gateway_status = status
        return status

    def _reconnect(self) -> GatewayStatus:
        with self._lock:
            logger.debug(
                "Attempting reconnection to MSCL gateway at %s:%s", self._host, self._port
            )
            self._close_connection()
            try:
                connection = self._connection_class()(self._host, self._port, timeout=self._timeout)
                connection.connect()
            except (OSError, http.client.HTTPException, socket.error) as exc:
                message = f"Fallo de conexión: {exc}".strip()
                logger.warning("Reconnection attempt failed: %s", message)
                return self._update_status(connected=False, message=message)
            self._connection = connection
            logger.info("Connected to MSCL HTTP gateway at %s:%s", self._host, self._port)
            return self._update_status(connected=True, message="Conectado")

    def _ensure_connection(self) -> GatewayStatus:
        status = self._gateway_status
        if status.connected and self._connection is not None:
            return status
        return self._reconnect()

    def _perform_request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> bytes:
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            status = self._ensure_connection()
            if not status.connected or self._connection is None:
                last_exc = ConnectionError(status.message)
                time.sleep(self._reconnect_backoff)
                continue

            request_headers = {"Content-Type": "application/json"}
            request_headers.update(self._auth_header())
            if headers:
                request_headers.update(headers)

            try:
                self._connection.request(
                    method,
                    f"{self._base_path}{path}",
                    body=body,
                    headers=request_headers,
                )
                response = self._connection.getresponse()
                payload = response.read()
            except (OSError, http.client.HTTPException, socket.error) as exc:
                last_exc = exc
                logger.warning(
                    "HTTP request %s %s failed on attempt %s/%s: %s",
                    method,
                    path,
                    attempt + 1,
                    self._max_retries + 1,
                    exc,
                )
                self._update_status(connected=False, message=str(exc))
                time.sleep(self._reconnect_backoff)
                continue

            if 200 <= response.status < 300:
                return payload

            last_exc = RuntimeError(
                f"HTTP {response.status} {response.reason}: {payload.decode('utf-8', 'ignore')}"
            )
            logger.warning(
                "HTTP error response for %s %s: %s", method, path, last_exc
            )
            if response.status in {401, 403}:
                break
            time.sleep(self._reconnect_backoff)

        if last_exc is None:
            last_exc = ConnectionError("Unknown error comunicating with MSCL gateway")
        raise last_exc

    # ------------------------------------------------------------------
    # Public API
    def connect_gateway(self, host: str, port: int) -> GatewayStatus:
        logger.info("Connecting to MSCL HTTP gateway at %s:%s", host, port)
        self._host = host
        self._port = port
        return self._reconnect()

    def disconnect_gateway(self) -> GatewayStatus:
        logger.info("Disconnecting from MSCL HTTP gateway")
        for sensor_id in list(self._streams):
            self.stop_streaming(sensor_id)
        self._close_connection()
        return self._update_status(connected=False, message="Desconectado")

    def gateway_status(self) -> GatewayStatus:
        return self._gateway_status

    def list_nodes(self) -> List[SensorInfo]:
        try:
            payload = self._perform_request("GET", "/nodes")
        except Exception as exc:
            logger.warning("Failed to list nodes: %s", exc)
            return []

        try:
            data = json.loads(payload.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Invalid JSON from MSCL gateway: %s", exc)
            return []

        sensors: List[SensorInfo] = []
        for entry in data or []:
            try:
                sensors.append(
                    SensorInfo(
                        sensor_id=str(entry["sensor_id"]),
                        stay_id=str(entry.get("stay_id", "")),
                        sample_rate_hz=float(entry.get("sample_rate_hz", 0.0)),
                        axes=list(entry.get("axes", [])),
                        battery_percent=(
                            float(entry["battery_percent"])
                            if entry.get("battery_percent") is not None
                            else None
                        ),
                    )
                )
            except Exception as exc:
                logger.debug("Skipping malformed sensor entry %s: %s", entry, exc)
        return sensors

    def configure_node(
        self,
        sensor_id: str,
        sample_rate_hz: float,
        axes: Iterable[str],
        data_format: str = "float",
        sampling_mode: str = "continuous",
        duration_seconds: Optional[int] = None,
    ) -> None:
        body = json.dumps(
            {
                "sample_rate_hz": sample_rate_hz,
                "axes": list(axes),
                "data_format": data_format,
                "sampling_mode": sampling_mode,
                "duration_seconds": duration_seconds,
            }
        ).encode("utf-8")
        self._perform_request("POST", f"/nodes/{sensor_id}/configure", body=body)
        logger.info(
            "Configured sensor %s with fs=%.3f, axes=%s, format=%s, mode=%s via HTTP gateway",
            sensor_id,
            sample_rate_hz,
            list(axes),
            data_format,
            sampling_mode,
        )

    def start_streaming(self, sensor_id: str, callback: Callable[[Sample], None]) -> None:
        if sensor_id in self._streams:
            logger.debug("Sensor %s is already streaming", sensor_id)
            return

        stop_event = threading.Event()
        self._stream_stops[sensor_id] = stop_event

        def run() -> None:
            logger.info("Starting HTTP stream for sensor %s", sensor_id)
            while not stop_event.is_set():
                try:
                    payload = self._perform_request("GET", f"/stream/{sensor_id}")
                except Exception as exc:
                    logger.warning("Stream polling failed for %s: %s", sensor_id, exc)
                    time.sleep(self._reconnect_backoff)
                    continue

                try:
                    data = json.loads(payload.decode("utf-8"))
                except Exception as exc:
                    logger.debug(
                        "Invalid stream payload for %s: %s", sensor_id, exc
                    )
                    time.sleep(self._poll_interval)
                    continue

                samples = np.array(data.get("acceleration_g", []), dtype=float)
                if samples.size == 0:
                    time.sleep(self._poll_interval)
                    continue

                sample = Sample(
                    sensor_id=sensor_id,
                    stay_id=str(data.get("stay_id", "")),
                    fs_hz=float(data.get("fs_hz", samples.shape[0])),
                    timestamp=float(data.get("timestamp", time.time())),
                    acceleration_g=samples,
                )
                callback(sample)
                time.sleep(self._poll_interval)

            logger.info("HTTP stream stopped for sensor %s", sensor_id)

        thread = threading.Thread(
            target=run,
            name=f"HttpMSCLStream-{sensor_id}",
            daemon=True,
        )
        thread.start()
        self._streams[sensor_id] = thread

    def stop_streaming(self, sensor_id: str) -> None:
        stop_event = self._stream_stops.pop(sensor_id, None)
        thread = self._streams.pop(sensor_id, None)
        if stop_event is not None:
            stop_event.set()
        if thread is not None:
            thread.join(timeout=1.0)
        logger.debug("Stopped HTTP streaming for sensor %s", sensor_id)


def create_demo_client(stays_config: List[Dict[str, str]], default_fs: float) -> DemoMSCLClient:
    sensors = [
        SensorInfo(
            sensor_id=stay["sensor_id"],
            stay_id=stay["stay_id"],
            sample_rate_hz=default_fs,
            axes=["x", "y", "z"],
        )
        for stay in stays_config
    ]
    client = DemoMSCLClient(sensors)
    client.connect_gateway("demo-gateway", 5500)
    return client


__all__ = [
    "MSCLClient",
    "DemoMSCLClient",
    "HttpMSCLClient",
    "SensorInfo",
    "Sample",
    "GatewayStatus",
    "create_demo_client",
]
