# Configuración de Redis para Memoria Conversacional

Este documento explica cómo configurar Redis para habilitar la memoria conversacional en el Smart Expense Bot.

## ¿Por qué Redis?

Redis permite que el bot recuerde el contexto de la conversación durante el día. Sin Redis, cada mensaje se procesa de forma independiente, lo que hace que el bot no pueda recordar conversaciones previas.

## Usando Upstash (Recomendado)

Upstash es un servicio de Redis serverless en la nube, perfecto para producción. Ofrece un tier gratuito generoso y escalado automático.

### Paso 1: Crear cuenta en Upstash

1. Ve a https://upstash.com/
2. Crea una cuenta (puedes usar GitHub, Google, etc.)
3. Una vez dentro del dashboard, crea un nuevo Redis database

### Paso 2: Crear Base de Datos Redis

1. En el dashboard de Upstash, haz clic en "Create Database"
2. Elige la región más cercana a tu servidor (ej: `us-east-1`)
3. Selecciona el plan (el tier gratuito es suficiente para empezar)
4. Dale un nombre a tu base de datos (ej: `smart-expense-bot`)
5. Haz clic en "Create"

### Paso 3: Obtener la URL de Conexión

1. Una vez creada la base de datos, ve a la página de detalles
2. En la sección "Redis CLI" o "Connect", encontrarás la URL de conexión
3. La URL se ve así:
   ```
   redis://default:TU_PASSWORD@TU_ENDPOINT:6379
   ```
   O con SSL (rediss://):
   ```
   rediss://default:TU_PASSWORD@TU_ENDPOINT:6379
   ```

4. **Importante**: 
   - Copia la URL completa que incluye la contraseña
   - Si la URL usa `rediss://` (con doble 's'), significa que usa SSL/TLS
   - El código del bot soporta ambos formatos automáticamente

### Paso 4: Configurar en el Bot

Agrega la URL de Upstash a tu archivo `.env`:

```env
# Redis con Upstash
REDIS_ENABLED=true
REDIS_URL=redis://default:TU_PASSWORD@TU_ENDPOINT:6379
```

**Ejemplo real:**
```env
REDIS_ENABLED=true
REDIS_URL=redis://default:AXr3abc123xyz@usw1-xyz-12345.upstash.io:6379
```

### Paso 5: Verificar Conexión

Después de reiniciar el bot, deberías ver en los logs:
```
INFO - Cliente de Redis inicializado correctamente
```

Si ves un error, verifica:
- Que la URL esté completa (incluye password)
- Que no haya espacios extra en la URL
- Que la base de datos esté activa en Upstash

## Alternativas (Opcional)

### Redis Local (Solo para Desarrollo)

Si prefieres usar Redis local para desarrollo:

#### Windows
1. Descarga Redis desde: https://github.com/microsoftarchive/redis/releases
2. O usa WSL2 y sigue las instrucciones de Linux
3. O usa Docker:
   ```bash
   docker run -d -p 6379:6379 redis:latest
   ```

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

#### macOS
```bash
brew install redis
brew services start redis
```

Luego en `.env`:
```env
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379
```

### Otros Servicios en la Nube

- **Redis Cloud**: https://redis.com/try-free/
- **AWS ElastiCache**: Para producción en AWS

## Instalación de Dependencias

### 1. Instalar dependencias de Redis

```bash
poetry install --extras redis
```

O si ya tienes Redis instalado:
```bash
poetry add redis
```

### 2. Configurar variables de entorno

Agrega estas variables a tu archivo `.env`:

**Para Upstash:**
```env
# Redis con Upstash
REDIS_ENABLED=true
REDIS_URL=redis://default:TU_PASSWORD@TU_ENDPOINT:6379
```

**Para Redis local (desarrollo):**
```env
# Redis local
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379
```

### 3. Verificar que Redis funciona

El bot intentará conectarse a Redis al iniciar. Si Redis no está disponible:
- El bot seguirá funcionando pero sin memoria conversacional
- Verás un warning en los logs
- Los mensajes se procesarán sin contexto previo

**Verificar conexión a Upstash:**
1. Ve al dashboard de Upstash
2. En la sección "Metrics" deberías ver actividad cuando el bot se conecta
3. En los logs del bot deberías ver: `INFO - Cliente de Redis inicializado correctamente`

## Funcionamiento

### Almacenamiento
- Cada conversación se almacena con la clave: `conversation:{user_id}:{fecha}`
- Ejemplo: `conversation:1909715176:2024-12-22`
- Las conversaciones se eliminan automáticamente después de 25 horas

### Contexto
- El bot recuerda hasta 20 mensajes recientes por usuario
- Solo mantiene conversaciones del mismo día
- Al día siguiente, comienza con contexto limpio

### Ejemplo de uso

**Sin Redis:**
```
Usuario: "compre una pizza de 50mil"
Bot: "¿Quieres que registre el gasto de $50,000 en Pizza?"
Usuario: "si dale asi"
Bot: "¿Qué quieres hacer?" (no recuerda la conversación anterior)
```

**Con Redis:**
```
Usuario: "compre una pizza de 50mil"
Bot: "¿Quieres que registre el gasto de $50,000 en Pizza?"
Usuario: "si dale asi"
Bot: "¡Perfecto! Gasto registrado..." (recuerda el contexto)
```

## Solución de Problemas

### Error: "Redis no está instalado"
```bash
poetry install --extras redis
```

### Error: "Error conectando a Redis"

**Para Upstash:**
1. Verifica que la URL esté completa y correcta en `.env`
2. Asegúrate de que la URL incluya el password (formato: `redis://default:PASSWORD@ENDPOINT:6379`)
3. Verifica en el dashboard de Upstash que la base de datos esté activa
4. Revisa que no haya límites de rate limit alcanzados (en el tier gratuito hay límites)

**Para Redis local:**
1. Verifica que Redis esté corriendo:
   ```bash
   redis-cli ping
   # Debe responder: PONG
   ```

2. Verifica la URL en `.env`:
   ```env
   REDIS_URL=redis://localhost:6379
   ```

### El bot no recuerda conversaciones
1. Verifica que `REDIS_ENABLED=true` en `.env`
2. Revisa los logs para ver si hay errores de conexión
3. Verifica que Redis esté funcionando: `redis-cli ping`

## Deshabilitar Redis

Si no quieres usar Redis, simplemente configura:

```env
REDIS_ENABLED=false
```

El bot funcionará normalmente, pero sin memoria conversacional.

