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
                    # CRÍTICO: Configurar el nodo para muestreo continuo ANTES de usarlo
                    try:
                        LOGGER.info(f"Configuring node {sensor_id} for unlimited duration sampling...")
                        
                        # Obtener configuración del nodo
                        config = node.getConfig()
                        
                        # Configurar para duración ilimitada (no se detiene automáticamente)
                        config.unlimitedDuration(True)
                        
                        # Aplicar configuración
                        node.applyConfig(config)
                        LOGGER.info(f"Node {sensor_id} configured for continuous unlimited sampling!")
                    except AttributeError as attr_err:
                        LOGGER.warning(f"Node API does not support unlimitedDuration: {attr_err}")
                    except Exception as config_err:
                        LOGGER.warning(f"Could not configure node {sensor_id} for unlimited duration: {config_err}")
                    
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
    
    def configure_node(self, sensor_id: str, sample_rate_hz: float, axes: Iterable[str], data_format: str = "float") -> None:
        """Configure node sampling parameters."""
        if sensor_id not in self._sensors:
            raise KeyError(f"Unknown sensor {sensor_id}")
        
        info = self._sensors[sensor_id]
        info.sample_rate_hz = sample_rate_hz
        info.axes = list(axes)
        
        # Configurar formato de datos
        node = self.nodes.get(sensor_id)
        if node:
            try:
                node_config = mscl.WirelessNodeConfig()
                
                # Formato de datos
                if data_format == "uint16":
                    node_config.dataFormat(mscl.WirelessTypes.dataFormat_raw_uint16)
                    LOGGER.info(f"Data format configured: uint16 (raw)")
                else:  # float por defecto
                    node_config.dataFormat(mscl.WirelessTypes.dataFormat_cal_float)
                    LOGGER.info(f"Data format configured: float (calibrated)")
                
                # Aplicar configuración
                node.applyConfig(node_config)
                
            except AttributeError as e:
                LOGGER.warning(f"Could not set data format (API limitation): {e}")
            except Exception as e:
                LOGGER.error(f"Error configuring data format: {e}")
        
        LOGGER.info(f"Configured sensor {sensor_id}: fs={sample_rate_hz}Hz, axes={axes}, format={data_format}")
    
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
                LOGGER.debug(f"Calling getData() - iteration #{loop_iterations}")
                sweeps = self.base_station.getData(500)  # 500ms timeout
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
                    
                    samples_received += 1
                    
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
                    
                    if samples_received % 100 == 1:  # Log every 100th sweep
                        LOGGER.info(f"Received sweep #{samples_received} from node {sensor_id}: {num_samples} samples, accumulated: {len(accumulated_samples)}")
                    
                    if num_samples == 0:
                        LOGGER.warning(f"Sweep has {len(data)} data points, expected multiple of {num_channels}")
                        continue
                    
                    # Parse all samples in this sweep
                    for i in range(num_samples):
                        try:
                            # Get X, Y, Z for this sample
                            idx_base = i * num_channels
                            x = data[idx_base].as_float()
                            y = data[idx_base + 1].as_float()
                            z = data[idx_base + 2].as_float()
                            accumulated_samples.append([x, y, z])
                        except:
                            try:
                                # Try as double
                                x = data[idx_base].as_double()
                                y = data[idx_base + 1].as_double()
                                z = data[idx_base + 2].as_double()
                                accumulated_samples.append([x, y, z])
                            except Exception as parse_err:
                                LOGGER.warning(f"Could not parse sample {i}: {parse_err}")
                                continue
                    
                    # Send accumulated samples in batches (every ~128 samples or ~1 second worth)
                    if len(accumulated_samples) >= 256:
                        # Create numpy array: shape (num_samples, 3)
                        acc_data = np.array(accumulated_samples, dtype=np.float64)
                        
                        batches_sent += 1
                        # Log first 10 batches
                        if batches_sent <= 10:
                            LOGGER.info(f"Batch #{batches_sent}: {len(accumulated_samples)} samples, shape {acc_data.shape}")
                        
                        # NUEVO: Enviar datos al StreamingCoordinator (desacoplado)
                        if self.streaming_coordinator:
                            # Calcular timestamps individuales para cada muestra
                            dt = 1.0 / info.sample_rate_hz  # Delta tiempo entre muestras
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
                            dt = 1.0 / info.sample_rate_hz
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
        """Configure and start sampling using SyncSamplingNetwork with multiple retry strategies."""
        
        # Strategy 1: Try with existing SyncSamplingNetwork (if already created)
        try:
            if self._sync_network is None:
                LOGGER.info("Creating SyncSamplingNetwork...")
                self._sync_network = mscl.SyncSamplingNetwork(self.base_station)
            
            if not self._sync_network_started:
                LOGGER.info(f"Adding node {node.nodeAddress()} to sync network...")
                
                # Give the node time to be ready
                time.sleep(1.0)
                
                # PASO 1: DETENER CUALQUIER SESIÓN DE MUESTREO EXISTENTE
                try:
                    LOGGER.info(f"Stopping any existing sampling session on node {node.nodeAddress()}...")
                    idle_status = node.setToIdle()
                    
                    # Esperar a que complete
                    timeout_counter = 0
                    while not idle_status.complete() and timeout_counter < 50:  # 5 segundos max
                        time.sleep(0.1)
                        timeout_counter += 1
                    
                    if idle_status.result() == mscl.SetToIdleStatus.setToIdleResult_success:
                        LOGGER.info("Node successfully set to IDLE - ready for new configuration")
                    else:
                        LOGGER.warning(f"setToIdle result: {idle_status.result()}")
                        LOGGER.info("Proceeding with configuration anyway...")
                        
                except Exception as idle_err:
                    LOGGER.warning(f"Could not set node to idle: {idle_err}")
                    LOGGER.info("Node may already be idle, proceeding with configuration...")
                
                # PASO 2: CONFIGURAR EL NODO (ahora que está en IDLE)
                try:
                    LOGGER.info(f"Configuring node {node.nodeAddress()} for continuous sync sampling...")
                    
                    # Crear nueva configuración
                    node_config = mscl.WirelessNodeConfig()
                    
                    # CRÍTICO: Modo de muestreo sincronizado
                    node_config.samplingMode(mscl.WirelessTypes.samplingMode_sync)
                    LOGGER.info("Set sampling mode: SYNC")
                    
                    # Configurar frecuencia de muestreo (son constantes, no funciones)
                    if sample_rate_hz == 512:
                        node_config.sampleRate(mscl.WirelessTypes.sampleRate_512Hz)
                    elif sample_rate_hz == 256:
                        node_config.sampleRate(mscl.WirelessTypes.sampleRate_256Hz)
                    elif sample_rate_hz == 128:
                        node_config.sampleRate(mscl.WirelessTypes.sampleRate_128Hz)
                    else:
                        LOGGER.warning(f"Unsupported sample rate {sample_rate_hz}Hz, using 256Hz")
                        node_config.sampleRate(mscl.WirelessTypes.sampleRate_256Hz)
                    
                    # CRÍTICO: Habilitar duración ilimitada
                    node_config.unlimitedDuration(True)
                    LOGGER.info(f"Set unlimitedDuration=True for continuous sampling")
                    
                    # Habilitar canales del acelerómetro (X, Y, Z)
                    channels = mscl.ChannelMask()
                    channels.enable(mscl.WirelessChannel.channel_1)  # X
                    channels.enable(mscl.WirelessChannel.channel_2)  # Y
                    channels.enable(mscl.WirelessChannel.channel_3)  # Z
                    node_config.activeChannels(channels)
                    LOGGER.info("Enabled accelerometer channels: X, Y, Z")
                    
                    # PASO 3: APLICAR configuración al nodo
                    node.applyConfig(node_config)
                    LOGGER.info(f"Node {node.nodeAddress()} configured: SYNC mode, {sample_rate_hz}Hz, unlimited duration")
                    
                    # PASO 4: VERIFICAR configuración aplicada
                    try:
                        actual_rate = node.getSampleRate()
                        actual_unlimited = node.getUnlimitedDuration()
                        LOGGER.info(f"Verified config - Rate: {actual_rate}, Unlimited: {actual_unlimited}")
                    except Exception as verify_err:
                        LOGGER.warning(f"Could not verify configuration: {verify_err}")
                    
                except AttributeError as attr_err:
                    LOGGER.warning(f"Node configuration API not available: {attr_err}")
                    LOGGER.info("Will proceed without explicit configuration")
                except Exception as config_err:
                    LOGGER.error(f"Failed to configure node: {config_err}")
                    LOGGER.info("Will attempt to start with default/existing configuration")
                
                # PASO 5: AGREGAR el nodo a la red de sincronización
                self._sync_network.addNode(node)
                LOGGER.info(f"Node {node.nodeAddress()} added to sync network")
                
                # PASO 6: CONFIGURAR modo lossless
                try:
                    LOGGER.info("Configuring lossless mode...")
                    self._sync_network.lossless(True)
                    LOGGER.info("Lossless mode enabled!")
                except Exception as lossless_err:
                    LOGGER.warning(f"Could not enable lossless mode: {lossless_err}")
                
                # PASO 7: APLICAR configuración de la red
                LOGGER.info("Applying sync network configuration...")
                self._sync_network.applyConfiguration()
                LOGGER.info("Sync network configuration applied")
                
                # PASO 8: INICIAR muestreo
                LOGGER.info("Starting sync sampling network...")
                self._sync_network.startSampling()
                self._sync_network_started = True
                LOGGER.info("SUCCESS: Sync sampling network started - continuous @ {sample_rate_hz}Hz!")
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
        # Don't raise - let it try to read data anyway