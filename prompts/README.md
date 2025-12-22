# Prompts del Bot

Esta carpeta contiene todos los prompts del sistema en formato Markdown para facilitar su edición y mantenimiento.

## Estructura

- `system_prompt.md` - Prompt principal del sistema con la personalidad de Miss Toña 🐱💅

## Cómo funciona

Los prompts se cargan automáticamente desde estos archivos cuando se inicializa el agente. Los cambios en los archivos `.md` se reflejarán después de reiniciar la aplicación.

### Formato

Los archivos Markdown pueden incluir:
- Títulos con `#` (se ignoran automáticamente)
- Listas con `-` o `*`
- Texto formateado con Markdown
- Emojis y caracteres especiales

El contenido se carga tal cual, removiendo solo el primer encabezado si existe (para permitir títulos de documento).

## Agregar nuevos prompts

1. Crea un nuevo archivo `.md` en esta carpeta
2. Agrega una función en `app/agent.py` similar a `obtener_system_prompt()`:
   ```python
   def obtener_mi_nuevo_prompt() -> str:
       return _cargar_prompt("mi_nuevo_prompt.md")
   ```
3. Usa la función donde necesites el prompt

## Notas

- Los prompts se cachean en memoria (`@lru_cache`) para mejorar el rendimiento
- Los archivos se leen con encoding UTF-8
- Si un archivo no existe, se lanzará un `FileNotFoundError` al intentar cargarlo



