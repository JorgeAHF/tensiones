"""
Script para explorar la API de MSCL y encontrar cómo configurar LXRS+.
"""
import sys
sys.path.insert(0, '.')

try:
    import mscl
except ImportError:
    print("❌ Error: MSCL no está instalado")
    sys.exit(1)


def explore_basestation_methods():
    """Explora todos los métodos disponibles del BaseStation."""
    print("="*80)
    print("EXPLORANDO API DE MSCL")
    print("="*80)

    # Conectar al BaseStation
    try:
        print("\n1. Conectando al BaseStation...")
        connection = mscl.Connection.TcpIp("192.168.8.101", 5000)
        base_station = mscl.BaseStation(connection)
        print("   ✅ Conectado exitosamente")
    except Exception as e:
        print(f"   ❌ Error al conectar: {e}")
        return

    # Listar todos los métodos del BaseStation
    print("\n2. Métodos disponibles en BaseStation:")
    print("   (buscando métodos relacionados con protocol, comm, lxrs)")
    methods = [m for m in dir(base_station) if not m.startswith('_')]

    # Filtrar métodos relevantes
    relevant_keywords = ['protocol', 'comm', 'lxrs', 'plus', 'network', 'config', 'feature']
    relevant_methods = [m for m in methods if any(kw in m.lower() for kw in relevant_keywords)]

    if relevant_methods:
        print("\n   Métodos relevantes encontrados:")
        for method in sorted(relevant_methods):
            print(f"   - {method}")
    else:
        print("\n   No se encontraron métodos con keywords relevantes")
        print("   Mostrando TODOS los métodos disponibles:")
        for method in sorted(methods)[:30]:  # Primeros 30
            print(f"   - {method}")

    # Explorar WirelessTypes para enums relacionados con protocolo
    print("\n3. Enums en WirelessTypes relacionados con protocolo:")
    wireless_types_attrs = [attr for attr in dir(mscl.WirelessTypes) if not attr.startswith('_')]

    protocol_attrs = [attr for attr in wireless_types_attrs if 'protocol' in attr.lower() or 'lxrs' in attr.lower() or 'comm' in attr.lower()]

    if protocol_attrs:
        print("\n   Enums encontrados:")
        for attr in sorted(protocol_attrs):
            try:
                value = getattr(mscl.WirelessTypes, attr)
                print(f"   - WirelessTypes.{attr} = {value}")
            except:
                print(f"   - WirelessTypes.{attr} (no se pudo obtener valor)")
    else:
        print("\n   No se encontraron enums relacionados con protocolo")

    # Intentar obtener features del BaseStation
    print("\n4. Features del BaseStation:")
    try:
        features = base_station.features()
        print(f"   ✅ Features obtenido: {type(features)}")

        # Explorar métodos de features
        feature_methods = [m for m in dir(features) if not m.startswith('_')]
        protocol_features = [m for m in feature_methods if 'protocol' in m.lower() or 'lxrs' in m.lower() or 'comm' in m.lower()]

        if protocol_features:
            print("\n   Métodos de features relacionados con protocolo:")
            for method in sorted(protocol_features):
                print(f"   - features.{method}()")
        else:
            print("\n   Métodos disponibles en features (primeros 20):")
            for method in sorted(feature_methods)[:20]:
                print(f"   - features.{method}()")
    except AttributeError:
        print("   ❌ BaseStation no tiene método features()")
    except Exception as e:
        print(f"   ❌ Error al obtener features: {e}")

    # Explorar SyncSamplingNetwork
    print("\n5. Métodos de SyncSamplingNetwork:")
    try:
        sync_net = mscl.SyncSamplingNetwork(base_station)
        sync_methods = [m for m in dir(sync_net) if not m.startswith('_')]
        protocol_sync = [m for m in sync_methods if 'protocol' in m.lower() or 'lxrs' in m.lower() or 'comm' in m.lower()]

        if protocol_sync:
            print("\n   Métodos relacionados con protocolo:")
            for method in sorted(protocol_sync):
                print(f"   - sync_network.{method}()")
        else:
            print("\n   Métodos disponibles (primeros 20):")
            for method in sorted(sync_methods)[:20]:
                print(f"   - sync_network.{method}()")
    except Exception as e:
        print(f"   ❌ Error al crear SyncSamplingNetwork: {e}")

    # Información básica del BaseStation
    print("\n6. Información del BaseStation:")
    try:
        print(f"   Modelo: {base_station.model()}")
        print(f"   Serial: {base_station.serial()}")
        try:
            fw = base_station.firmwareVersion()
            print(f"   Firmware: {fw.str()}")
        except:
            print(f"   Firmware: (no disponible)")

        try:
            freq = base_station.frequency()
            print(f"   Frecuencia: {freq}")
        except:
            print(f"   Frecuencia: (no disponible)")
    except Exception as e:
        print(f"   ⚠️ Error obteniendo información: {e}")

    # Versión de MSCL
    print("\n7. Versión de MSCL:")
    try:
        version = mscl.version()
        print(f"   Versión: {version}")
    except:
        print("   (no se pudo determinar)")

    print("\n" + "="*80)
    print("INVESTIGACIÓN ADICIONAL:")
    print("="*80)
    print("\nBasado en la documentación de MSCL, el protocolo puede configurarse:")
    print("1. En el BaseStation directamente (método protocol())")
    print("2. En el SyncSamplingNetwork (si tiene método setProtocol() o similar)")
    print("3. Puede ser automático basado en el firmware del BaseStation")
    print("4. Puede configurarse solo desde SensorConnect y persistir")
    print("\nRECOMENDACIÓN:")
    print("- Configura LXRS+ desde SensorConnect")
    print("- Luego ejecuta nuestra app")
    print("- El protocolo debería persistir en el BaseStation")
    print("="*80)


if __name__ == "__main__":
    explore_basestation_methods()
