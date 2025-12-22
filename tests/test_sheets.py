"""Tests unitarios para el módulo de Google Sheets (app.sheets)."""

from unittest.mock import MagicMock, patch

import pytest

from app import sheets


class TestObtenerCategorias:
    """Tests para la función obtener_categorias."""

    @patch("app.sheets._get_worksheet")
    def test_obtener_categorias_devuelve_lista(self, mock_get_worksheet):
        """Debe devolver una lista de categorías leyendo la primera columna."""
        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = [
            ["Categoria", "Limite"],
            ["Comida", "500000"],
            ["Transporte", "300000"],
            ["Ocio", "200000"],
        ]
        mock_get_worksheet.return_value = mock_ws

        categorias = sheets.obtener_categorias()

        assert categorias == ["Comida", "Transporte", "Ocio"]
        mock_ws.get_all_values.assert_called_once()

    @patch("app.sheets._get_worksheet")
    def test_obtener_categorias_hoja_vacia(self, mock_get_worksheet):
        """Si la hoja está vacía, debe devolver lista vacía."""
        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = []
        mock_get_worksheet.return_value = mock_ws

        categorias = sheets.obtener_categorias()

        assert categorias == []


class TestObtenerPresupuesto:
    """Tests para la función obtener_presupuesto."""

    @patch("app.sheets._get_worksheet")
    def test_obtener_presupuesto_encontrado(self, mock_get_worksheet):
        """Debe devolver el límite numérico cuando la categoría existe."""
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = [
            {"Categoria": "Comida", "Limite": 500000},
            {"Categoria": "Transporte", "Limite": 300000},
        ]
        mock_get_worksheet.return_value = mock_ws

        limite = sheets.obtener_presupuesto("Comida")

        assert limite == 500000.0
        mock_ws.get_all_records.assert_called_once()

    @patch("app.sheets._get_worksheet")
    def test_obtener_presupuesto_case_insensitive(self, mock_get_worksheet):
        """La búsqueda de categoría debe ser case-insensitive."""
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = [
            {"Categoria": "comida", "Limite": "450000"},
        ]
        mock_get_worksheet.return_value = mock_ws

        limite = sheets.obtener_presupuesto("CoMiDa")

        assert limite == 450000.0

    @patch("app.sheets._get_worksheet")
    def test_obtener_presupuesto_no_encontrado(self, mock_get_worksheet):
        """Si la categoría no existe, debe devolver None."""
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = [
            {"Categoria": "Comida", "Limite": 500000},
        ]
        mock_get_worksheet.return_value = mock_ws

        limite = sheets.obtener_presupuesto("Ocio")

        assert limite is None

    @patch("app.sheets._get_worksheet")
    def test_obtener_presupuesto_valor_no_numerico(self, mock_get_worksheet):
        """Si el valor de límite no es numérico, debe devolver None."""
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = [
            {"Categoria": "Comida", "Limite": "no-es-numero"},
        ]
        mock_get_worksheet.return_value = mock_ws

        limite = sheets.obtener_presupuesto("Comida")

        assert limite is None

    def test_obtener_presupuesto_categoria_vacia(self):
        """Si la categoría es vacía, debe lanzar ValueError."""
        with pytest.raises(ValueError, match="La categoría no puede estar vacía"):
            sheets.obtener_presupuesto("")
