# Smart Expense Bot 🐱💅

[![CI](https://github.com/TU_USUARIO/smart_expense_bot/actions/workflows/ci.yml/badge.svg)](https://github.com/TU_USUARIO/smart_expense_bot/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Bot de Telegram para gestión de finanzas personales con IA. Operado por **Miss Toña**, una gata elegante que te ayuda a llevar tus gastos mientras te echa carrilla con cariño gatuno.

## Características

- 📝 Registro de gastos por texto natural
- 🎤 Entrada de gastos por notas de voz
- 📸 Extracción automática de datos desde fotos de recibos
- 💰 Validación de presupuestos mensuales
- 📊 Reportes automáticos por categoría
- 🧠 Procesamiento inteligente con OpenAI

## Stack Técnico

- **Backend:** FastAPI (Python 3.10+)
- **IA:** OpenAI (GPT-4o-mini, Whisper)
- **Base de Datos:** Supabase (PostgreSQL)
- **Reglas:** Google Sheets
- **Interfaz:** Telegram Bot API

## Instalación

1. Clona el repositorio
2. Instala las dependencias con Poetry:
   ```bash
   poetry install
   ```
3. Copia `.env.example` a `.env` y configura tus variables de entorno
4. Ejecuta la aplicación:
   ```bash
   poetry run uvicorn app.main:app --reload
   ```

## Desarrollo

Ver `STEPS.md` para el plan de implementación completo.

### Tests

```bash
# Ejecutar todos los tests
poetry run pytest

# Con cobertura
poetry run pytest --cov=app --cov-report=term-missing

# Solo tests de integración
poetry run pytest -m integration

# Solo tests de humo
poetry run pytest -m smoke
```

### Linting

```bash
# Verificar código
poetry run ruff check app/ tests/

# Formatear código
poetry run ruff format app/ tests/
```

## Licencia

Ver `LICENSE` para más información.

