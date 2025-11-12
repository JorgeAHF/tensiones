"""
Script de prueba para modo datalogging.

Este script prueba la funcionalidad de datalogging donde:
- Los datos se guardan en la memoria del sensor (no se transmiten wireless)
- Al detener el monitoreo, los datos se descargan y procesan en CSVs de 2 minutos
- No hay visualización en tiempo real
"""
import sys
sys.path.insert(0, '.')

import time
import mscl
from app.acquisition.real_mscl_client import RealMSCLClient
from app.acquisition.mscl_client import Sample
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOGGER = logging.getLogger(__name__)


def test_datalogging():
    """Test datalogging mode with real sensor."""
    print("=" * 80)
    print("PRUEBA DE MODO DATALOGGING")
    print("=" * 80)
    print()
    print("En este modo:")
    print("- Los datos se guardan en la memoria interna del sensor")
    print("- NO hay transmisión wireless durante el monitoreo")
    print("- Al detener, los datos se descargan automáticamente")
    print("- Se generan CSVs de 2 minutos en data/acceleration/")
    print()
    print("=" * 80)

    try:
        # Connect to BaseStation
        print("\n1. Conectando al BaseStation...")
        connection = mscl.Connection.TcpIp("192.168.8.101", 5000)
        base_station = mscl.BaseStation(connection)
        print("   ✓ Conectado exitosamente")

        # Create RealMSCLClient with datalogging enabled
        print("\n2. Creando cliente MSCL con DATALOGGING habilitado...")
        sensor_configs = [{"id": "10603", "name": "Sensor-10603"}]

        client = RealMSCLClient(
            base_station=base_station,
            sensor_configs=sensor_configs,
            default_fs=1024.0,  # Test at 1024 Hz
            use_datalogging=True  # ENABLE DATALOGGING MODE
        )
        print("   ✓ Cliente creado")

        # List available sensors
        sensors = client.list_nodes()
        if not sensors:
            print("\n❌ No se encontraron sensores")
            return

        sensor = sensors[0]
        sensor_id = sensor.sensor_id
        print(f"\n3. Sensor encontrado: {sensor_id}")

        # Configure sensor for datalogging at 1024 Hz
        print(f"\n4. Configurando sensor {sensor_id} para datalogging a 1024 Hz...")
        client.configure_node(
            sensor_id=sensor_id,
            sample_rate_hz=1024.0,
            axes=['x', 'y', 'z'],
            data_format='float',
            sampling_mode='continuous'
        )
        print("   ✓ Sensor configurado")

        # Dummy callback (won't be called in datalogging mode)
        def dummy_callback(sample: Sample):
            pass

        # Start "streaming" (actually starts datalogging)
        print(f"\n5. Iniciando DATALOGGING en sensor {sensor_id}...")
        print("   (Los datos se están guardando en la memoria del sensor)")
        client.start_streaming(sensor_id, dummy_callback)
        print("   ✓ Datalogging iniciado")

        # Wait for user input
        print("\n" + "=" * 80)
        print("DATALOGGING ACTIVO")
        print("=" * 80)
        print()
        print("El sensor está guardando datos en su memoria interna a 1024 Hz.")
        print("NO verás datos en tiempo real - es normal.")
        print()
        print("Presiona ENTER cuando quieras detener y descargar los datos...")
        input()

        # Stop streaming (will trigger download)
        print("\n6. Deteniendo datalogging y descargando datos...")
        print("   (Esto puede tomar varios minutos dependiendo de cuántos datos hay)")
        client.stop_streaming(sensor_id)
        print("   ✓ Descarga completada")

        print("\n" + "=" * 80)
        print("PRUEBA COMPLETADA")
        print("=" * 80)
        print()
        print("Los archivos CSV se generaron en: data/acceleration/")
        print("Cada archivo contiene 2 minutos de datos.")
        print()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_datalogging()
