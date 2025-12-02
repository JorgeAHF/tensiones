"""Quick protocol check without emoji issues."""
import sys
sys.path.insert(0, '.')

try:
    import mscl

    # Connect
    connection = mscl.Connection.TcpIp("192.168.8.101", 5000)
    base_station = mscl.BaseStation(connection)

    # Check protocol
    current_protocol = base_station.communicationProtocol()

    if current_protocol == 0:
        print("Protocolo actual: LXRS (4,000 samples/s)")
        print("Estado: NO OPTIMO para frecuencias altas")
    elif current_protocol == 1:
        print("Protocolo actual: LXRS+ (16,000 samples/s)")
        print("Estado: OPTIMO - Listo para 512-1024 Hz")
    else:
        print(f"Protocolo desconocido: {current_protocol}")

    print(f"\nValor numerico: {current_protocol}")
    print("0 = LXRS, 1 = LXRS+")

except Exception as e:
    print(f"Error: {e}")
