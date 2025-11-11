# Cómo Configurar LXRS+ Manualmente en SensorConnect

## 🎯 Problema

El protocolo LXRS+ **no puede configurarse por código** en esta versión de MSCL. El método `communicationProtocol()` es **solo lectura** (getter), no permite cambiar el protocolo.

## ✅ Solución: Configurar Manualmente en SensorConnect

### Pasos para Habilitar LXRS+:

1. **Abrir SensorConnect**
   - Iniciar la aplicación SensorConnect

2. **Conectar al BaseStation**
   - Debería conectarse automáticamente a 192.168.8.101:5000

3. **Ir a Opciones del BaseStation**
   - Click en "Base Station 177076" (lado izquierdo)
   - Click en el ícono de opciones/configuración
   - O navegar a: **Base Station Options**

4. **Cambiar Protocolo a LXRS+**
   - Buscar sección: **Communication Protocol**
   - Seleccionar del dropdown: **LXRS+**
   - Click en **Apply** o **Save**

5. **Verificar el Cambio**
   - El protocolo debería mostrar "LXRS+" activo
   - Cerrar SensorConnect

6. **Ejecutar Nuestra App**
   - La configuración de LXRS+ persiste en el BaseStation
   - Nuestra app usará LXRS+ automáticamente

### Verificación:

Después de configurar LXRS+ en SensorConnect, ejecuta:

```bash
python check_lxrs_plus.py
```

Deberías ver:
```
✅ Protocolo actual: LXRS+
📊 Throughput máximo: 16,000 samples/s
```

## 📊 Diferencias LXRS vs LXRS+

| Protocolo | Throughput | 512 Hz | 1024 Hz |
|-----------|-----------|--------|---------|
| LXRS | 4,000 samples/s | ❌ 60% datos | ❌ 50% datos |
| LXRS+ | 16,000 samples/s | ✅ 95-100% | ✅ 95-100% |

## 🔍 Capturas de Pantalla (Referencias)

Basado en tus capturas de SensorConnect:

**Imagen 1**: Opciones del BaseStation
- Muestra el panel de configuración

**Imagen 5**: Dropdown de Protocolo
- Muestra las opciones: LXRS y LXRS+
- Seleccionar LXRS+

**Imagen 4**: Configuración de Modo
- "Transmit" debe estar seleccionado (no "Log")

## ⚠️ Notas Importantes

### 1. La Configuración Persiste
- Una vez configurado LXRS+ en SensorConnect, queda guardado en el BaseStation
- No necesitas configurarlo cada vez
- Nuestra app lo detectará y usará automáticamente

### 2. Verificación en Logs de la App

Al iniciar nuestra app, verás en los logs:

**Si LXRS+ está configurado:**
```
Checking communication protocol...
✅ LXRS+ is enabled! High frequencies (512-1024 Hz) should work correctly
Current BaseStation protocol: LXRS+ (16,000 samples/s)
```

**Si está en LXRS:**
```
Checking communication protocol...
⚠️  Protocol is LXRS - For high frequencies (>256 Hz), configure LXRS+ in SensorConnect
   LXRS limits:
   - 512 Hz:  Only ~60% of data will be received
   - 1024 Hz: Only ~50% of data will be received
   To fix: Open SensorConnect → BaseStation Options → Protocol → LXRS+
```

### 3. No Afecta Frecuencias Bajas

- A 128 Hz o menos, LXRS funciona perfectamente
- LXRS+ solo es necesario para 256 Hz o mayor
- Sin diferencia perceptible a frecuencias bajas

## 🚀 Flujo de Trabajo Recomendado

### Primera Vez (Configuración Única):
1. Abrir SensorConnect
2. Configurar LXRS+
3. Cerrar SensorConnect
4. Verificar con `python check_lxrs_plus.py`

### Uso Normal (Diario):
1. Iniciar nuestra app directamente
2. La app detecta LXRS+ automáticamente
3. Funciona a altas frecuencias sin problemas

## 🔧 Troubleshooting

### Problema: No Encuentro la Opción de Protocolo

**Causa**: Puede estar en diferente ubicación según versión de SensorConnect

**Solución**: Buscar en:
- BaseStation Options → Communication Protocol
- BaseStation Options → Advanced → Protocol
- Base Station → Settings → Protocol

### Problema: LXRS+ No Aparece en el Dropdown

**Causa 1**: Firmware desactualizado
- **Solución**: Actualizar firmware del BaseStation
- Contactar soporte MicroStrain para upgrade

**Causa 2**: Modelo no compatible
- **Solución**: Verificar que WSDA-2000 soporte LXRS+
- Según tus capturas, SÍ lo soporta

### Problema: Configuré LXRS+ pero la App Dice LXRS

**Causa**: Cambio no se aplicó correctamente

**Solución**:
1. Abrir SensorConnect nuevamente
2. Verificar que el protocolo sea LXRS+
3. Click en Apply/Save nuevamente
4. Desconectar y reconectar el BaseStation
5. Ejecutar `check_lxrs_plus.py` para verificar

## 📞 Soporte

Si después de configurar LXRS+ en SensorConnect, `check_lxrs_plus.py` sigue mostrando LXRS:

**Contactar MicroStrain Support:**
- Web: https://support.microstrain.com
- Email: support@microstrain.com
- Información a proporcionar:
  - Modelo: WSDA-2000
  - Serial: 6314-2000-177076
  - Problema: No puedo habilitar LXRS+
  - SensorConnect versión: [tu versión]

---

**Generado**: 2025-11-11
**Motivo**: communicationProtocol() es read-only en MSCL Python bindings
**Solución**: Configuración manual en SensorConnect (única vez)
