"""MSCL client abstraction and demo implementation."""
from __future__ import annotations

import logging
import math
import random
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

    def configure_node(self, sensor_id: str, sample_rate_hz: float, axes: Iterable[str]) -> None:  # pragma: no cover
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

    def configure_node(self, sensor_id: str, sample_rate_hz: float, axes: Iterable[str]) -> None:
        info = self._sensors.get(sensor_id)
        if info is None:
            raise KeyError(f"Unknown sensor {sensor_id}")
        info.sample_rate_hz = sample_rate_hz
        info.axes = list(axes)
        logger.info("Configured demo sensor %s fs=%.2f axes=%s", sensor_id, sample_rate_hz, axes)

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
    "SensorInfo",
    "Sample",
    "GatewayStatus",
    "create_demo_client",
]
