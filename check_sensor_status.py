#!/usr/bin/env python
"""Script para verificar el estado del sensor y forzar inicio de streaming."""
import requests
import time

API_BASE = "http://localhost:8050"

def check_status():
    """Verifica el estado actual del sistema."""
    print("=" * 60)
    print("VERIFICACIÓN DE ESTADO DEL SISTEMA")
    print("=" * 60)
    
    # No hay API REST directa en este sistema, pero podemos verificar
    # leyendo los logs más recientes
    import os
    log_path = "data/logs/mscl_tension.log.1"
    
    if not os.path.exists(log_path):
        print(f"❌ No se encuentra el archivo de log: {log_path}")
        return
    
    print(f"\n📄 Leyendo últimos 50 mensajes del log...\n")
    
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        recent = lines[-50:] if len(lines) > 50 else lines
        
        # Buscar mensajes clave
        gateway_connected = False
        sensor_connected = False
        streaming_active = False
        last_sweep = None
        last_update = None
        
        for line in recent:
            if "Gateway MSCL connected" in line or "Connected to gateway" in line:
                gateway_connected = True
                print(f"✅ Gateway: {line.strip()}")
            
            if "Sensor 10603" in line and "connected" in line.lower():
                sensor_connected = True
                print(f"✅ Sensor: {line.strip()}")
            
            if "streaming" in line.lower() and "started" in line.lower():
                streaming_active = True
                print(f"✅ Streaming: {line.strip()}")
            
            if "Received sweep" in line:
                last_sweep = line.strip()
            
            if "Updating realtime_store" in line:
                last_update = line.strip()
        
        print("\n" + "=" * 60)
        print("RESUMEN:")
        print("=" * 60)
        print(f"Gateway conectado: {'✅ SÍ' if gateway_connected else '❌ NO'}")
        print(f"Sensor 10603 conectado: {'✅ SÍ' if sensor_connected else '❌ NO'}")
        print(f"Streaming activo: {'✅ SÍ' if streaming_active else '❌ NO'}")
        
        if last_sweep:
            print(f"\n📊 Último sweep recibido:")
            print(f"   {last_sweep}")
        else:
            print("\n⚠️  NO se han recibido sweeps recientemente")
        
        if last_update:
            print(f"\n🔄 Última actualización de datos:")
            print(f"   {last_update}")
        else:
            print("\n⚠️  NO se ha actualizado realtime_store recientemente")
        
        print("\n" + "=" * 60)
        print("DIAGNÓSTICO:")
        print("=" * 60)
        
        if not gateway_connected:
            print("❌ PROBLEMA: Gateway no está conectado")
            print("   → Solución: Ir a la interfaz web y conectar el gateway")
        elif not sensor_connected:
            print("❌ PROBLEMA: Sensor 10603 no está conectado")
            print("   → Solución: Verificar conexión física del sensor")
        elif not streaming_active:
            print("⚠️  ADVERTENCIA: Streaming no está activo")
            print("   → Solución: Ir a 'Control de Sensores' e iniciar el streaming")
        elif not last_sweep:
            print("⚠️  ADVERTENCIA: No se están recibiendo datos del sensor")
            print("   → Solución: Verificar que el sensor esté enviando datos")
            print("   → El sensor puede estar en modo sleep o suspendido")
        else:
            print("✅ Sistema funcionando correctamente")
            print("   Los datos deberían estar apareciendo en la interfaz")
            print("   Verifica que estés en la pestaña 'Aceleración en Tiempo Real'")

if __name__ == "__main__":
    check_status()
