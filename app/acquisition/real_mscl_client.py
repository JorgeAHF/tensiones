"""Real MSCL client implementation."""
import logging
import threading
import time
from typing import List, Dict, Any, Callable, Iterable, Optional
from dataclasses import dataclass
import numpy as np
import mscl
from app.acquisition.mscl_client import MSCLClient, GatewayStatus, SensorInfo, Sample
from app.acquisition.streaming_coordinator import StreamingCoordinator
from app.sinks.raw_writer import RawStreamingWriter

LOGGER = logging.getLogger(__name__)


class FrequencyDetector:
    """Helper class para detectar la frecuencia REAL de muestreo."""
    
    def __init__(self, window_size: int = 1000):
        self.timestamps = []
        self.window_size = window_size
        self.measured_freq = None
    
    def add_sample(self, timestamp: float):
        """Agrega un timestamp y calcula frecuencia."""
        self.timestamps.append(timestamp)
        
        # Mantener solo los últimos N timestamps
        if len(self.timestamps) > self.window_size:
            self.timestamps.pop(0)
        
        # Calcular frecuencia si tenemos suficientes muestras
        if len(self.timestamps) >= 100:
            time_diff = self.timestamps[-1] - self.timestamps[0]
            if time_diff > 0:
                self.measured_freq = (len(self.timestamps) - 1) / time_diff
    
    def get_frequency(self) -> Optional[float]:
        """Retorna la frecuencia medida, o None si no hay suficientes datos."""
        return self.measured_freq


class RealMSCLClient(MSCLClient):
    """Wrapper for real MSCL BaseStation and WirelessNodes."""
    
    def __init__(
        self, 
        base_station: mscl.BaseStation, 
        sensor_configs: List[Dict[str, Any]], 
        default_fs: float,
        streaming_coordinator: Optional[StreamingCoordinator] = None,
        raw_writer: Optional[RawStreamingWriter] = None,
    ):
        self.base_station = base_station
        self.sensor_configs = sensor_configs
        self.default_fs = default_fs
        self.streaming_coordinator = streaming_coordinator
        self.raw_writer = raw_writer
        self.nodes = {}
        self._sensors = {}  # Dict[str, SensorInfo]
        self._threads: Dict[str, threading.Thread] = {}
        self._stops: Dict[str, threading.Event] = {}
        self._callbacks: Dict[str, Callable[[Sample], None]] = {}
        self._sync_network = None  # Will hold SyncSamplingNetwork
        self._sync_network_started = False
        self._gateway_status = GatewayStatus(host="192.168.8.101", port=5000, connected=True, message="Connected to real MSCL Gateway")
        
        if self.streaming_coordinator:
            LOGGER.info("[OK] RealMSCLClient integrado con StreamingCoordinator")
        
        self._initialize_nodes()
    
    def _initialize_nodes(self):
        """Initialize wireless nodes using auto-discovery."""
        LOGGER.info("=" * 80)
        LOGGER.info("AUTO-DISCOVERY: Scanning for wireless nodes...")
        LOGGER.info("=" * 80)

        discovered_nodes = []

        # METHOD 1: Try auto-discovery from base station beacons
        try:
            LOGGER.info("Method 1: Checking for node discoveries from base station...")
            time.sleep(2)  # Wait for nodes to announce themselves

            node_discoveries = self.base_station.getNodeDiscoveries()
            LOGGER.info(f"Found {len(node_discoveries)} node(s) via auto-discovery")

            for discovery in node_discoveries:
                try:
                    node_address = discovery.nodeAddress()
                    frequency = discovery.frequency()
                    rssi = discovery.rssi()
                    LOGGER.info(f"  - Node {node_address}: freq={frequency}, RSSI={rssi} dBm")
                    discovered_nodes.append(node_address)
                except Exception as disc_err:
                    LOGGER.warning(f"Could not parse discovery: {disc_err}")
        except Exception as e:
            LOGGER.warning(f"Auto-discovery method failed: {e}")

        # METHOD 2: Ping nodes from YAML config (fallback for known nodes)
        LOGGER.info("Method 2: Pinging nodes from configuration file...")
        for config in self.sensor_configs:
            sensor_id_int = int(config['sensor_id'])
            if sensor_id_int not in discovered_nodes:
                LOGGER.info(f"  Trying to ping configured node {sensor_id_int}...")
                discovered_nodes.append(sensor_id_int)

        # METHOD 3: Optional - scan common node ID ranges (commented out for speed)
        # Uncomment if you want to scan for unknown nodes
        # LOGGER.info("Method 3: Scanning common node ID ranges...")
        # for node_id in range(10000, 20000, 1000):  # Scan every 1000th ID
        #     if node_id not in discovered_nodes:
        #         discovered_nodes.append(node_id)

        # Now try to connect to all discovered nodes
        LOGGER.info(f"\nAttempting to connect to {len(discovered_nodes)} discovered node(s)...")

        for node_id_int in discovered_nodes:
            sensor_id = str(node_id_int)

            # Check if node is in config, otherwise use default stay_id
            config_entry = next((c for c in self.sensor_configs if int(c['sensor_id']) == node_id_int), None)
            stay_id = config_entry.get('stay_id', f'sensor_{sensor_id}') if config_entry else f'sensor_{sensor_id}'

            try:
                LOGGER.info(f"\n--- Connecting to Node {sensor_id} ---")
                node = mscl.WirelessNode(node_id_int, self.base_station)

                # Wait for node to be ready
                time.sleep(0.5)

                # Ping node with retries
                ping_success = False
                for attempt in range(3):
                    try:
                        LOGGER.info(f"Ping attempt {attempt + 1}/3 for node {sensor_id}...")
                        ping_response = node.ping()
                        rssi_base = ping_response.baseRssi()
                        rssi_node = ping_response.nodeRssi()
                        LOGGER.info(f"✅ Node {sensor_id} connected! (RSSI Base: {rssi_base}, Node: {rssi_node})")
                        self.nodes[sensor_id] = node
                        ping_success = True
                        break
                    except Exception as ping_error:
                        LOGGER.warning(f"Ping attempt {attempt + 1} failed: {ping_error}")
                        if attempt < 2:
                            time.sleep(1)

                if ping_success:
                    # Get node model and info
                    try:
                        model = node.model()
                        LOGGER.info(f"Node {sensor_id} model: {model}")
                    except:
                        LOGGER.info(f"Node {sensor_id} model: Unknown")

                    # Configure for unlimited duration sampling
                    try:
                        LOGGER.info(f"Configuring node {sensor_id} for continuous sampling...")
                        config = node.getConfig()
                        config.unlimitedDuration(True)
                        node.applyConfig(config)
                        LOGGER.info(f"✅ Node {sensor_id} configured for continuous sampling")
                    except AttributeError:
                        LOGGER.warning(f"Node {sensor_id} API does not support unlimitedDuration")
                    except Exception as config_err:
                        LOGGER.warning(f"Could not configure node {sensor_id}: {config_err}")

                    # Create SensorInfo
                    sensor_info = SensorInfo(
                        sensor_id=sensor_id,
                        stay_id=stay_id,
                        sample_rate_hz=self.default_fs,
                        axes=["x", "y", "z"],
                        battery_percent=None
                    )
                    self._sensors[sensor_id] = sensor_info
                    LOGGER.info(f"✅ Registered sensor {sensor_id} ({stay_id})")
                else:
                    LOGGER.error(f"❌ Node {sensor_id} ping failed after 3 attempts")
            except Exception as e:
                LOGGER.error(f"❌ Failed to initialize node {sensor_id}: {e}")

        LOGGER.info("=" * 80)
        LOGGER.info(f"AUTO-DISCOVERY COMPLETE: {len(self._sensors)} node(s) registered")
        LOGGER.info(f"Nodes: {list(self._sensors.keys())}")
        LOGGER.info("=" * 80)

    def refresh_nodes(self) -> List[SensorInfo]:
        """Re-scan for wireless nodes and update the sensor list.

        This allows discovering new nodes without restarting the application.

        Returns:
            List of newly discovered sensors
        """
        LOGGER.info("\n" + "=" * 80)
        LOGGER.info("REFRESH: Re-scanning for wireless nodes...")
        LOGGER.info("=" * 80)

        # Store current sensors to detect new ones
        previous_sensors = set(self._sensors.keys())

        # Re-run node discovery
        self._initialize_nodes()

        # Find new sensors
        current_sensors = set(self._sensors.keys())
        new_sensors = current_sensors - previous_sensors

        if new_sensors:
            LOGGER.info(f"✅ Discovered {len(new_sensors)} NEW sensor(s): {list(new_sensors)}")
        else:
            LOGGER.info("No new sensors discovered")

        LOGGER.info("=" * 80)

        # Return list of all current sensors
        return list(self._sensors.values())

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
    
    def configure_node(
        self,
        sensor_id: str,
        sample_rate_hz: float,
        axes: Iterable[str],
        data_format: str = "float",
        sampling_mode: str = "continuous",
        duration_seconds: Optional[int] = None,
    ) -> None:
        """Configure node sampling parameters using WirelessNodeConfig.

        Args:
            sensor_id: ID del sensor a configurar
            sample_rate_hz: Frecuencia de muestreo en Hz (>= 32 Hz recomendado)
            axes: Lista de ejes activos ('x', 'y', 'z')
            data_format: Formato de datos ('float' o 'uint16')
            sampling_mode: Modo de muestreo ('continuous', 'duration', 'burst', 'event')
            duration_seconds: Duración en segundos (solo para modo 'duration')
        """
        if sensor_id not in self._sensors:
            raise KeyError(f"Unknown sensor {sensor_id}")

        # Asegurar que sample_rate_hz sea float PRIMERO (puede venir como string desde UI)
        sample_rate_hz = float(sample_rate_hz)

        info = self._sensors[sensor_id]
        info.axes = list(axes)

        node = self.nodes.get(sensor_id)
        if not node:
            LOGGER.error(f"Node {sensor_id} not found in nodes dictionary")
            return

        try:
            # CRÍTICO: Usar WirelessNodeConfig en lugar de métodos individuales
            LOGGER.info(f"Creating WirelessNodeConfig for sensor {sensor_id}")
            node_config = mscl.WirelessNodeConfig()

            # PASO 1: Configurar modo de muestreo sincronizado
            node_config.samplingMode(mscl.WirelessTypes.samplingMode_sync)
            LOGGER.info("Set sampling mode: SYNC")

            # PASO 2: Convertir Hz a enum de MSCL
            rate_enum = self._hz_to_sample_rate_enum(sample_rate_hz)
            node_config.sampleRate(rate_enum)
            LOGGER.info(f"Set sample rate: {sample_rate_hz} Hz (enum: {rate_enum})")

            # PASO 3: Configurar duración según el modo
            if sampling_mode == "continuous":
                node_config.unlimitedDuration(True)
                LOGGER.info("Set sampling mode: CONTINUOUS (unlimited duration)")
            elif sampling_mode == "duration" and duration_seconds:
                node_config.unlimitedDuration(False)
                # Configurar duración en segundos
                # NOTA: La API de MSCL usa "dataCollectionMethod" con tiempo en segundos
                try:
                    # Convertir segundos a milisegundos si es necesario
                    node_config.timeBetweenBursts(mscl.TimeSpan.Seconds(duration_seconds))
                    LOGGER.info(f"Set sampling mode: DURATION ({duration_seconds} seconds)")
                except AttributeError:
                    LOGGER.warning(f"Could not set duration, using unlimited instead")
                    node_config.unlimitedDuration(True)
            elif sampling_mode == "burst":
                LOGGER.warning("Burst mode not fully implemented yet - using continuous mode")
                node_config.unlimitedDuration(True)
            elif sampling_mode == "event":
                LOGGER.warning("Event-driven mode not fully implemented yet - using continuous mode")
                node_config.unlimitedDuration(True)
            else:
                # Default: continuous
                node_config.unlimitedDuration(True)
                LOGGER.info("Set unlimited duration: True (default)")
            
            # PASO 4: Habilitar canales (X, Y, Z)
            channels = mscl.ChannelMask()
            if 'x' in [a.lower() for a in axes]:
                channels.enable(mscl.WirelessChannel.channel_1)  # X
            if 'y' in [a.lower() for a in axes]:
                channels.enable(mscl.WirelessChannel.channel_2)  # Y
            if 'z' in [a.lower() for a in axes]:
                channels.enable(mscl.WirelessChannel.channel_3)  # Z
            node_config.activeChannels(channels)
            LOGGER.info(f"Enabled channels: {axes}")

            # PASO 4.5: Configurar modo de transmisión (defaultMode)
            # CRÍTICO para evitar que el sensor entre en modo datalogging durante gaps
            try:
                node_config.defaultMode(mscl.WirelessTypes.defaultMode_sync)
                LOGGER.info("Default mode: SYNC (continuous real-time transmission)")
            except AttributeError:
                LOGGER.warning("Node API does not support defaultMode - using default behavior")
            except Exception as e:
                LOGGER.warning(f"Could not set defaultMode: {e}")

            # PASO 5: Formato de datos
            # IMPORTANTE: G-Link-200 en modo SYNC solo soporta datos calibrados (float)
            # El formato raw (uint16) NO está soportado en modo SYNC
            if data_format == "uint16":
                LOGGER.error(
                    "⚠️  HARDWARE LIMITATION: G-Link-200 does NOT support uint16 (raw) format in SYNC mode. "
                    "Only calibrated float data is supported. Forcing float format."
                )
                # Forzar float para evitar error de configuración
                node_config.dataFormat(mscl.WirelessTypes.dataFormat_cal_float)
                LOGGER.info("Data format: float (calibrated) - forced due to hardware limitation")
            else:
                node_config.dataFormat(mscl.WirelessTypes.dataFormat_cal_float)
                LOGGER.info("Data format: float (calibrated)")
            
            # PASO 6: APLICAR LA CONFIGURACIÓN (CRÍTICO)
            LOGGER.info(f"Applying configuration to node {sensor_id}...")
            node.applyConfig(node_config)
            LOGGER.info(f"Configuration applied successfully to node {sensor_id}")
            
            # PASO 7: Verificar configuración aplicada
            actual_rate_enum = node.getSampleRate()
            actual_rate_hz = self._sample_rate_enum_to_hz(actual_rate_enum)
            LOGGER.info(f"Verification - Configured rate: {sample_rate_hz} Hz, Actual rate enum: {actual_rate_enum}, Actual rate Hz: {actual_rate_hz} Hz")
            
            # PASO 8: Actualizar info del sensor con frecuencia verificada
            info.sample_rate_hz = actual_rate_hz  # Usar la frecuencia verificada
            
            # Advertencia si no coinciden
            if abs(actual_rate_hz - sample_rate_hz) > 1:
                LOGGER.warning(
                    f"Frequency mismatch for {sensor_id}! "
                    f"Requested: {sample_rate_hz} Hz, Got: {actual_rate_hz} Hz"
                )
            
            # PASO 9: Reconfigurar StreamingCoordinator con frecuencia real
            if self.streaming_coordinator:
                self.streaming_coordinator.reconfigure_sensor(sensor_id, int(actual_rate_hz))
                LOGGER.info(f"StreamingCoordinator reconfigured for {sensor_id} @ {actual_rate_hz}Hz")
            
        except mscl.Error as e:
            LOGGER.error(f"MSCL Error configuring node {sensor_id}: {e}")
            raise
        except Exception as e:
            LOGGER.error(f"Unexpected error configuring node {sensor_id}: {e}")
            raise
    
    def start_streaming(self, sensor_id: str, callback: Callable[[Sample], None]) -> None:
        """Start streaming data from a sensor."""
        import traceback
        import sys
        
        LOGGER.info(f"[START_STREAMING] Called for sensor {sensor_id}")
        
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
        
        LOGGER.info(f"[START_STREAMING] Creating thread for {sensor_id}...")
        
        # Start streaming thread
        try:
            thread = threading.Thread(
                target=self._stream_worker,
                args=(sensor_id, node, callback, stop_event),
                daemon=True,
                name=f"Stream-{sensor_id}"
            )
            self._threads[sensor_id] = thread
            
            LOGGER.info(f"[START_STREAMING] Starting thread for {sensor_id}...")
            thread.start()
            
            LOGGER.info(f"[START_STREAMING] Thread started for sensor {sensor_id} - thread.is_alive()={thread.is_alive()}")
            
            # Give thread a moment to start and check for immediate errors
            import time
            time.sleep(0.5)
            
            if not thread.is_alive():
                error_msg = f"[START_STREAMING] Thread for {sensor_id} died immediately after starting!"
                LOGGER.error(error_msg)
                print(f"\n{'='*80}", file=sys.stderr)
                print(error_msg, file=sys.stderr)
                print(f"{'='*80}\n", file=sys.stderr)
                raise RuntimeError(error_msg)
            
            LOGGER.info(f"Started streaming for sensor {sensor_id}")
            
        except Exception as e:
            error_detail = traceback.format_exc()
            LOGGER.error(
                f"[START_STREAMING] FATAL ERROR creating/starting thread for {sensor_id}:\n"
                f"Error type: {type(e).__name__}\n"
                f"Error message: {str(e)}\n"
                f"Full traceback:\n{error_detail}"
            )
            print(f"\n{'='*80}", file=sys.stderr)
            print(f"[START_STREAMING] FATAL ERROR for {sensor_id}", file=sys.stderr)
            print(f"{'='*80}", file=sys.stderr)
            print(f"Error type: {type(e).__name__}", file=sys.stderr)
            print(f"Error message: {str(e)}", file=sys.stderr)
            print(f"\nFull traceback:", file=sys.stderr)
            print(error_detail, file=sys.stderr)
            print(f"{'='*80}\n", file=sys.stderr)
            raise
    
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

    def reset_sync_network(self) -> None:
        """Reset SyncSamplingNetwork state to allow restarting sampling.

        This should be called after stopping all streams to prepare for a new
        sampling session. It resets the internal state so that initialize_sync_network()
        can be called again.
        """
        LOGGER.info("=" * 80)
        LOGGER.info("RESETTING SyncSamplingNetwork state...")
        LOGGER.info("=" * 80)

        # Reset the flag so the network can be reinitialized
        self._sync_network_started = False

        # Clear the sync network object to force recreation
        self._sync_network = None

        LOGGER.info("SyncSamplingNetwork state reset - ready for new sampling session")
        LOGGER.info("=" * 80)

    def initialize_sync_network(self, sensor_ids: List[str]) -> None:
        """Initialize SyncSamplingNetwork with multiple nodes BEFORE starting streaming.

        This must be called BEFORE start_streaming() when using SYNC mode with multiple sensors.
        It configures the network with all nodes at once, which is required by MSCL.

        Args:
            sensor_ids: List of sensor IDs to include in the sync network
        """
        import time

        LOGGER.info("=" * 80)
        LOGGER.info(f"INITIALIZING SYNC NETWORK with {len(sensor_ids)} nodes: {sensor_ids}")
        LOGGER.info("=" * 80)

        if self._sync_network_started:
            LOGGER.warning("SyncSamplingNetwork already started - skipping initialization")
            return

        try:
            # Create the sync network if it doesn't exist
            if self._sync_network is None:
                LOGGER.info("Creating SyncSamplingNetwork...")
                self._sync_network = mscl.SyncSamplingNetwork(self.base_station)

            # PASO 1: Set all nodes to IDLE first
            for sensor_id in sensor_ids:
                node = self.nodes.get(sensor_id)
                if node is None:
                    LOGGER.warning(f"Node {sensor_id} not found - skipping")
                    continue

                try:
                    LOGGER.info(f"Setting node {sensor_id} to IDLE...")
                    idle_status = node.setToIdle()

                    # Wait for completion
                    timeout_counter = 0
                    while not idle_status.complete() and timeout_counter < 50:
                        time.sleep(0.1)
                        timeout_counter += 1

                    if idle_status.result() == mscl.SetToIdleStatus.setToIdleResult_success:
                        LOGGER.info(f"Node {sensor_id} successfully set to IDLE")
                    else:
                        LOGGER.warning(f"setToIdle result for {sensor_id}: {idle_status.result()}")

                except Exception as e:
                    LOGGER.warning(f"Could not set node {sensor_id} to idle: {e}")

            # PASO 2: Add all nodes to the sync network
            for sensor_id in sensor_ids:
                node = self.nodes.get(sensor_id)
                if node is None:
                    continue

                LOGGER.info(f"Adding node {sensor_id} to sync network...")
                self._sync_network.addNode(node)
                LOGGER.info(f"Node {sensor_id} added to sync network")

            # PASO 3: Configure lossless mode
            try:
                LOGGER.info("Configuring lossless mode...")
                self._sync_network.lossless(True)
                LOGGER.info("Lossless mode enabled!")
            except Exception as e:
                LOGGER.warning(f"Could not enable lossless mode: {e}")

            # PASO 3.2: Try to enable LXRS+ protocol for higher throughput
            # LXRS+: 16,000 samples/s (4x faster than LXRS 4,000 samples/s)
            try:
                LOGGER.info("Attempting to configure LXRS+ protocol...")

                # First check current protocol
                try:
                    current_protocol = self.base_station.communicationProtocol()
                    if current_protocol == mscl.WirelessTypes.commProtocol_lxrs:
                        protocol_name = "LXRS (4,000 samples/s)"
                    elif current_protocol == mscl.WirelessTypes.commProtocol_lxrsPlus:
                        protocol_name = "LXRS+ (16,000 samples/s)"
                    else:
                        protocol_name = f"Unknown ({current_protocol})"

                    LOGGER.info(f"Current protocol: {protocol_name}")

                    # If not LXRS+, try to set it
                    if current_protocol != mscl.WirelessTypes.commProtocol_lxrsPlus:
                        LOGGER.info("Setting protocol to LXRS+...")
                        self.base_station.communicationProtocol(mscl.WirelessTypes.commProtocol_lxrsPlus)

                        # Verify the change
                        new_protocol = self.base_station.communicationProtocol()
                        if new_protocol == mscl.WirelessTypes.commProtocol_lxrsPlus:
                            LOGGER.info("✅ LXRS+ protocol enabled! (16,000 samples/s maximum)")
                        else:
                            LOGGER.warning(f"⚠️  Protocol change failed. Still using: {protocol_name}")
                    else:
                        LOGGER.info("✅ LXRS+ already enabled! (16,000 samples/s maximum)")

                except AttributeError as attr_err:
                    LOGGER.warning(f"communicationProtocol() not available: {attr_err} - using default protocol")
                except Exception as proto_err:
                    LOGGER.warning(f"Could not configure LXRS+ protocol: {proto_err}")
                    LOGGER.warning("WORKAROUND: Configure LXRS+ manually in SensorConnect before running this app")
            except Exception as e:
                LOGGER.warning(f"Error during protocol configuration: {e}")

            # PASO 3.5: Configure retransmission on each node
            # Esto asegura que el modo lossless funcione correctamente
            try:
                LOGGER.info("Configuring retransmission for each node...")
                for sensor_id in sensor_ids:
                    node = self.nodes.get(sensor_id)
                    if node is None:
                        continue

                    try:
                        node_config = node.getConfig()
                        node_config.retransmit(mscl.WirelessTypes.retransmission_on)
                        node.applyConfig(node_config)
                        LOGGER.info(f"Retransmission enabled for node {sensor_id}")
                    except AttributeError:
                        LOGGER.warning(f"Node {sensor_id} API does not support retransmit setting")
                    except Exception as node_err:
                        LOGGER.warning(f"Could not configure retransmission for node {sensor_id}: {node_err}")

                LOGGER.info("Retransmission configuration completed")
            except Exception as e:
                LOGGER.warning(f"Error during retransmission configuration: {e}")

            # PASO 4: Apply configuration
            LOGGER.info("Applying sync network configuration...")
            self._sync_network.applyConfiguration()
            LOGGER.info("Sync network configuration applied")

            # PASO 5: Start sampling
            LOGGER.info("Starting sync sampling network...")
            self._sync_network.startSampling()
            self._sync_network_started = True
            LOGGER.info(f"SUCCESS: Sync sampling network started with {len(sensor_ids)} nodes!")
            LOGGER.info("=" * 80)

        except Exception as e:
            LOGGER.error(f"Failed to initialize sync network: {e}")
            LOGGER.info("Individual nodes will attempt fallback methods when starting streams")

    def _stream_worker(self, sensor_id: str, node: mscl.WirelessNode, callback: Callable[[Sample], None], stop_event: threading.Event) -> None:
        """Worker thread that reads data from node and calls callback."""
        # CRÍTICO: Envolver TODO en try-except para capturar errores del thread
        import traceback
        import sys
        
        # DEBUG: Verificar que LOGGER existe y funciona
        print(f"[DEBUG] Thread {threading.current_thread().name} started", file=sys.stderr)
        print(f"[DEBUG] LOGGER object: {LOGGER}", file=sys.stderr)
        print(f"[DEBUG] LOGGER type: {type(LOGGER)}", file=sys.stderr)
        print(f"[DEBUG] Module globals has LOGGER: {'LOGGER' in globals()}", file=sys.stderr)
        
        info = self._sensors[sensor_id]
        
        # NUEVO: Detector de frecuencia real
        freq_detector = FrequencyDetector(window_size=1000)
        last_freq_report = time.time()
        
        try:
            # Try to configure and start the node with multiple strategies
            LOGGER.info(f"Initializing sampling for node {sensor_id}...")
            self._configure_and_start_node(node, info.sample_rate_hz)
            
            LOGGER.info(f"Stream worker for {sensor_id} starting data collection loop...")
            node_addr_int = int(sensor_id)
            samples_received = 0
            batches_sent = 0
            accumulated_samples = []  # Accumulate samples before sending to callback
            last_data_time = time.time()
            no_data_warnings = 0
            # NOTA: Preventive restart DESHABILITADO - unlimitedDuration(True) mantiene el sampling indefinidamente
            # La API de MSCL Python no tiene stopSampling() en SyncSamplingNetwork
            
            # DEBUG: Contador de iteraciones del loop
            loop_iterations = 0
            while not stop_event.is_set():
                loop_iterations += 1
                
                # DEBUG: Log cada 20 iteraciones (~10 segundos)
                if loop_iterations % 20 == 0:
                    LOGGER.info(f"Stream loop iteration #{loop_iterations} - Still receiving data...")
                
                # Get data from base station
                # Timeout aumentado a 2000ms para manejar mejor ráfagas grandes a alta frecuencia
                LOGGER.debug(f"Calling getData() - iteration #{loop_iterations}")
                sweeps = self.base_station.getData(2000)  # 2000ms timeout (antes 500ms)
                LOGGER.debug(f"getData() returned {len(sweeps)} sweeps")
                
                # Check if we're receiving data
                if len(sweeps) == 0:
                    # No data received in this cycle
                    time_since_last = time.time() - last_data_time
                    if time_since_last > 10.0:  # 10 seconds without data
                        no_data_warnings += 1
                        if no_data_warnings % 5 == 1:  # Log every 5th warning (every ~50s)
                            LOGGER.warning(f"No data from node {sensor_id} for {time_since_last:.1f}s - check hardware LED status")
                else:
                    # Reset timeout counter when we get data
                    last_data_time = time.time()
                    no_data_warnings = 0
                
                for sweep in sweeps:
                    if sweep.nodeAddress() != node_addr_int:
                        continue

                    samples_received += 1  # This counts sweeps, not individual samples

                    # Get current time for frequency reporting (do NOT add to freq_detector here)
                    current_time = time.time()

                    # Reportar frecuencia medida cada 10 segundos
                    if current_time - last_freq_report > 10.0:
                        measured_freq = freq_detector.get_frequency()
                        if measured_freq:
                            # Conversión defensiva: asegurar que sample_rate_hz sea float
                            configured_rate = float(info.sample_rate_hz)
                            
                            LOGGER.info(
                                f"[FREQ CHECK] Sensor {sensor_id} - "
                                f"Configured: {configured_rate} Hz, "
                                f"Measured: {measured_freq:.2f} Hz"
                            )
                            
                            # Advertencia si hay discrepancia > 10%
                            if abs(measured_freq - configured_rate) > configured_rate * 0.1:
                                LOGGER.warning(
                                    f"[FREQ MISMATCH] Sensor {sensor_id} frequency mismatch > 10%! "
                                    f"Expected: {configured_rate} Hz, Got: {measured_freq:.2f} Hz"
                                )
                        
                        last_freq_report = current_time
                    
                    # Extract data from sweep
                    timestamp = sweep.timestamp().seconds()  # Get seconds since epoch
                    data = sweep.data()

                    if len(data) == 0:
                        continue

                    # In Sync Sampling mode, data comes as interleaved channels
                    # For 3-axis accel: [X0, Y0, Z0, X1, Y1, Z1, ...]
                    # For 1-axis: [Z0, Z1, Z2, ...]
                    # Each sweep may contain multiple samples

                    # CRÍTICO: Calcular número de canales dinámicamente basándose en configuración
                    num_channels = len(info.axes)  # Usar ejes configurados
                    if num_channels == 0:
                        num_channels = 3  # Fallback por seguridad

                    num_samples = len(data) // num_channels

                    # Calculate time delta between samples for frequency detection
                    # Conversión defensiva: asegurar que sample_rate_hz sea float
                    configured_rate = float(info.sample_rate_hz)
                    sample_dt = 1.0 / configured_rate if configured_rate > 0 else 0.001
                    
                    if samples_received % 100 == 1:  # Log every 100th sweep
                        LOGGER.info(f"Received sweep #{samples_received} from node {sensor_id}: {num_samples} samples, accumulated: {len(accumulated_samples)}")
                    
                    if num_samples == 0:
                        LOGGER.warning(f"Sweep has {len(data)} data points, expected multiple of {num_channels}")
                        continue
                    
                    # Parse all samples in this sweep
                    for i in range(num_samples):
                        try:
                            # Parsear canales dinámicamente según configuración
                            idx_base = i * num_channels
                            channel_values = []

                            # Intentar primero como float
                            try:
                                for ch in range(num_channels):
                                    channel_values.append(data[idx_base + ch].as_float())
                            except:
                                # Intentar como double
                                channel_values = []
                                for ch in range(num_channels):
                                    channel_values.append(data[idx_base + ch].as_double())

                            # Construir array [x, y, z] basándose en ejes configurados
                            # Siempre crear 3 valores para compatibilidad con el resto del código
                            x, y, z = 0.0, 0.0, 0.0
                            axes_lower = [a.lower() for a in info.axes]

                            for idx, axis in enumerate(axes_lower):
                                if axis == 'x':
                                    x = channel_values[idx]
                                elif axis == 'y':
                                    y = channel_values[idx]
                                elif axis == 'z':
                                    z = channel_values[idx]

                            accumulated_samples.append([x, y, z])

                            # Add timestamp for THIS individual sample to frequency detector
                            # Calculate sample's timestamp: base timestamp + sample index * dt
                            sample_timestamp = timestamp + (i * sample_dt)
                            freq_detector.add_sample(sample_timestamp)

                        except Exception as parse_err:
                            LOGGER.warning(f"Could not parse sample {i}: {parse_err}")
                            continue
                    
                    # Send accumulated samples in batches (more frequent for better latency)
                    # Reduced batch size: transmit every 0.5 seconds instead of 1 second
                    # This reduces buffer accumulation and improves data flow consistency
                    batch_threshold = max(int(info.sample_rate_hz) // 2, 32)  # At least 32 samples, or 0.5 second of data
                    if len(accumulated_samples) >= batch_threshold:
                        # Create numpy array: shape (num_samples, 3)
                        acc_data = np.array(accumulated_samples, dtype=np.float64)
                        
                        batches_sent += 1
                        # Log first 10 batches
                        if batches_sent <= 10:
                            LOGGER.info(f"Batch #{batches_sent}: {len(accumulated_samples)} samples, shape {acc_data.shape}")
                        
                        # VERIFICACIÓN: Después del 5to batch, mostrar frecuencia almacenada vs medida
                        if batches_sent == 5:
                            import sys
                            print("\n" + "="*80, file=sys.stderr)
                            print(f"📊 VERIFICACIÓN DE FRECUENCIA - Sensor {sensor_id}", file=sys.stderr)
                            print("="*80, file=sys.stderr)
                            print(f"   Frecuencia en info.sample_rate_hz: {info.sample_rate_hz} Hz", file=sys.stderr)
                            print(f"   Tamaño de batch (0.5 segundo de datos): {batch_threshold} samples", file=sys.stderr)
                            print(f"   Samples por batch REAL: {len(accumulated_samples)} samples", file=sys.stderr)
                            if len(accumulated_samples) != batch_threshold:
                                print(f"   ⚠️  DISCREPANCIA DETECTADA!", file=sys.stderr)
                                print(f"   La frecuencia REAL podría ser ~{len(accumulated_samples)} Hz", file=sys.stderr)
                            else:
                                print(f"   ✅ Frecuencia coincide con configuración", file=sys.stderr)
                            print("="*80 + "\n", file=sys.stderr)
                        
                        # NUEVO: Enviar datos al StreamingCoordinator (desacoplado)
                        if self.streaming_coordinator:
                            # Calcular timestamps individuales para cada muestra
                            # Conversión defensiva: asegurar que sample_rate_hz sea float
                            sample_rate = float(info.sample_rate_hz) if isinstance(info.sample_rate_hz, str) else info.sample_rate_hz
                            dt = 1.0 / sample_rate  # Delta tiempo entre muestras
                            samples_for_coordinator = [
                                (timestamp + i * dt, x, y, z)
                                for i, (x, y, z) in enumerate(accumulated_samples)
                            ]
                            if self.raw_writer:
                                try:
                                    self.raw_writer.append_batch(sensor_id, samples_for_coordinator)
                                except Exception as writer_err:
                                    LOGGER.warning(
                                        "[RAW] Error guardando lote para %s: %s",
                                        sensor_id,
                                        writer_err,
                                    )
                            self.streaming_coordinator.add_samples_batch(sensor_id, samples_for_coordinator)
                        elif self.raw_writer:
                            # Conversión defensiva: asegurar que sample_rate_hz sea float
                            sample_rate = float(info.sample_rate_hz) if isinstance(info.sample_rate_hz, str) else info.sample_rate_hz
                            dt = 1.0 / sample_rate
                            samples_for_writer = [
                                (timestamp + i * dt, x, y, z)
                                for i, (x, y, z) in enumerate(accumulated_samples)
                            ]
                            try:
                                self.raw_writer.append_batch(sensor_id, samples_for_writer)
                            except Exception as writer_err:
                                LOGGER.warning(
                                    "[RAW] Error guardando lote para %s sin coordinator: %s",
                                    sensor_id,
                                    writer_err,
                                )

                        # EXISTENTE: Mantener callback para compatibilidad con StreamManager
                        sample = Sample(
                            sensor_id=sensor_id,
                            stay_id=info.stay_id,
                            fs_hz=info.sample_rate_hz,
                            timestamp=timestamp,
                            acceleration_g=acc_data
                        )
                        
                        callback(sample)
                        accumulated_samples = []  # Reset accumulator
                
                time.sleep(0.01)  # Small delay to prevent CPU spinning
        
        except Exception as e:
            # CRÍTICO: Capturar y registrar CUALQUIER excepción con traceback completo
            error_msg = f"FATAL ERROR in stream worker for {sensor_id}"
            full_traceback = traceback.format_exc()
            
            # Registrar en el logger con traceback completo
            LOGGER.error(f"{error_msg}:\n{full_traceback}")
            
            # También imprimir a stderr para debugging
            print(f"\n{'='*80}", file=sys.stderr)
            print(f"{error_msg}", file=sys.stderr)
            print(f"{'='*80}", file=sys.stderr)
            print(full_traceback, file=sys.stderr)
            print(f"{'='*80}\n", file=sys.stderr)
            
            # Re-lanzar la excepción para que el caller pueda manejarla
            raise
        
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
        """Start sampling using SyncSamplingNetwork (configuration already applied in configure_node).

        IMPORTANTE: Este método NO debe reconfigurar el nodo. La configuración ya se aplicó
        en configure_node() y debe respetarse. Este método solo agrega el nodo a la red
        de sincronización e inicia el sampling.
        """
        import traceback
        import sys

        try:
            # If sync network is already started, don't try to modify it
            # This happens when initialize_sync_network() was called before start_streaming()
            if self._sync_network_started:
                LOGGER.info(f"SyncSamplingNetwork already running - node {node.nodeAddress()} should already be part of it")
                LOGGER.info("Skipping node initialization (already done by initialize_sync_network)")
                return  # Success - network is already running

            # Legacy path: If initialize_sync_network() wasn't called, try to start with just this node
            LOGGER.warning("SyncSamplingNetwork not initialized - attempting legacy single-node start...")
            LOGGER.warning("For multiple sensors, call initialize_sync_network() before start_streaming()")

            if self._sync_network is None:
                LOGGER.info("Creating SyncSamplingNetwork...")
                self._sync_network = mscl.SyncSamplingNetwork(self.base_station)

            LOGGER.info(f"Adding node {node.nodeAddress()} to sync network...")

            # Give the node time to be ready
            time.sleep(1.0)

            # Set node to IDLE
            try:
                LOGGER.info(f"Stopping any existing sampling session on node {node.nodeAddress()}...")
                idle_status = node.setToIdle()

                timeout_counter = 0
                while not idle_status.complete() and timeout_counter < 50:
                    time.sleep(0.1)
                    timeout_counter += 1

                if idle_status.result() == mscl.SetToIdleStatus.setToIdleResult_success:
                    LOGGER.info("Node successfully set to IDLE")
                else:
                    LOGGER.warning(f"setToIdle result: {idle_status.result()}")

            except Exception as idle_err:
                LOGGER.warning(f"Could not set node to idle: {idle_err}")

            # Add node to network
            self._sync_network.addNode(node)
            LOGGER.info(f"Node {node.nodeAddress()} added to sync network")

            # Configure lossless mode
            try:
                LOGGER.info("Configuring lossless mode...")
                self._sync_network.lossless(True)
                LOGGER.info("Lossless mode enabled!")
            except Exception as lossless_err:
                LOGGER.warning(f"Could not enable lossless mode: {lossless_err}")

            # Apply configuration
            LOGGER.info("Applying sync network configuration...")
            self._sync_network.applyConfiguration()
            LOGGER.info("Sync network configuration applied")

            # Start sampling
            LOGGER.info("Starting sync sampling network...")
            self._sync_network.startSampling()
            self._sync_network_started = True
            LOGGER.info(f"SUCCESS: Sync sampling network started!")

            return  # Success!
                
        except Exception as e:
            LOGGER.error(f"Failed to configure/start sync network: {e}")
            LOGGER.info("Will attempt alternative initialization method...")
            
        # Strategy 2: Try to use node's individual startSyncSampling
        try:
            LOGGER.info(f"Trying individual node.startSyncSampling() for node {node.nodeAddress()}...")
            # Some MSCL versions support starting sync sampling directly on the node
            node.startSyncSampling()
            self._sync_network_started = True
            LOGGER.info("SUCCESS: Node sync sampling started individually!")
            return  # Success!
        except AttributeError:
            LOGGER.info("Node does not support individual startSyncSampling()")
        except Exception as e:
            LOGGER.warning(f"Individual sync sampling failed: {e}")
        
        # Strategy 3: Try simple node.startSampling() (works for G-Link-200)
        try:
            LOGGER.info(f"Trying simple node.startSampling() for node {node.nodeAddress()}...")
            node.startSampling()
            self._sync_network_started = True
            LOGGER.info("SUCCESS: Node sampling started with node.startSampling()!")
            return  # Success!
        except Exception as e:
            LOGGER.warning(f"Simple node.startSampling() failed: {e}")
        
        # Strategy 4: Check if network is already running from external source
        LOGGER.info("Checking if SyncSamplingNetwork is already active from external source (e.g., SensorConnect)...")
        LOGGER.info("Application will attempt to read data from existing sampling session")
    
    def _hz_to_sample_rate_enum(self, hz: float) -> 'mscl.WirelessTypes.WirelessSampleRate':
        """
        Convierte frecuencia en Hz a enum de MSCL.

        G-Link-200 soporta estas frecuencias en modo SYNC:
        32, 64, 128, 256, 512, 1024, 2048, 4096 Hz

        IMPORTANTE: Según la documentación de LORD MicroStrain:
        - Frecuencias >= 32 Hz están completamente soportadas en modo SYNC
        - Frecuencias < 32 Hz pueden tener problemas de transferencia de datos con 3 canales
        - El hardware puede NO respetar frecuencias < 32 Hz y usar 256 Hz por defecto

        Referencias:
        - LORD MicroStrain User Manual: "data transfer considerations become relevant
          when using 3 channels on G-Link-200 with a sample rate 32Hz and less"
        """
        # Mapeo de Hz a enums de MSCL (solo frecuencias >= 32 Hz)
        rate_map = {
            32: mscl.WirelessTypes.sampleRate_32Hz,
            64: mscl.WirelessTypes.sampleRate_64Hz,
            128: mscl.WirelessTypes.sampleRate_128Hz,
            256: mscl.WirelessTypes.sampleRate_256Hz,
            512: mscl.WirelessTypes.sampleRate_512Hz,
            1024: mscl.WirelessTypes.sampleRate_1024Hz,
            2048: mscl.WirelessTypes.sampleRate_2048Hz,
            4096: mscl.WirelessTypes.sampleRate_4096Hz,
        }

        hz_int = int(hz)

        # Validación: Advertir sobre frecuencias no soportadas
        if hz_int < 32:
            LOGGER.error(
                f"⚠️  HARDWARE LIMITATION: Sample rate {hz} Hz is below 32 Hz. "
                f"G-Link-200 may NOT support frequencies < 32 Hz in SYNC mode with 3 channels. "
                f"The hardware will likely default to 256 Hz. "
                f"Consider using >= 32 Hz for reliable operation."
            )
            # Usar 256 Hz como fallback seguro
            return mscl.WirelessTypes.sampleRate_256Hz

        if hz_int not in rate_map:
            supported = list(rate_map.keys())
            LOGGER.warning(
                f"Unsupported sample rate: {hz} Hz. "
                f"Supported rates for G-Link-200 in SYNC mode: {supported}. "
                f"Using closest supported rate..."
            )
            # Encontrar la frecuencia más cercana
            hz_int = min(supported, key=lambda x: abs(x - hz))
            LOGGER.info(f"Selected closest rate: {hz_int} Hz")

        return rate_map[hz_int]
    
    def _sample_rate_enum_to_hz(self, rate_enum: 'mscl.WirelessTypes.WirelessSampleRate') -> float:
        """
        Convierte enum de MSCL a frecuencia en Hz.
        
        IMPORTANTE: getSampleRate() retorna un enum, NO Hz directamente.
        """
        # Mapeo inverso de enums a Hz
        enum_map = {
            mscl.WirelessTypes.sampleRate_32Hz: 32.0,
            mscl.WirelessTypes.sampleRate_64Hz: 64.0,
            mscl.WirelessTypes.sampleRate_128Hz: 128.0,
            mscl.WirelessTypes.sampleRate_256Hz: 256.0,
            mscl.WirelessTypes.sampleRate_512Hz: 512.0,
            mscl.WirelessTypes.sampleRate_1024Hz: 1024.0,
            mscl.WirelessTypes.sampleRate_2048Hz: 2048.0,
            mscl.WirelessTypes.sampleRate_4096Hz: 4096.0,
        }
        
        if rate_enum in enum_map:
            return enum_map[rate_enum]
        else:
            # Si no está en el mapa, intentar convertir directamente
            # (algunos enums pueden tener método samples_per_second())
            try:
                if hasattr(rate_enum, 'samples_per_second'):
                    return float(rate_enum.samples_per_second())
            except:
                pass
            
            LOGGER.warning(f"Unknown sample rate enum: {rate_enum}, defaulting to 256 Hz")
            return 256.0
    
    def get_supported_sample_rates(self) -> List[float]:
        """Retorna lista de frecuencias soportadas por G-Link-200 en modo SYNC.

        NOTA: Solo se incluyen frecuencias >= 32 Hz debido a limitaciones de hardware
        documentadas por LORD MicroStrain. Frecuencias menores pueden no ser respetadas
        por el dispositivo en modo SYNC con 3 canales activos.
        """
        return [32.0, 64.0, 128.0, 256.0, 512.0, 1024.0, 2048.0, 4096.0]