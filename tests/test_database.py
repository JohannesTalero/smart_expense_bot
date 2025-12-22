"""Tests unitarios para el módulo de base de datos."""

from datetime import datetime
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from app import database


class TestInsertarGasto:
    """Tests para la función insertar_gasto."""

    @patch("app.database.get_supabase_client")
    def test_insertar_gasto_exitoso(self, mock_get_client):
        """Test que inserta un gasto correctamente."""
        # Mock del cliente y respuesta
        mock_client = Mock()
        mock_table = Mock()
        mock_insert = Mock()
        mock_execute = Mock()

        gasto_insertado = {
            "id": str(uuid4()),
            "user": "test_user",
            "monto": 25000.0,
            "item": "Pizza",
            "categoria": "Comida",
            "metodo": "Tarjeta",
            "created_at": datetime.utcnow().isoformat(),
        }

        mock_execute.return_value = Mock(data=[gasto_insertado])
        mock_insert.execute = mock_execute
        mock_table.insert.return_value = mock_insert
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        # Ejecutar función
        resultado = database.insertar_gasto(
            user="test_user",
            monto=25000.0,
            item="Pizza",
            categoria="Comida",
            metodo="Tarjeta",
        )

        # Verificaciones
        assert resultado == gasto_insertado
        mock_table.insert.assert_called_once()
        mock_execute.assert_called_once()

    @patch("app.database.get_supabase_client")
    def test_insertar_gasto_con_campos_opcionales(self, mock_get_client):
        """Test que inserta un gasto con todos los campos opcionales."""
        mock_client = Mock()
        mock_table = Mock()
        mock_insert = Mock()
        mock_execute = Mock()

        gasto_insertado = {
            "id": str(uuid4()),
            "user": "test_user",
            "monto": 50000.0,
            "item": "Taxi",
            "categoria": "Transporte",
            "metodo": "Efectivo",
            "raw_input": "gasté 50 mil en taxi",
            "notas": "Viaje al aeropuerto",
            "created_at": datetime.utcnow().isoformat(),
        }

        mock_execute.return_value = Mock(data=[gasto_insertado])
        mock_insert.execute = mock_execute
        mock_table.insert.return_value = mock_insert
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.insertar_gasto(
            user="test_user",
            monto=50000.0,
            item="Taxi",
            categoria="Transporte",
            metodo="Efectivo",
            raw_input="gasté 50 mil en taxi",
            notas="Viaje al aeropuerto",
        )

        assert resultado == gasto_insertado

    def test_insertar_gasto_monto_invalido(self):
        """Test que valida que el monto sea mayor a 0."""
        with pytest.raises(ValueError, match="El monto debe ser mayor a 0"):
            database.insertar_gasto(
                user="test_user",
                monto=0,
                item="Test",
                categoria="Test",
            )

        with pytest.raises(ValueError, match="El monto debe ser mayor a 0"):
            database.insertar_gasto(
                user="test_user",
                monto=-100,
                item="Test",
                categoria="Test",
            )


class TestObtenerGastos:
    """Tests para la función obtener_gastos."""

    @patch("app.database.get_supabase_client")
    def test_obtener_gastos_sin_filtros(self, mock_get_client):
        """Test que obtiene gastos sin filtros de período o categoría."""
        mock_client = Mock()
        mock_table = Mock()
        mock_query = Mock()

        gastos_esperados = [
            {
                "id": str(uuid4()),
                "user": "test_user",
                "monto": 25000.0,
                "item": "Pizza",
                "categoria": "Comida",
            },
            {
                "id": str(uuid4()),
                "user": "test_user",
                "monto": 50000.0,
                "item": "Taxi",
                "categoria": "Transporte",
            },
        ]

        mock_query.execute.return_value = Mock(data=gastos_esperados)
        mock_query.limit.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_table.select.return_value = mock_query
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.obtener_gastos(user="test_user")

        assert resultado == gastos_esperados
        mock_query.eq.assert_called_with("user", "test_user")
        mock_query.order.assert_called_with("created_at", desc=True)
        mock_query.limit.assert_called_with(100)

    @patch("app.database.get_supabase_client")
    def test_obtener_gastos_con_periodo(self, mock_get_client):
        """Test que obtiene gastos filtrados por período."""
        mock_client = Mock()
        mock_table = Mock()
        mock_query = Mock()

        mock_query.execute.return_value = Mock(data=[])
        mock_query.limit.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.gte.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_table.select.return_value = mock_query
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.obtener_gastos(user="test_user", periodo="semana")

        assert resultado == []
        mock_query.gte.assert_called_once()  # Debe llamar a gte para el filtro de fecha

    @patch("app.database.get_supabase_client")
    def test_obtener_gastos_con_categoria(self, mock_get_client):
        """Test que obtiene gastos filtrados por categoría."""
        mock_client = Mock()
        mock_table = Mock()
        mock_query = Mock()

        gastos_esperados = [
            {
                "id": str(uuid4()),
                "user": "test_user",
                "monto": 25000.0,
                "item": "Pizza",
                "categoria": "Comida",
            },
        ]

        mock_query.execute.return_value = Mock(data=gastos_esperados)
        mock_query.limit.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.gte.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_table.select.return_value = mock_query
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.obtener_gastos(user="test_user", periodo="mes", categoria="Comida")

        assert resultado == gastos_esperados
        # Debe llamar a eq dos veces: una para user y otra para categoria
        assert mock_query.eq.call_count >= 2


class TestActualizarGasto:
    """Tests para la función actualizar_gasto."""

    @patch("app.database.get_supabase_client")
    def test_actualizar_gasto_exitoso(self, mock_get_client):
        """Test que actualiza un gasto correctamente."""
        mock_client = Mock()
        mock_table = Mock()
        mock_update = Mock()
        mock_execute = Mock()

        gasto_id = str(uuid4())
        gasto_actualizado = {
            "id": gasto_id,
            "user": "test_user",
            "monto": 30000.0,  # Actualizado
            "item": "Pizza Grande",  # Actualizado
            "categoria": "Comida",
        }

        mock_execute.return_value = Mock(data=[gasto_actualizado])
        mock_update.execute = mock_execute
        mock_update.eq.return_value = mock_update
        mock_table.update.return_value = mock_update
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.actualizar_gasto(
            gasto_id=gasto_id,
            campos={"monto": 30000.0, "item": "Pizza Grande"},
        )

        assert resultado == gasto_actualizado
        mock_table.update.assert_called_once_with({"monto": 30000.0, "item": "Pizza Grande"})
        mock_update.eq.assert_called_with("id", gasto_id)

    def test_actualizar_gasto_id_invalido(self):
        """Test que valida que el ID sea un UUID válido."""
        with pytest.raises(ValueError, match="ID de gasto inválido"):
            database.actualizar_gasto(gasto_id="no-es-un-uuid", campos={"monto": 1000})

    def test_actualizar_gasto_campos_no_permitidos(self):
        """Test que valida que solo se puedan actualizar campos permitidos."""
        gasto_id = str(uuid4())

        with pytest.raises(ValueError, match="Campos no permitidos"):
            database.actualizar_gasto(
                gasto_id=gasto_id,
                campos={"user": "otro_user"},  # user no es actualizable
            )

    def test_actualizar_gasto_monto_invalido(self):
        """Test que valida el monto al actualizar."""
        gasto_id = str(uuid4())

        with pytest.raises(ValueError, match="El monto debe ser mayor a 0"):
            database.actualizar_gasto(gasto_id=gasto_id, campos={"monto": -100})


class TestEliminarGasto:
    """Tests para la función eliminar_gasto."""

    @patch("app.database.get_supabase_client")
    def test_eliminar_gasto_exitoso(self, mock_get_client):
        """Test que elimina un gasto correctamente."""
        mock_client = Mock()
        mock_table = Mock()
        mock_delete = Mock()
        mock_execute = Mock()

        gasto_id = str(uuid4())
        gasto_eliminado = {"id": gasto_id}

        mock_execute.return_value = Mock(data=[gasto_eliminado])
        mock_delete.execute = mock_execute
        mock_delete.eq.return_value = mock_delete
        mock_table.delete.return_value = mock_delete
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.eliminar_gasto(gasto_id=gasto_id)

        assert resultado is True
        mock_delete.eq.assert_called_with("id", gasto_id)

    @patch("app.database.get_supabase_client")
    def test_eliminar_gasto_no_encontrado(self, mock_get_client):
        """Test cuando se intenta eliminar un gasto que no existe."""
        mock_client = Mock()
        mock_table = Mock()
        mock_delete = Mock()
        mock_execute = Mock()

        gasto_id = str(uuid4())

        mock_execute.return_value = Mock(data=[])  # No se encontró
        mock_delete.execute = mock_execute
        mock_delete.eq.return_value = mock_delete
        mock_table.delete.return_value = mock_delete
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.eliminar_gasto(gasto_id=gasto_id)

        assert resultado is False

    def test_eliminar_gasto_id_invalido(self):
        """Test que valida que el ID sea un UUID válido."""
        with pytest.raises(ValueError, match="ID de gasto inválido"):
            database.eliminar_gasto(gasto_id="no-es-un-uuid")


class TestObtenerGastoPorId:
    """Tests para la función obtener_gasto_por_id."""

    @patch("app.database.get_supabase_client")
    def test_obtener_gasto_por_id_exitoso(self, mock_get_client):
        """Test que obtiene un gasto por su ID."""
        mock_client = Mock()
        mock_table = Mock()
        mock_query = Mock()

        gasto_id = str(uuid4())
        gasto_esperado = {
            "id": gasto_id,
            "user": "test_user",
            "monto": 25000.0,
            "item": "Pizza",
            "categoria": "Comida",
        }

        mock_query.execute.return_value = Mock(data=[gasto_esperado])
        mock_query.eq.return_value = mock_query
        mock_table.select.return_value = mock_query
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.obtener_gasto_por_id(gasto_id=gasto_id)

        assert resultado == gasto_esperado
        mock_query.eq.assert_called_with("id", gasto_id)

    @patch("app.database.get_supabase_client")
    def test_obtener_gasto_por_id_no_encontrado(self, mock_get_client):
        """Test cuando no se encuentra un gasto por su ID."""
        mock_client = Mock()
        mock_table = Mock()
        mock_query = Mock()

        gasto_id = str(uuid4())

        mock_query.execute.return_value = Mock(data=[])
        mock_query.eq.return_value = mock_query
        mock_table.select.return_value = mock_query
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.obtener_gasto_por_id(gasto_id=gasto_id)

        assert resultado is None

    def test_obtener_gasto_por_id_invalido(self):
        """Test que valida que el ID sea un UUID válido."""
        with pytest.raises(ValueError, match="ID de gasto inválido"):
            database.obtener_gasto_por_id(gasto_id="no-es-un-uuid")
