"""
Script para probar diferentes formas de configurar LXRS+ en MSCL.
"""
import sys
sys.path.insert(0, '.')

try:
    import mscl
except ImportError:
    print("❌ Error: MSCL no está instalado")
    sys.exit(1)


def test_lxrs_plus_configuration():
    """Prueba diferentes métodos para configurar LXRS+."""
    print("="*80)
    print("PROBANDO FORMAS DE CONFIGURAR LXRS+")
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

    # Verificar protocolo actual
    try:
        current_protocol = base_station.communicationProtocol()
        protocol_name = "LXRS" if current_protocol == 0 else "LXRS+" if current_protocol == 1 else "Unknown"
        print(f"\n2. Protocolo actual: {protocol_name}")
    except Exception as e:
        print(f"\n2. Error leyendo protocolo: {e}")
        return

    if current_protocol == 1:
        print("   ✅ Ya está en LXRS+. No es necesario cambiar.")
        return

    # Método 1: Intentar usar features para configurar
    print("\n3. MÉTODO 1: Intentar configurar via BaseStationFeatures...")
    try:
        features = base_station.features()

        # Ver si soporta LXRS+
        if hasattr(features, 'supportsCommunicationProtocol'):
            supports_lxrs_plus = features.supportsCommunicationProtocol(mscl.WirelessTypes.commProtocol_lxrsPlus)
            print(f"   Soporta LXRS+: {supports_lxrs_plus}")

            if not supports_lxrs_plus:
                print("   ❌ El BaseStation NO soporta LXRS+")
                print("   Puede requerir actualización de firmware")
                return

        # Intentar métodos relacionados
        feature_methods = [m for m in dir(features) if 'protocol' in m.lower() or 'set' in m.lower()]
        print(f"   Métodos encontrados en features: {feature_methods}")

    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Método 2: Intentar via configuración del BaseStation
    print("\n4. MÉTODO 2: Intentar via BaseStationConfig...")
    try:
        # Algunos BaseStations tienen un método config()
        if hasattr(base_station, 'config'):
            config = base_station.config()
            print(f"   ✅ Config obtenido: {type(config)}")

            config_methods = [m for m in dir(config) if not m.startswith('_')]
            protocol_methods = [m for m in config_methods if 'protocol' in m.lower()]
            print(f"   Métodos de config: {protocol_methods}")

            # Intentar setCommunicationProtocol o similar
            if hasattr(config, 'setCommunicationProtocol'):
                print("   Intentando config.setCommunicationProtocol()...")
                config.setCommunicationProtocol(mscl.WirelessTypes.commProtocol_lxrsPlus)
                base_station.applyConfig(config)
                print("   ✅ Configuración aplicada")
        else:
            print("   ❌ BaseStation no tiene método config()")

    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Método 3: Via SyncSamplingNetwork
    print("\n5. MÉTODO 3: Intentar via SyncSamplingNetwork...")
    try:
        sync_net = mscl.SyncSamplingNetwork(base_station)

        # Ver qué métodos tiene
        sync_methods = [m for m in dir(sync_net) if not m.startswith('_')]
        protocol_methods = [m for m in sync_methods if 'protocol' in m.lower()]
        print(f"   Métodos de protocolo en sync_net: {protocol_methods}")

        # Probar si tiene un setter
        if hasattr(sync_net, 'communicationProtocol'):
            # Verificar si es getter o setter
            import inspect
            sig = None
            try:
                # En Python 3, podemos inspeccionar la firma
                method = getattr(sync_net, 'communicationProtocol')
                # Intentar con argumento
                print("   Intentando sync_net.communicationProtocol(LXRS+)...")
                sync_net.communicationProtocol(mscl.WirelessTypes.commProtocol_lxrsPlus)
                print("   ✅ Protocolo configurado en SyncSamplingNetwork")
            except TypeError as te:
                print(f"   Es solo getter: {te}")

    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Método 4: Verificar si el protocolo se configura automáticamente
    print("\n6. MÉTODO 4: Verificar configuración automática...")
    print("   Según documentación de MSCL, algunos BaseStations configuran")
    print("   el protocolo automáticamente basado en los nodos conectados.")
    print("   Si todos los nodos soportan LXRS+, se usará LXRS+ automáticamente.")

    # Verificar protocolo final
    try:
        final_protocol = base_station.communicationProtocol()
        final_name = "LXRS" if final_protocol == 0 else "LXRS+" if final_protocol == 1 else "Unknown"
        print(f"\n7. Protocolo final: {final_name}")

        if final_protocol == 1:
            print("   ✅ ÉXITO: LXRS+ está habilitado")
        else:
            print("   ⚠️  Protocolo sigue siendo LXRS")
    except Exception as e:
        print(f"\n7. Error leyendo protocolo final: {e}")

    print("\n" + "="*80)
    print("CONCLUSIÓN:")
    print("="*80)
    print("\nSi ningún método funcionó, el protocolo debe configurarse:")
    print("1. Manualmente en SensorConnect")
    print("2. O se configura automáticamente cuando se inicia el SyncSamplingNetwork")
    print("   con nodos que soporten LXRS+")
    print("\nRECOMENDACIÓN:")
    print("- Configurar LXRS+ en SensorConnect")
    print("- O el protocolo se configurará automáticamente al iniciar sampling")
    print("="*80)


if __name__ == "__main__":
    test_lxrs_plus_configuration()
