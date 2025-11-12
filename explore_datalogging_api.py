"""
Script para explorar la API de MSCL relacionada con datalogging.
"""
import sys
sys.path.insert(0, '.')

try:
    import mscl
except ImportError:
    print("Error: MSCL no esta instalado")
    sys.exit(1)


def explore_datalogging_api():
    """Explora los metodos disponibles para datalogging en MSCL."""
    print("="*80)
    print("EXPLORANDO API DE DATALOGGING EN MSCL")
    print("="*80)

    # Conectar
    try:
        print("\n1. Conectando al BaseStation...")
        connection = mscl.Connection.TcpIp("192.168.8.101", 5000)
        base_station = mscl.BaseStation(connection)
        print("   Conectado exitosamente")
    except Exception as e:
        print(f"   Error al conectar: {e}")
        return

    # Obtener nodos
    try:
        print("\n2. Obteniendo nodos...")
        nodes = base_station.getNodeDiscoveries()
        if not nodes:
            print("   No hay nodos descubiertos")
            return

        node_address = nodes[0].nodeAddress
        node = mscl.WirelessNode(node_address, base_station)
        print(f"   Nodo encontrado: {node_address}")
    except Exception as e:
        print(f"   Error obteniendo nodos: {e}")
        return

    # Explorar SamplingModes
    print("\n3. SAMPLING MODES disponibles:")
    try:
        sampling_modes = [attr for attr in dir(mscl.WirelessTypes) if 'samplingMode' in attr]
        print(f"   Modos encontrados: {len(sampling_modes)}")
        for mode in sampling_modes:
            mode_value = getattr(mscl.WirelessTypes, mode)
            print(f"   - {mode} = {mode_value}")
    except Exception as e:
        print(f"   Error: {e}")

    # Explorar metodos de Node relacionados con datalogging
    print("\n4. METODOS DE NODE relacionados con datalogging:")
    try:
        node_methods = dir(node)
        datalog_methods = [m for m in node_methods if 'datalog' in m.lower() or 'log' in m.lower()]
        print(f"   Metodos encontrados: {len(datalog_methods)}")
        for method in datalog_methods:
            print(f"   - {method}")
    except Exception as e:
        print(f"   Error: {e}")

    # Explorar NodeConfig para datalogging
    print("\n5. CONFIGURACION DE NODE para datalogging:")
    try:
        config = node.getNodeConfig()
        config_methods = [m for m in dir(config) if not m.startswith('_')]

        # Buscar metodos relacionados con sampling mode
        sampling_methods = [m for m in config_methods if 'sampling' in m.lower() or 'mode' in m.lower()]
        print(f"   Metodos de sampling/mode encontrados: {len(sampling_methods)}")
        for method in sampling_methods:
            print(f"   - {method}")

        # Buscar metodos relacionados con datalogging
        datalog_config_methods = [m for m in config_methods if 'datalog' in m.lower() or 'log' in m.lower()]
        print(f"\n   Metodos de datalogging encontrados: {len(datalog_config_methods)}")
        for method in datalog_config_methods:
            print(f"   - {method}")
    except Exception as e:
        print(f"   Error: {e}")

    # Explorar metodos de descarga de datos
    print("\n6. METODOS DE DESCARGA de datos:")
    try:
        download_methods = [m for m in node_methods if 'download' in m.lower() or 'get' in m.lower() and 'data' in m.lower()]
        print(f"   Metodos encontrados: {len(download_methods)}")
        for method in download_methods:
            print(f"   - {method}")
    except Exception as e:
        print(f"   Error: {e}")

    # Verificar si el nodo soporta datalogging
    print("\n7. VERIFICAR SOPORTE de datalogging:")
    try:
        features = node.features()
        features_methods = [m for m in dir(features) if 'datalog' in m.lower() or 'supports' in m.lower()]
        print(f"   Metodos de verificacion encontrados: {len(features_methods)}")
        for method in features_methods:
            print(f"   - {method}")

        # Intentar verificar soporte
        if hasattr(features, 'supportsDatalogging'):
            supports = features.supportsDatalogging()
            print(f"\n   Soporta datalogging: {supports}")
    except Exception as e:
        print(f"   Error: {e}")

    # Mostrar ejemplo de configuracion
    print("\n" + "="*80)
    print("EJEMPLO DE USO (basado en API encontrada):")
    print("="*80)
    print("""
# 1. Configurar nodo en modo datalogging:
config = node.getNodeConfig()
config.samplingMode(mscl.WirelessTypes.samplingMode_armedDatalog)
node.applyConfig(config)

# 2. Iniciar datalogging:
node.startDatalog()

# 3. Detener datalogging:
node.stopDatalog()

# 4. Descargar datos:
data = node.getDatalogData()

# 5. Procesar datos:
for sweep in data:
    timestamp = sweep.timestamp()
    samples = sweep.data()
    # Procesar samples...
""")
    print("="*80)


if __name__ == "__main__":
    explore_datalogging_api()
