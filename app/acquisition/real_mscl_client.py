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
            # Try to configure and start node sampling (may fail if node doesn't support it)
            try:
                self._configure_and_start_node(node, info.sample_rate_hz)
            except Exception as config_error:
                LOGGER.warning(f"Could not configure node {sensor_id}, will try to read existing data: {config_error}")
            
            LOGGER.info(f"Stream worker for {sensor_id} starting data collection loop...")
            node_addr_int = int(sensor_id)
            samples_received = 0
            
            while not stop_event.is_set():
                # Get data from base station
                sweeps = self.base_station.getData(500)  # 500ms timeout
                
                for sweep in sweeps:
                    if sweep.nodeAddress() != node_addr_int:
                        continue
                    
                    samples_received += 1
                    if samples_received % 10 == 1:  # Log every 10th sweep
                        LOGGER.info(f"Received sweep #{samples_received} from node {sensor_id}")
                    
                    # Extract data from sweep
                    timestamp = sweep.timestamp().seconds()  # Get seconds since epoch
                    data = sweep.data()
                    
                    if len(data) == 0:
                        continue
                    
                    # In Sync Sampling mode, data comes as interleaved channels
                    # For 3-axis accel: [X0, Y0, Z0, X1, Y1, Z1, ...]
                    # Each sweep may contain multiple samples
                    
                    num_channels = 3  # X, Y, Z
                    num_samples = len(data) // num_channels
                    
                    if num_samples == 0:
                        LOGGER.warning(f"Sweep has {len(data)} data points, expected multiple of {num_channels}")
                        continue
                    
                    # Parse all samples in this sweep
                    samples_list = []
                    for i in range(num_samples):
                        try:
                            # Get X, Y, Z for this sample
                            idx_base = i * num_channels
                            x = data[idx_base].as_float()
                            y = data[idx_base + 1].as_float()
                            z = data[idx_base + 2].as_float()
                            samples_list.append([x, y, z])
                        except:
                            try:
                                # Try as double
                                x = data[idx_base].as_double()
                                y = data[idx_base + 1].as_double()
                                z = data[idx_base + 2].as_double()
                                samples_list.append([x, y, z])
                            except Exception as parse_err:
                                LOGGER.warning(f"Could not parse sample {i}: {parse_err}")
                                continue
                    
                    if not samples_list:
                        continue
                    
                    # Create numpy array: shape (num_samples, 3)
                    acc_data = np.array(samples_list, dtype=np.float64)
                    
                    # Log first sweep details
                    if samples_received == 1:
                        LOGGER.info(f"First sweep: {num_samples} samples, shape {acc_data.shape}")
                    
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
            LOGGER.info(f"Stream worker for {sensor_id} shutting down...")
            # Don't try to stop the node, it may cause errors
            # try:
            #     if sensor_id in self.nodes:
            #         self.nodes[sensor_id].cyclePower()
            #         LOGGER.info(f"Stopped sampling for node {sensor_id}")
            # except Exception as e:
            #     LOGGER.warning(f"Failed to stop node {sensor_id}: {e}")
    
    def _configure_and_start_node(self, node: mscl.WirelessNode, sample_rate_hz: float) -> None:
        """Configure and start sampling on a node."""
        try:
            # Create basic config without reading from node
            config = mscl.WirelessNodeConfig()
            
            # Set sampling mode to sync sampling
            config.samplingMode(mscl.WirelessTypes.samplingMode_sync)
            
            # Configure active channels (accelerometer X, Y, Z)
            channels = mscl.ChannelMask()
            channels.enable(mscl.WirelessChannel.channel_1)  # X axis
            channels.enable(mscl.WirelessChannel.channel_2)  # Y axis  
            channels.enable(mscl.WirelessChannel.channel_3)  # Z axis
            config.activeChannels(channels)
            
            # Map sample rate to MSCL enum
            if sample_rate_hz == 512:
                config.sampleRate(mscl.WirelessTypes.sampleRate_512Hz)
            elif sample_rate_hz == 256:
                config.sampleRate(mscl.WirelessTypes.sampleRate_256Hz)
            elif sample_rate_hz == 128:
                config.sampleRate(mscl.WirelessTypes.sampleRate_128Hz)
            else:
                LOGGER.warning(f"Unsupported sample rate {sample_rate_hz}, using 256Hz")
                config.sampleRate(mscl.WirelessTypes.sampleRate_256Hz)
            
            # Apply configuration
            node.applyConfig(config)
            LOGGER.info(f"Node {node.nodeAddress()} configured for {sample_rate_hz}Hz sampling")
            
            # Start sampling
            node.startSyncSampling()
            LOGGER.info(f"Node {node.nodeAddress()} started sync sampling")
            
        except Exception as e:
            LOGGER.error(f"Failed to configure/start node: {e}")
            raise
            raise