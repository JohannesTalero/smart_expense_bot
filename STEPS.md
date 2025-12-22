# 🚀 Plan de Implementación - Smart Expense Bot v0

Cada paso es un checkpoint. Después de completar cada uno, probamos y seguimos.

---

## Paso 1: Setup del Proyecto ⚙️
**Objetivo:** Tener la estructura base lista para desarrollar.

- [X] Crear estructura de carpetas (`app/`, `tests/`)
- [X] Inicializar proyecto con Poetry (`pyproject.toml`)
- [X] Crear `.gitignore` (Python + env)
- [X] Crear `.env.example` con las variables necesarias
- [X] Crear `app/config.py` para cargar configuración

**Prueba:** `poetry install` funciona sin errores.

---

## Paso 2: FastAPI + Webhook Básico 🌐
**Objetivo:** Bot que responde "pong" a cualquier mensaje.

- [X] Crear `app/main.py` con FastAPI
- [X] Endpoint `/health` para verificar que está vivo
- [X] Endpoint `/webhook` que recibe updates de Telegram
- [X] Responder con un mensaje simple de confirmación

**Prueba:** Enviar mensaje al bot → Recibe "Mensaje recibido ✓"

---

## Paso 3: Conexión a Supabase 🗄️
**Objetivo:** Poder guardar y leer gastos de la base de datos.

- [X] Crear `app/database.py` con cliente Supabase
- [X] Función `insertar_gasto(data)`
- [X] Función `obtener_gastos(user, periodo?)`
- [X] Función `actualizar_gasto(id, data)`
- [X] Función `eliminar_gasto(id)`
- [X] Tests unitarios para database
- [X] Crear `supabase_schema.sql` con el schema de la tabla

**Prueba:** Test pasa → Puedo insertar y leer un gasto desde código.

**Nota:** Ejecuta el SQL en `supabase_schema.sql` en el SQL Editor de Supabase para crear la tabla antes de usar las funciones.

---

## Paso 4: Conexión a Google Sheets 📊
**Objetivo:** Leer presupuestos desde la hoja de cálculo.

- [X] Crear `app/sheets.py` con cliente gspread
- [X] Función `obtener_presupuesto(categoria)`
- [X] Función `obtener_categorias()` (lista todas)
- [X] Tests unitarios para sheets

**Prueba:** Test pasa → Puedo leer el límite de "Comida" desde Sheets.

---

## Paso 5: Agente LLM con Tools 🧠
**Objetivo:** El cerebro que entiende mensajes y ejecuta acciones.

- [X] Crear `app/agent.py`
- [X] Definir tools con LangChain:
  - `registrar_gasto`
  - `editar_gasto`
  - `eliminar_gasto`
  - `listar_gastos`
  - `verificar_presupuesto`
  - `generar_reporte`
- [X] System prompt con personalidad del bot (Miss Toña)
- [X] Función principal `procesar_mensaje(texto, user)`
- [X] Tests para el agente (con mocks de LangChain)

**Prueba:** "Gasté 20 mil en almuerzo" → Llama a `registrar_gasto` correctamente.

---

## Paso 6: Procesamiento de Audio 🎤
**Objetivo:** Convertir notas de voz a texto.

- [X] Crear `app/media.py`
- [X] Función `transcribir_audio(audio_bytes)` con Whisper
- [X] Función `transcribir_audio_telegram(file_id)` - flujo completo
- [X] Integrar en el webhook (detectar tipo de mensaje)
- [X] Tests para media

**Prueba:** Enviar audio "gasté cincuenta mil en taxi" → Se registra el gasto.

---

## Paso 7: Procesamiento de Imágenes 📸
**Objetivo:** Extraer datos de fotos de recibos.

- [X] Función `extraer_recibo(image_bytes)` en `media.py`
- [X] Usar GPT-4o-mini con visión
- [X] Validar JSON de respuesta
- [X] Integrar en el webhook
- [X] Tests para funciones de imagen

**Prueba:** Enviar foto de recibo → Extrae monto y establece categoría.

---

## Paso 8: Integración Completa 🔗
**Objetivo:** Todo conectado y funcionando end-to-end.

- [X] Webhook procesa texto, audio e imágenes
- [X] Agente ejecuta tools reales (no mocks)
- [X] Respuestas con personalidad de "Miss Toña"
- [X] Manejo de errores amigable
- [X] Siempre preguntar por método de pago
- [X] Usar nombre de Telegram en lugar de user_id

**Prueba:** Flujo completo texto → DB → Sheets → Respuesta bonita.

---

## Paso 9: CI/CD con GitHub Actions 🔄
**Objetivo:** Tests automáticos en cada push.

- [X] Crear `.github/workflows/ci.yml`
- [X] Ejecutar pytest en cada PR con cobertura
- [X] Linting con ruff
- [X] Security check con bandit
- [X] Badge de status en README

**Prueba:** Hacer push → GitHub Actions corre tests → ✅ Verde.

---

## Paso 10: Deploy 🚀
**Objetivo:** Bot en producción accesible 24/7.

- [ ] Configurar Railway/Render
- [ ] Variables de entorno en producción
- [ ] Configurar webhook de Telegram apuntando al servidor
- [ ] Probar con usuarios reales

**Prueba:** Bot responde desde el servidor en la nube.

---

## Notas

- **Después de cada paso:** Probamos juntos antes de continuar.
- **Si algo falla:** Lo arreglamos antes de seguir.
- **Commits frecuentes:** Un commit por paso completado.

---

## Progreso

| Paso | Estado | Fecha |
|------|--------|-------|
| 1. Setup | ✅ Completado | - |
| 2. Webhook | ✅ Completado | - |
| 3. Supabase | ✅ Completado | - |
| 4. Sheets | ✅ Completado | - |
| 5. Agente | ✅ Completado | - |
| 6. Audio | ✅ Completado | - |
| 7. Imágenes | ✅ Completado | - |
| 8. Integración | ✅ Completado | - |
| 9. CI/CD | ✅ Completado | - |
| 10. Deploy | ⏳ Pendiente | - |

