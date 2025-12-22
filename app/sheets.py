"""Cliente de Google Sheets para leer presupuestos.

Este módulo se encarga de:
- Conectarse a Google Sheets usando credenciales de servicio.
- Leer la hoja de presupuestos.
- Exponer funciones simples para el agente / lógica de negocio:
  - obtener_categorias()
  - obtener_presupuesto(categoria)
"""

from functools import lru_cache
from typing import List, Optional

import gspread
from google.oauth2.service_account import Credentials

from app.config import get_settings


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]


@lru_cache()
def get_gspread_client() -> gspread.Client:
    """Crea y devuelve un cliente de gspread autenticado.

    Usa las credenciales configuradas en Settings.
    """
    settings = get_settings()

    credentials = Credentials.from_service_account_file(
        settings.google_sheets_credentials_path,
        scopes=SCOPES,
    )
    return gspread.authorize(credentials)


@lru_cache()
def _get_worksheet():
    """Obtiene la worksheet de presupuestos configurada.

    Se separa en una función interna para facilitar el mocking en tests.
    """
    settings = get_settings()
    client = get_gspread_client()

    spreadsheet = client.open_by_key(settings.google_sheets_spreadsheet_id)
    worksheet = spreadsheet.worksheet(settings.google_sheets_worksheet_name)
    return worksheet


def obtener_categorias() -> List[str]:
    """Devuelve la lista de categorías definidas en la hoja de presupuestos.

    Se asume un formato simple:
    - Columna A: "Categoría" (encabezado en la primera fila)
    - Filas siguientes: nombres de categorías (texto).
    """
    worksheet = _get_worksheet()

    # get_all_values devuelve una lista de filas (listas de celdas).
    values = worksheet.get_all_values()
    if not values:
        return []

    # Ignorar la fila de encabezado (primera fila)
    data_rows = values[1:]

    categorias: List[str] = []
    for row in data_rows:
        if not row:
            continue
        categoria = row[0].strip() if row[0] is not None else ""
        if categoria:
            categorias.append(categoria)

    return categorias


def obtener_presupuesto(categoria: str) -> Optional[float]:
    """Obtiene el límite de presupuesto para una categoría.

    - Busca la categoría (case-insensitive) en la hoja.
    - Si la encuentra, intenta convertir el límite a float y lo devuelve.
    - Si no la encuentra o el valor no es numérico, devuelve None.

    Estructura esperada de la hoja:
    - Primera fila: encabezados, por ejemplo: ["Categoria", "Limite"]
    - Filas siguientes: datos.
    """
    if not categoria:
        raise ValueError("La categoría no puede estar vacía")

    worksheet = _get_worksheet()

    # get_all_records devuelve una lista de dicts usando la primera fila como encabezados.
    registros = worksheet.get_all_records()

    # Normalizamos la categoría de entrada para comparación case-insensitive.
    categoria_normalizada = categoria.strip().lower()

    for registro in registros:
        # Intentar leer claves comunes, tolerando variaciones menores.
        # Por ejemplo: "Categoria", "Categoría", "category".
        claves_categoria_posibles = ["Categoria", "Categoría", "category", "Category"]
        claves_limite_posibles = ["Limite", "Límite", "limit", "Limit"]

        valor_categoria = None
        for clave in claves_categoria_posibles:
            if clave in registro and registro[clave]:
                valor_categoria = str(registro[clave]).strip()
                break

        if not valor_categoria:
            continue

        if valor_categoria.strip().lower() != categoria_normalizada:
            continue

        valor_limite = None
        for clave in claves_limite_posibles:
            if clave in registro and registro[clave] not in (None, ""):
                valor_limite = registro[clave]
                break

        if valor_limite is None:
            return None

        # Intentar convertir el límite a float.
        try:
            # get_all_records ya suele devolver numéricos como int/float.
            return float(valor_limite)
        except (TypeError, ValueError):
            return None

    # Si no se encontró la categoría
    return None


