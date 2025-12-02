"""
Script para verificar qué modos de sampling soporta el G-Link-200.
"""
import sys
sys.path.insert(0, '.')

try:
    import mscl
except ImportError:
    print("Error: MSCL no esta instalado")
    sys.exit(1)


def check_supported_modes():
    """Verifica qué modos de sampling soporta el nodo."""
    print("=" * 80)
    print("VERIFICANDO MODOS SOPORTADOS POR G-LINK-200")
    print("=" * 80)

    try:
        # Connect
        print("\n1. Conectando al BaseStation...")
        connection = mscl.Connection.TcpIp("192.168.8.101", 5000)
        base_station = mscl.BaseStation(connection)
        print("   Conectado exitosamente")

        # Get node
        print("\n2. Obteniendo nodos...")
        nodes = base_station.getNodeDiscoveries()
        if not nodes:
            print("   No hay nodos descubiertos")
            return

        node_address = nodes[0].nodeAddress
        node = mscl.WirelessNode(node_address, base_station)
        print(f"   Nodo encontrado: {node_address}")

        # Get features
        print("\n3. Obteniendo features del nodo...")
        features = node.features()

        # Check all sampling modes
        print("\n4. Verificando modos de sampling soportados:")

        sampling_modes = [
            ("SYNC", mscl.WirelessTypes.samplingMode_sync),
            ("NON-SYNC", mscl.WirelessTypes.samplingMode_nonSync),
            ("SYNC BURST", mscl.WirelessTypes.samplingMode_syncBurst),
            ("ARMED DATALOGGING", mscl.WirelessTypes.samplingMode_armedDatalog),
        ]

        supported_modes = []
        for mode_name, mode_enum in sampling_modes:
            try:
                supported = features.supportsSamplingMode(mode_enum)
                status = "SI" if supported else "NO"
                symbol = "✓" if supported else "✗"
                print(f"   [{symbol}] {mode_name}: {status}")
                if supported:
                    supported_modes.append(mode_name)
            except Exception as e:
                print(f"   [?] {mode_name}: Error al verificar - {e}")

        # Check datalogging support
        print("\n5. Verificando soporte de datalogging:")
        try:
            if hasattr(features, 'supportsDatalogging'):
                supports_datalog = features.supportsDatalogging()
                print(f"   supportsDatalogging(): {supports_datalog}")
            else:
                print("   supportsDatalogging() no disponible en esta API")
        except Exception as e:
            print(f"   Error: {e}")

        # Get model info
        print("\n6. Información del modelo:")
        try:
            model = node.model()
            print(f"   Modelo: {model}")
            print(f"   Serial: {node.serial()}")
            try:
                fw = node.firmwareVersion()
                print(f"   Firmware: {fw.str()}")
            except:
                pass
        except Exception as e:
            print(f"   Error obteniendo info: {e}")

        # Summary
        print("\n" + "=" * 80)
        print("RESUMEN")
        print("=" * 80)
        if supported_modes:
            print(f"\nModos soportados: {', '.join(supported_modes)}")
        else:
            print("\nNo se encontraron modos soportados")

        if "ARMED DATALOGGING" not in supported_modes:
            print("\n⚠️  CONCLUSIÓN: El G-Link-200 NO soporta datalogging")
            print("   La única forma de capturar datos es via transmisión wireless (SYNC mode)")
            print("   Limitación: ~64 Hz máximo con 100% de datos")
        print("=" * 80)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_supported_modes()
