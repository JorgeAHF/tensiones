"""
Script de diagnóstico para G-Link-200
Verifica y corrige problemas de configuración de frecuencia.
"""
import mscl
import time

def diagnose_sensor(node_address: int, host: str = "192.168.8.101", port: int = 5000):
    """Diagnostica y muestra configuración actual del sensor."""
    print(f"\n{'='*60}")
    print(f"Diagnóstico de Sensor {node_address}")
    print(f"{'='*60}\n")

    try:
        # Conectar
        print(f"[1] Conectando a gateway {host}:{port}...")
        connection = mscl.Connection.TcpIp(host, port)
        base_station = mscl.BaseStation(connection)
        print("✅ Conectado")

        # Crear nodo
        print(f"\n[2] Creando nodo {node_address}...")
        node = mscl.WirelessNode(node_address, base_station)

        # Verificar comunicación
        print(f"\n[3] Verificando comunicación...")
        if not node.hasLinkAddress(base_station.address()):
            print("❌ El nodo no puede comunicarse con la base station")
            return
        print("✅ Comunicación OK")

        # Leer configuración actual
        print(f"\n[4] Leyendo configuración actual del nodo...")

        # Sample rate
        current_rate_enum = node.getSampleRate()
        print(f"   Sample Rate (enum): {current_rate_enum}")

        # Mapeo de enums a Hz
        rate_map = {
            mscl.WirelessTypes.sampleRate_32Hz: 32,
            mscl.WirelessTypes.sampleRate_64Hz: 64,
            mscl.WirelessTypes.sampleRate_128Hz: 128,
            mscl.WirelessTypes.sampleRate_256Hz: 256,
            mscl.WirelessTypes.sampleRate_512Hz: 512,
            mscl.WirelessTypes.sampleRate_1024Hz: 1024,
            mscl.WirelessTypes.sampleRate_2048Hz: 2048,
            mscl.WirelessTypes.sampleRate_4096Hz: 4096,
        }

        current_hz = rate_map.get(current_rate_enum, "DESCONOCIDO")
        print(f"   ➜ Frecuencia actual: {current_hz} Hz")

        # Sampling mode
        sampling_mode = node.getSamplingMode()
        print(f"   Sampling Mode: {sampling_mode}")

        # Channels activos
        channels = node.getActiveChannels()
        print(f"   Canales activos: {channels}")

        # Data format
        data_format = node.getDataFormat()
        print(f"   Formato de datos: {data_format}")

        # Duration
        unlimited = node.unlimitedDuration()
        print(f"   Duración ilimitada: {unlimited}")

        print(f"\n[5] Diagnóstico completo\n")

        return node, base_station

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def reconfigure_sensor(node, target_hz: int):
    """Reconfigura el sensor a la frecuencia especificada."""
    print(f"\n{'='*60}")
    print(f"Reconfiguración a {target_hz} Hz")
    print(f"{'='*60}\n")

    try:
        # Mapeo de Hz a enum
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

        if target_hz not in rate_map:
            print(f"❌ Frecuencia {target_hz} Hz no soportada")
            print(f"   Frecuencias válidas: {list(rate_map.keys())}")
            return False

        # Crear configuración
        print(f"[1] Creando nueva configuración...")
        config = mscl.WirelessNodeConfig()

        # Configurar parámetros
        config.samplingMode(mscl.WirelessTypes.samplingMode_sync)
        config.sampleRate(rate_map[target_hz])
        config.unlimitedDuration(True)
        config.dataFormat(mscl.WirelessTypes.dataFormat_cal_float)

        # Configurar canales (solo Z para testing)
        channels = mscl.ChannelMask()
        channels.enable(1, True)   # X
        channels.enable(2, True)   # Y
        channels.enable(3, True)   # Z
        config.activeChannels(channels)

        print(f"   ✅ Configuración creada")
        print(f"      - Modo: SYNC")
        print(f"      - Frecuencia: {target_hz} Hz")
        print(f"      - Duración: Ilimitada")
        print(f"      - Formato: Float calibrado")
        print(f"      - Canales: X, Y, Z")

        # Aplicar configuración
        print(f"\n[2] Aplicando configuración al nodo...")
        node.applyConfig(config)
        print(f"   ✅ Configuración aplicada")

        # Esperar un poco
        time.sleep(2)

        # Verificar que se aplicó
        print(f"\n[3] Verificando configuración aplicada...")
        actual_rate = node.getSampleRate()
        rate_map_inv = {v: k for k, v in rate_map.items()}
        actual_hz = rate_map_inv.get(actual_rate, "DESCONOCIDO")

        if actual_hz == target_hz:
            print(f"   ✅ ÉXITO: Sensor configurado a {actual_hz} Hz")
            return True
        else:
            print(f"   ❌ ERROR: Se configuró {target_hz} Hz pero el sensor reporta {actual_hz} Hz")
            return False

    except Exception as e:
        print(f"❌ Error al reconfigurar: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys

    # Argumentos: python diagnose_sensor.py <node_address> [target_hz]
    node_address = int(sys.argv[1]) if len(sys.argv) > 1 else 10603
    target_hz = int(sys.argv[2]) if len(sys.argv) > 2 else None

    # Diagnóstico
    node, base_station = diagnose_sensor(node_address)

    if node and target_hz:
        # Reconfigurar si se especificó frecuencia
        input(f"\n\nPresiona ENTER para reconfigurar a {target_hz} Hz...")
        success = reconfigure_sensor(node, target_hz)

        if success:
            print(f"\n✅ Sensor {node_address} reconfigurado exitosamente a {target_hz} Hz")
            print(f"\nAhora puedes iniciar el monitoreo desde la aplicación web.")
        else:
            print(f"\n❌ No se pudo reconfigurar el sensor")

    print(f"\n{'='*60}\n")
