"""Script para verificar qué datos se están guardando en InfluxDB."""
import sys
from influxdb_client import InfluxDBClient
from datetime import datetime, timedelta

def check_influxdb_data(sensor_id="10603", last_minutes=5):
    """
    Consulta InfluxDB para ver qué campos se están guardando.
    
    Args:
        sensor_id: ID del sensor a verificar
        last_minutes: Últimos N minutos de datos a consultar
    """
    # Configuración de InfluxDB (mismo que app.yaml)
    url = "http://localhost:8086"
    token = "3hQ1WFHJP8zJjegPoby8JbxsFEdwrUzEM0XuSdQ-4VogBxdWlPCnwUIkQAvqW0kT-8SVOSSQl2T1cmNA4o5Y9Q=="
    org = "imt"
    bucket = "python"
    
    try:
        # Conectar a InfluxDB
        client = InfluxDBClient(url=url, token=token, org=org)
        query_api = client.query_api()
        
        # Query para obtener los últimos datos del sensor
        query = f'''
        from(bucket: "{bucket}")
            |> range(start: -{last_minutes}m)
            |> filter(fn: (r) => r["_measurement"] == "sensor_data")
            |> filter(fn: (r) => r["sensor_id"] == "{sensor_id}")
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            |> limit(n: 10)
        '''
        
        print(f"\n{'='*80}")
        print(f"Verificando datos de InfluxDB para sensor {sensor_id}")
        print(f"Últimos {last_minutes} minutos")
        print(f"{'='*80}\n")
        
        tables = query_api.query(query, org=org)
        
        if not tables or len(tables) == 0:
            print(f"❌ No se encontraron datos para el sensor {sensor_id} en los últimos {last_minutes} minutos")
            print(f"   Prueba aumentando el rango de tiempo o verifica que el sensor esté transmitiendo.")
            return
        
        # Analizar los campos disponibles
        fields_found = set()
        data_count = 0
        
        for table in tables:
            for record in table.records:
                data_count += 1
                # El record tiene todos los campos como atributos
                record_dict = record.values
                
                # Mostrar primer registro como ejemplo
                if data_count == 1:
                    print("📊 Primer registro encontrado:")
                    print(f"   Timestamp: {record_dict.get('_time')}")
                    
                # Recolectar campos de aceleración
                for key in record_dict.keys():
                    if key.startswith('acceleration_'):
                        fields_found.add(key)
                        if data_count == 1:
                            print(f"   {key}: {record_dict.get(key)}")
        
        print(f"\n{'='*80}")
        print(f"📈 Resumen del análisis:")
        print(f"{'='*80}")
        print(f"   Total de registros analizados: {data_count}")
        print(f"   Campos de aceleración encontrados:")
        
        for field in sorted(fields_found):
            axis = field.replace('acceleration_', '').upper()
            print(f"      ✓ {field} (Eje {axis})")
        
        print(f"\n{'='*80}")
        if len(fields_found) == 1:
            axis_name = list(fields_found)[0].replace('acceleration_', '').upper()
            print(f"✅ CORRECTO: Solo se está guardando el eje {axis_name}")
        elif len(fields_found) == 2:
            axes_names = sorted([f.replace('acceleration_', '').upper() for f in fields_found])
            print(f"✅ CORRECTO: Se están guardando 2 ejes: {', '.join(axes_names)}")
        elif len(fields_found) == 3:
            print("✅ CORRECTO: Se están guardando los 3 ejes (X, Y, Z)")
            print("   (Configuración predeterminada cuando se seleccionan todos los ejes)")
        else:
            print(f"ℹ️  Se están guardando {len(fields_found)} ejes: {', '.join(sorted(fields_found))}")
        print(f"{'='*80}\n")
        
        # Cerrar conexión
        client.close()
        
    except Exception as e:
        print(f"❌ Error al consultar InfluxDB: {e}")
        print(f"   Verifica que InfluxDB esté corriendo en {url}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Verificar datos guardados en InfluxDB")
    parser.add_argument("--sensor-id", default="10603", help="ID del sensor (default: 10603)")
    parser.add_argument("--minutes", type=int, default=5, help="Últimos N minutos a consultar (default: 5)")
    
    args = parser.parse_args()
    
    check_influxdb_data(sensor_id=args.sensor_id, last_minutes=args.minutes)
