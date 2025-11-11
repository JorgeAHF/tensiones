"""
Script para verificar si LXRS+ está disponible y habilitado en el BaseStation.
Ejecutar antes y después de iniciar el monitoreo para confirmar el protocolo.
"""
import sys
sys.path.insert(0, '.')

try:
    import mscl
except ImportError:
    print("❌ Error: MSCL no está instalado")
    print("   Instalar desde: https://github.com/LORD-MicroStrain/MSCL")
    sys.exit(1)


def check_lxrs_plus():
    """Verifica el protocolo configurado en el BaseStation."""
    print("="*80)
    print("VERIFICACIÓN DE PROTOCOLO LXRS/LXRS+")
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
        print("\n2. Verificando protocolo actual...")
        current_protocol = base_station.communicationProtocol()

        # Mapear el enum a nombre legible
        if current_protocol == mscl.WirelessTypes.commProtocol_lxrs:
            protocol_name = "LXRS"
            max_throughput = "4,000 samples/s"
            color = "⚠️"
        elif current_protocol == mscl.WirelessTypes.commProtocol_lxrsPlus:
            protocol_name = "LXRS+"
            max_throughput = "16,000 samples/s"
            color = "✅"
        else:
            protocol_name = f"Unknown ({current_protocol})"
            max_throughput = "Unknown"
            color = "❓"

        print(f"   {color} Protocolo actual: {protocol_name}")
        print(f"   📊 Throughput máximo: {max_throughput}")

    except AttributeError:
        print("   ❌ El método communicationProtocol() no está disponible en esta versión de MSCL")
        return
    except Exception as e:
        print(f"   ❌ Error al verificar protocolo: {e}")
        return

    # Intentar cambiar a LXRS+ si no está activo
    if current_protocol != mscl.WirelessTypes.commProtocol_lxrsPlus:
        print("\n3. Intentando habilitar LXRS+...")
        try:
            base_station.communicationProtocol(mscl.WirelessTypes.commProtocol_lxrsPlus)

            # Verificar el cambio
            new_protocol = base_station.communicationProtocol()
            if new_protocol == mscl.WirelessTypes.commProtocol_lxrsPlus:
                print("   ✅ LXRS+ habilitado exitosamente!")
                print("   📊 Nuevo throughput máximo: 16,000 samples/s")
            else:
                print("   ⚠️  El cambio no se aplicó correctamente")

        except AttributeError:
            print("   ❌ LXRS+ no disponible en esta versión de MSCL")
        except Exception as e:
            print(f"   ❌ Error al habilitar LXRS+: {e}")
            print("\n   Posibles causas:")
            print("   - BaseStation no soporta LXRS+")
            print("   - Firmware desactualizado")
            print("   - Sensores no compatibles con LXRS+")
    else:
        print("\n3. ✅ LXRS+ ya está habilitado")

    # Información del BaseStation
    print("\n4. Información del BaseStation:")
    try:
        print(f"   Modelo: {base_station.model()}")
        print(f"   Serial: {base_station.serial()}")
        try:
            print(f"   Firmware: {base_station.firmwareVersion().str()}")
        except:
            pass

        try:
            frequency = base_station.frequency()
            freq_mhz = frequency.freqKhz() / 1000
            print(f"   Frecuencia RF: {freq_mhz} MHz")
        except:
            pass
    except Exception as e:
        print(f"   ⚠️  No se pudo obtener información completa: {e}")

    # Recomendaciones
    print("\n" + "="*80)
    print("RECOMENDACIONES:")
    print("="*80)

    if current_protocol == mscl.WirelessTypes.commProtocol_lxrsPlus:
        print("✅ Tu BaseStation está configurado con LXRS+")
        print("   Deberías poder muestrear a:")
        print("   - 512 Hz: ~3% del bandwidth (muy seguro)")
        print("   - 1024 Hz: ~6% del bandwidth (seguro)")
        print("   - 2048 Hz: ~13% del bandwidth (factible)")
    else:
        print("⚠️  Tu BaseStation está usando LXRS (no LXRS+)")
        print("   Límites prácticos:")
        print("   - 128 Hz: ✅ Perfecto")
        print("   - 256 Hz: ✅ Bien")
        print("   - 512 Hz: ⚠️  Solo ~60% de datos")
        print("   - 1024 Hz: ❌ Solo ~50% de datos")
        print("\n   Para habilitar LXRS+:")
        print("   1. Verificar que el firmware del BaseStation sea compatible")
        print("   2. Verificar que los sensores soporten LXRS+")
        print("   3. Actualizar firmware si es necesario")

    print("="*80)


if __name__ == "__main__":
    check_lxrs_plus()
