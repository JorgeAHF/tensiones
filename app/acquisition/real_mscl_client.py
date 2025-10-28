"""Real MSCL client implementation."""
import logging
import threading
import time
from typing import List, Dict, Any, Callable, Iterable
from dataclasses import dataclass
import numpy as np
import mscl
from app.acquisition.mscl_client import MSCLClient, GatewayStatus, SensorInfo, Sample

LOGGER = logging.getLogger(__name__)


class RealMSCLClient(MSCLClient):
    """Wrapper for real MSCL BaseStation and WirelessNodes."""
    
    def __init__(self, base_station: mscl.BaseStation, sensor_configs: List[Dict[str, Any]], default_fs: float):
        self.base_station = base_station
        self.sensor_configs = sensor_configs
        self.default_fs = default_fs
        self.nodes = {}
        self._sensors = {}  # Dict[str, SensorInfo]
        self._threads: Dict[str, threading.Thread] = {}
        self._stops: Dict[str, threading.Event] = {}
        self._callbacks: Dict[str, Callable[[Sample], None]] = {}
        self._gateway_status = GatewayStatus(host="192.168.8.101", port=5000, connected=True, message="Connected to real MSCL Gateway")
        self._initialize_nodes()
    
    def _initialize_nodes(self):
        """Initialize wireless nodes."""
        LOGGER.info("Scanning for wireless nodes...")
        
        for config in self.sensor_configs:
            sensor_id = str(config['sensor_id'])  # Convertir a string
            stay_id = config.get('stay_id', f'sensor_{sensor_id}')
            
            try:
                LOGGER.info(f"Attempting to connect to node {sensor_id}...")
                node_id_int = int(sensor_id)
                node = mscl.WirelessNode(node_id_int, self.base_station)
                
                # Wait a moment for node to be ready
                time.sleep(0.5)
                
                # Ping node with retries
                ping_success = False
                for attempt in range(3):
                    try:
                        LOGGER.info(f"Ping attempt {attempt + 1}/3 for node {sensor_id}...")
                        ping_response = node.ping()
                        # Ping completed without exception = success
                        rssi_base = ping_response.baseRssi()
                        rssi_node = ping_response.nodeRssi()
                        LOGGER.info(f"Node {sensor_id} connected (RSSI Base: {rssi_base}, Node: {rssi_node})")
                        self.nodes[sensor_id] = node
                        ping_success = True
                        break
                    except Exception as ping_error:
                        LOGGER.warning(f"Ping attempt {attempt + 1} failed for node {sensor_id}: {ping_error}")
                        if attempt < 2:
                            LOGGER.info(f"Retrying in 1 second...")
                            time.sleep(1)
                
                if ping_success:
                    # Create SensorInfo
                    sensor_info = SensorInfo(
                        sensor_id=sensor_id,
                        stay_id=stay_id,
                        sample_rate_hz=self.default_fs,
                        axes=["x", "y", "z"],
                        battery_percent=None
                    )
                    self._sensors[sensor_id] = sensor_info
                    LOGGER.info(f"Registered sensor {sensor_id} ({stay_id})")
                else:
                    LOGGER.error(f"Node {sensor_id} ping failed")
            except Exception as e:
                LOGGER.error(f"Failed to initialize node {sensor_id}: {e}")
    
    
    def connect_gateway(self, host: str, port: int) -> GatewayStatus:
        """Connect to gateway (already connected in __init__)."""
        return self._gateway_status
    
    def disconnect_gateway(self) -> GatewayStatus:
        """Disconnect from gateway."""
        # Stop all streaming
        for sensor_id in list(self._threads):
            self.stop_streaming(sensor_id)
        LOGGER.info("Disconnected from gateway")
        self._gateway_status = GatewayStatus(host=None, port=None, connected=False, message="Disconnected")
        return self._gateway_status
    
    def gateway_status(self) -> GatewayStatus:
        """Return gateway connection status."""
        return self._gateway_status
    
    def list_nodes(self) -> List[SensorInfo]:
        """Return list of SensorInfo objects."""
        return list(self._sensors.values())
    
    def configure_node(self, sensor_id: str, sample_rate_hz: float, axes: Iterable[str]) -> None:
        """Configure node sampling parameters."""
        if sensor_id not in self._sensors:
            raise KeyError(f"Unknown sensor {sensor_id}")
        
        info = self._sensors[sensor_id]
        info.sample_rate_hz = sample_rate_hz
        info.axes = list(axes)
        LOGGER.info(f"Configured sensor {sensor_id}: fs={sample_rate_hz}Hz, axes={axes}")
    
    def start_streaming(self, sensor_id: str, callback: Callable[[Sample], None]) -> None:
        """Start streaming data from a sensor."""
        if sensor_id not in self.nodes:
            LOGGER.warning(f"Cannot start streaming: sensor {sensor_id} not available")
            return
        
        if sensor_id in self._threads:
            LOGGER.warning(f"Sensor {sensor_id} already streaming")
            return
        
        node = self.nodes[sensor_id]
        stop_event = threading.Event()
        self._stops[sensor_id] = stop_event
        self._callbacks[sensor_id] = callback
        
        # Start streaming thread
        thread = threading.Thread(
            target=self._stream_worker,
            args=(sensor_id, node, callback, stop_event),
            daemon=True,
            name=f"Stream-{sensor_id}"
        )
        self._threads[sensor_id] = thread
        thread.start()
        LOGGER.info(f"Started streaming for sensor {sensor_id}")
    
    def stop_streaming(self, sensor_id: str) -> None:
        """Stop streaming data from a sensor."""
        if sensor_id not in self._threads:
            LOGGER.warning(f"Sensor {sensor_id} not streaming")
            return
        
        # Signal thread to stop
        self._stops[sensor_id].set()
        self._threads[sensor_id].join(timeout=2.0)
        
        # Cleanup
        del self._threads[sensor_id]
        del self._stops[sensor_id]
        del self._callbacks[sensor_id]
        
        LOGGER.info(f"Stopped streaming for sensor {sensor_id}")
    
    def _stream_worker(self, sensor_id: str, node: mscl.WirelessNode, callback: Callable[[Sample], None], stop_event: threading.Event) -> None:
        """Worker thread that reads data from node and calls callback."""
        info = self._sensors[sensor_id]
        
        try:
            # Configure and start node sampling
            self._configure_and_start_node(node, info.sample_rate_hz)
            
            while not stop_event.is_set():
                # Get data from base station
                sweeps = self.base_station.getData(500)  # 500ms timeout
                
                for sweep in sweeps:
                    if sweep.nodeAddress() != int(sensor_id):
                        continue
                    
                    # Extract data from sweep
                    timestamp = sweep.timestamp().secondsOfWeek()
                    data = sweep.data()
                    
                    # Convert to numpy array (assuming 3-axis accelerometer)
                    # MSCL data format may vary - adjust as needed
                    if len(data) >= 3:
                        acc_data = np.array([
                            data[0].as_float(),
                            data[1].as_float(),
                            data[2].as_float()
                        ])
                        
                        sample = Sample(
                            sensor_id=sensor_id,
                            stay_id=info.stay_id,
                            fs_hz=info.sample_rate_hz,
                            timestamp=timestamp,
                            acceleration_g=acc_data
                        )
                        
                        callback(sample)
                
                time.sleep(0.01)  # Small delay to prevent CPU spinning
                
        except Exception as e:
            LOGGER.error(f"Error in stream worker for {sensor_id}: {e}")
        finally:
            # Stop node sampling
            try:
                node.stopSampling()
            except Exception as e:
                LOGGER.warning(f"Failed to stop node {sensor_id}: {e}")
    
    def _configure_and_start_node(self, node: mscl.WirelessNode, sample_rate_hz: float) -> None:
        """Configure and start sampling on a node."""
        try:
            config = mscl.WirelessNodeConfig()
            config.defaultMode(mscl.WirelessTypes.defaultMode_idle)
            config.samplingMode(mscl.WirelessTypes.samplingMode_sync)
            
            # Map sample rate to MSCL enum
            if sample_rate_hz == 256:
                config.sampleRate(mscl.WirelessTypes.sampleRate_256Hz)
            elif sample_rate_hz == 512:
                config.sampleRate(mscl.WirelessTypes.sampleRate_512Hz)
            else:
                LOGGER.warning(f"Unsupported sample rate {sample_rate_hz}, using 256Hz")
                config.sampleRate(mscl.WirelessTypes.sampleRate_256Hz)
            
            node.applyConfig(config)
            node.startSampling()
            LOGGER.info(f"Node {node.nodeAddress()} started sampling at {sample_rate_hz}Hz")
        except Exception as e:
            LOGGER.error(f"Failed to configure/start node: {e}")
            raise