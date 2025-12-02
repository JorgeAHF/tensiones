"""
Script para verificar y descargar datos del sensor manualmente.
"""
import sys
sys.path.insert(0, '.')

try:
    import mscl
except ImportError:
    print("Error: MSCL no esta instalado")
    sys.exit(1)


def test_download():
    """Intenta descargar datos del sensor."""
    print("=" * 80)
    print("VERIFICANDO DATOS GUARDADOS EN SENSOR")
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

        # Check if node is in IDLE
        print("\n3. Verificando estado del nodo...")
        try:
            # Try to set to IDLE first
            print("   Poniendo nodo en IDLE...")
            idle_status = node.setToIdle()

            import time
            timeout = 0
            while not idle_status.complete() and timeout < 50:
                time.sleep(0.1)
                timeout += 1

            if idle_status.result() == mscl.SetToIdleStatus.setToIdleResult_success:
                print("   Nodo en IDLE")
            else:
                print(f"   Resultado: {idle_status.result()}")
        except Exception as e:
            print(f"   Error: {e}")

        # Get datalog sessions
        print("\n4. Verificando sesiones de datalogging...")
        try:
            sessions = node.getDatalogSessionInfos()
            print(f"   Sesiones encontradas: {len(sessions)}")

            if len(sessions) == 0:
                print("\n   NO HAY DATOS GUARDADOS EN EL SENSOR")
                print("   Posibles razones:")
                print("   - El nodo NO estaba en modo 'Log' o 'Log and Transmit'")
                print("   - El nodo no inició el muestreo correctamente")
                print("   - La memoria fue borrada")
                return

            # Show session info
            for i, session in enumerate(sessions):
                print(f"\n   Sesión #{i}:")
                try:
                    print(f"   - Start time: {session.startTime()}")
                    print(f"   - Trigger: {session.trigger()}")
                except Exception as e:
                    print(f"   - Error obteniendo info: {e}")

            # Try to download from last session
            print(f"\n5. Intentando descargar sesión #{len(sessions) - 1}...")
            print("   (Esto puede tomar varios minutos...)")

            data_sweeps = node.getDatalogData(len(sessions) - 1)
            print(f"   DESCARGA EXITOSA: {len(data_sweeps)} sweeps")

            # Show sample data
            if len(data_sweeps) > 0:
                first_sweep = data_sweeps[0]
                print(f"\n   Primer sweep:")
                print(f"   - Timestamp: {first_sweep.timestamp().seconds()}")
                print(f"   - Data points: {len(first_sweep.data())}")

                print(f"\n   ✅ EL SENSOR TIENE DATOS GUARDADOS")
                print(f"   Total de sweeps: {len(data_sweeps)}")
                print(f"\n   El problema es que nuestra app NO está descargando los datos")
                print(f"   correctamente cuando presionas 'Set nodes to Idle'")

        except Exception as e:
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_download()
