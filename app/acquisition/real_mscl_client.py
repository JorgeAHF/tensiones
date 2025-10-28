"""Real MSCL client implementation."""
import logging
import time
from typing import List, Dict, Any
from dataclasses import dataclass
import mscl

LOGGER = logging.getLogger(__name__)


@dataclass
class NodeInfo:
    """Information about a wireless node."""
    sensor_id: int
    stay_id: str = ""  # ← AGREGAR ESTA LÍNEA
    model: str = ""
    serial: str = ""
    firmware: str = ""
    rssi: int = 0


class RealMSCLClient:
    """Wrapper for real MSCL BaseStation and WirelessNodes."""
    
    def __init__(self, base_station: mscl.BaseStation, sensor_configs: List[Dict[str, Any]], default_fs: float):
        self.base_station = base_station
        self.sensor_configs = sensor_configs
        self.default_fs = default_fs
        self.nodes = {}
        self.node_info = {}
        self._initialize_nodes()
    
    def _initialize_nodes(self):
        """Initialize wireless nodes."""
        LOGGER.info("Scanning for wireless nodes...")
        
        for config in self.sensor_configs:
            sensor_id = config['sensor_id']
            stay_id = config.get('stay_id', f'sensor_{sensor_id}')  # ← AGREGAR stay_id
            
            try:
                LOGGER.info(f"Attempting to connect to node {sensor_id}...")
                node = mscl.WirelessNode(sensor_id, self.base_station)
                
                # Ping node
                ping_response = node.ping()
                if ping_response.success():
                    rssi = ping_response.nodeRssi()
                    LOGGER.info(f"Node {sensor_id} connected (RSSI Base: {ping_response.baseRssi()}, Node: {rssi})")
                    self.nodes[sensor_id] = node
                    
                    # Get node info
                    try:
                        info = NodeInfo(
                            sensor_id=sensor_id,
                            stay_id=stay_id,  # ← AGREGAR AQUÍ
                            model=str(node.model()),
                            serial=node.serial(),
                            firmware=str(node.firmwareVersion()),
                            rssi=rssi
                        )
                        self.node_info[sensor_id] = info
                    except Exception as e:
                        LOGGER.warning(f"Could not get full info for node {sensor_id}: {e}")
                        self.node_info[sensor_id] = NodeInfo(sensor_id=sensor_id, stay_id=stay_id, rssi=rssi)  # ← Y AQUÍ
                else:
                    LOGGER.error(f"Node {sensor_id} ping failed")
            except Exception as e:
                LOGGER.error(f"Failed to initialize node {sensor_id}: {e}")
    
    def list_nodes(self) -> List[NodeInfo]:
        """Return list of NodeInfo objects."""
        return list(self.node_info.values())
    
    def get_node_info(self, sensor_id: int) -> Dict[str, Any]:
        """Get information about a specific node."""
        if sensor_id not in self.node_info:
            return {}
        
        info = self.node_info[sensor_id]
        return {
            "stay_id": info.stay_id,
            "model": info.model,
            "serial": info.serial,
            "firmware": info.firmware,
            "rssi": info.rssi
        }
    
    def start_sampling(self):
        """Start sampling on all nodes."""
        for sensor_id, node in self.nodes.items():
            try:
                # Configure node for sampling
                config = mscl.WirelessNodeConfig()
                config.defaultMode(mscl.WirelessTypes.defaultMode_idle)
                config.samplingMode(mscl.WirelessTypes.samplingMode_sync)
                config.sampleRate(mscl.WirelessTypes.sampleRate_256Hz)
                
                # Apply config
                node.applyConfig(config)
                
                # Start sampling
                node.startSampling()
                LOGGER.info(f"Node {sensor_id} started sampling")
            except Exception as e:
                LOGGER.error(f"Failed to start sampling on node {sensor_id}: {e}")
    
    def stop_sampling(self):
        """Stop sampling on all nodes."""
        for sensor_id, node in self.nodes.items():
            try:
                node.stopSampling()
                LOGGER.info(f"Node {sensor_id} stopped")
            except Exception as e:
                LOGGER.error(f"Failed to stop node {sensor_id}: {e}")
    
    def get_data_sweeps(self, timeout_ms: int = 500) -> List[Any]:
        """Get data sweeps from base station."""
        try:
            return self.base_station.getData(timeout_ms)
        except Exception as e:
            LOGGER.debug(f"No data available: {e}")
            return []
    
    def discover(self) -> List[int]:
        """Return list of discovered sensor IDs."""
        return list(self.nodes.keys())