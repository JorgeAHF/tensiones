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

        # Verificar comunicación (ping)
        print(f"\n[3] Verificando comunicación...")
        try:
            ping_response = node.ping()
            if ping_response.success():
                print(f"✅ Comunicación OK")
                # Intentar obtener RSSI si está disponible
                try:
                    rssi = ping_response.nodeRSSI()
                    print(f"   RSSI del nodo: {rssi} dBm")
                except:
                    pass
            else:
                print("❌ El nodo no respondió al ping")
                return
        except Exception as e:
            print(f"⚠️  No se pudo hacer ping, continuando... ({e})")
            # Continuar de todas formas

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
        channel_list = []
        if channels.enabled(1):  # X
            channel_list.append("X")
        if channels.enabled(2):  # Y
            channel_list.append("Y")
        if channels.enabled(3):  # Z
            channel_list.append("Z")
        print(f"   Canales activos: {', '.join(channel_list) if channel_list else 'Ninguno'}")

        # Data format
        data_format = node.getDataFormat()
        format_map = {
            2: "Float 32-bit (calibrado)",
            1: "UInt16 (raw)",
        }
        format_str = format_map.get(data_format, f"Desconocido ({data_format})")
        print(f"   Formato de datos: {format_str}")

        # Duration
        unlimited = node.getUnlimitedDuration()
        print(f"   Duración ilimitada: {'Sí' if unlimited else 'No'}")

        # Información adicional de radio/comunicación
        print(f"\n[5] Diagnóstico de comunicación...")
        try:
            # Protocol
            protocol = base_station.protocol()
            protocol_map = {
                1: "LXRS (4,000 samples/s por canal)",
                2: "LXRS+ (16,000 samples/s por canal)",
            }
            protocol_str = protocol_map.get(protocol, f"Desconocido ({protocol})")
            print(f"   Protocol de base station: {protocol_str}")

            # Transmit power
            try:
                tx_power = node.getTransmitPower()
                print(f"   Potencia de transmisión: {tx_power} dBm")
            except:
                pass

            # Radio frequency
            try:
                frequency = base_station.frequency()
                print(f"   Frecuencia de radio: {frequency}")
            except:
                pass

        except Exception as e:
            print(f"   ⚠️  No se pudo obtener info de comunicación: {e}")

        print(f"\n[6] Resumen del diagnóstico")
        print(f"   {'='*50}")
        print(f"   Configuración del sensor {node_address}:")
        print(f"   - Frecuencia: {current_hz} Hz")
        print(f"   - Canales: {', '.join(channel_list) if channel_list else 'Ninguno'}")
        print(f"   - Formato: {format_str}")
        print(f"   - Duración: {'Ilimitada' if unlimited else 'Limitada'}")

        # Calcular throughput esperado
        if isinstance(current_hz, int):
            samples_per_sec = current_hz * len(channel_list)
            bytes_per_sec = samples_per_sec * 4  # Float32 = 4 bytes
            print(f"\n   Throughput esperado:")
            print(f"   - {samples_per_sec} samples/s")
            print(f"   - {bytes_per_sec} bytes/s ({bytes_per_sec/1024:.2f} KB/s)")

            # Verificar si excede límites de LXRS
            if samples_per_sec > 4000:
                print(f"   ⚠️  ADVERTENCIA: Excede límite de LXRS (4,000 samples/s)")
                print(f"   ➜  Requiere LXRS+ protocol")

        print(f"   {'='*50}\n")

        print(f"\n[7] Diagnóstico completo\n")

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
