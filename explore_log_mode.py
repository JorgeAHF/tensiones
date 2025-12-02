"""
Script para explorar cómo configurar el modo Log/Transmit en G-Link-200.
"""
import sys
sys.path.insert(0, '.')

try:
    import mscl
except ImportError:
    print("Error: MSCL no esta instalado")
    sys.exit(1)


def explore_log_mode():
    """Explora la configuración de modo Log/Transmit."""
    print("=" * 80)
    print("EXPLORANDO CONFIGURACION DE MODO LOG/TRANSMIT")
    print("=" * 80)

    try:
        # Connect
        print("\n1. Conectando al BaseStation...")
        connection = mscl.Connection.TcpIp("192.168.8.101", 5000)
        base_station = mscl.BaseStation(connection)
        print("   Conectado exitosamente")

        # Get node
        print("\n2. Obteniendo nodo...")
        nodes = base_station.getNodeDiscoveries()
        if not nodes:
            print("   No hay nodos descubiertos")
            return

        node_address = nodes[0].nodeAddress
        node = mscl.WirelessNode(node_address, base_station)
        print(f"   Nodo encontrado: {node_address}")

        # Get current config
        print("\n3. Obteniendo configuración actual...")
        config = node.getConfig()

        # List all methods related to log/transmit/mode/default
        print("\n4. Métodos de configuración disponibles:")
        config_methods = [m for m in dir(config) if not m.startswith('_')]

        # Filter relevant methods
        relevant = [m for m in config_methods if any(keyword in m.lower() for keyword in
                   ['log', 'transmit', 'mode', 'default', 'datalog', 'collection'])]

        print(f"   Métodos relevantes encontrados: {len(relevant)}")
        for method in sorted(relevant):
            print(f"   - {method}")

        # Try to get current values
        print("\n5. Valores actuales:")

        # Check defaultMode
        if hasattr(config, 'defaultMode'):
            try:
                current_mode = config.defaultMode()
                print(f"   defaultMode: {current_mode}")

                # Show available modes
                print("\n   Modos disponibles (WirelessTypes.defaultMode_*):")
                default_modes = [attr for attr in dir(mscl.WirelessTypes) if 'defaultMode' in attr]
                for mode in sorted(default_modes):
                    mode_value = getattr(mscl.WirelessTypes, mode)
                    print(f"   - {mode} = {mode_value}")
            except Exception as e:
                print(f"   Error leyendo defaultMode: {e}")

        # Check dataCollectionMethod
        if hasattr(config, 'dataCollectionMethod'):
            try:
                current_method = config.dataCollectionMethod()
                print(f"\n   dataCollectionMethod: {current_method}")

                # Show available methods
                print("\n   Métodos disponibles (WirelessTypes.collectionMethod_*):")
                collection_methods = [attr for attr in dir(mscl.WirelessTypes) if 'collectionMethod' in attr]
                for method in sorted(collection_methods):
                    method_value = getattr(mscl.WirelessTypes, method)
                    print(f"   - {method} = {method_value}")
            except Exception as e:
                print(f"   Error leyendo dataCollectionMethod: {e}")

        # Check samplingMode
        print("\n6. Sampling mode actual:")
        try:
            sampling_mode = config.samplingMode()
            print(f"   samplingMode: {sampling_mode}")
        except Exception as e:
            print(f"   Error: {e}")

        # Try to find Log/Transmit setting
        print("\n7. Buscando configuración Log/Transmit...")
        potential_settings = ['logMode', 'transmitMode', 'dataMode', 'loggingMode',
                             'defaultMode', 'dataCollectionMethod']

        for setting in potential_settings:
            if hasattr(config, setting):
                try:
                    value = getattr(config, setting)
                    if callable(value):
                        value = value()
                    print(f"   ✓ {setting}: {value}")
                except Exception as e:
                    print(f"   ✗ {setting}: Error - {e}")

        print("\n" + "=" * 80)
        print("CONCLUSIÓN")
        print("=" * 80)
        print("\nPara configurar modo Log en G-Link-200:")
        print("1. Revisar si 'defaultMode' controla Log vs Transmit")
        print("2. O configurar en SensorConnect y solo descargar datos desde Python")
        print("=" * 80)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    explore_log_mode()
