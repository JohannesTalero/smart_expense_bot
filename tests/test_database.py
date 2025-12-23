"""Tests unitarios para el módulo de base de datos."""

from datetime import date, datetime, timedelta
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
        # Finanzas compartidas: no se filtra por usuario
        mock_query.eq.assert_not_called()
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
        mock_query.lte.return_value = mock_query
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
        mock_query.lte.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_table.select.return_value = mock_query
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.obtener_gastos(user="test_user", periodo="mes", categoria="Comida")

        assert resultado == gastos_esperados
        # Finanzas compartidas: se filtra por categoría (y también por fechas del periodo)
        assert mock_query.eq.called


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


class TestParsearFecha:
    """Tests para la función parsear_fecha."""

    def test_parsear_fecha_none(self):
        """Test que None devuelve la fecha actual."""
        resultado = database.parsear_fecha(None)
        assert resultado == date.today()

    def test_parsear_fecha_hoy(self):
        """Test que 'hoy' devuelve la fecha actual."""
        resultado = database.parsear_fecha("hoy")
        assert resultado == date.today()

    def test_parsear_fecha_ayer(self):
        """Test que 'ayer' devuelve la fecha de ayer."""
        resultado = database.parsear_fecha("ayer")
        assert resultado == date.today() - timedelta(days=1)

    def test_parsear_fecha_anteayer(self):
        """Test que 'anteayer' devuelve hace 2 días."""
        resultado = database.parsear_fecha("anteayer")
        assert resultado == date.today() - timedelta(days=2)

    def test_parsear_fecha_antier(self):
        """Test que 'antier' devuelve hace 2 días."""
        resultado = database.parsear_fecha("antier")
        assert resultado == date.today() - timedelta(days=2)

    def test_parsear_fecha_hace_dias(self):
        """Test que 'hace X días' funciona correctamente."""
        resultado = database.parsear_fecha("hace 5 días")
        assert resultado == date.today() - timedelta(days=5)

    def test_parsear_fecha_hace_dias_sin_acento(self):
        """Test que 'hace X dias' sin acento funciona."""
        resultado = database.parsear_fecha("hace 3 dias")
        assert resultado == date.today() - timedelta(days=3)

    def test_parsear_fecha_iso(self):
        """Test que fechas ISO YYYY-MM-DD funcionan."""
        resultado = database.parsear_fecha("2025-12-25")
        assert resultado == date(2025, 12, 25)

    def test_parsear_fecha_formato_slash(self):
        """Test que fechas DD/MM/YYYY funcionan."""
        resultado = database.parsear_fecha("25/12/2025")
        assert resultado == date(2025, 12, 25)

    def test_parsear_fecha_formato_guion(self):
        """Test que fechas DD-MM-YYYY funcionan."""
        resultado = database.parsear_fecha("25-12-2025")
        assert resultado == date(2025, 12, 25)

    def test_parsear_fecha_dia_semana_lunes(self):
        """Test que días de la semana funcionan."""
        resultado = database.parsear_fecha("el lunes")
        # Verificamos que sea un lunes (weekday == 0)
        assert resultado.weekday() == 0
        # Y que sea en el pasado o hoy
        assert resultado <= date.today()

    def test_parsear_fecha_invalida(self):
        """Test que fechas inválidas devuelven hoy con warning."""
        resultado = database.parsear_fecha("fecha-invalida-xyz")
        assert resultado == date.today()


class TestGetSupabaseClient:
    """Tests para la función get_supabase_client."""

    @patch("app.database.create_client")
    @patch("app.database.get_settings")
    def test_get_supabase_client_singleton(self, mock_get_settings, mock_create_client):
        """Test que el cliente de Supabase se crea solo una vez (singleton)."""
        mock_settings = Mock()
        mock_settings.supabase_url = "https://test.supabase.co"
        mock_settings.supabase_key = "test-key"
        mock_get_settings.return_value = mock_settings

        mock_client = Mock()
        mock_create_client.return_value = mock_client

        # Resetear singleton
        database._supabase_client = None

        # Llamar múltiples veces
        client1 = database.get_supabase_client()
        client2 = database.get_supabase_client()

        # Debe ser la misma instancia
        assert client1 is client2
        # Debe haberse creado solo una vez
        assert mock_create_client.call_count == 1


class TestInsertarGastoConFecha:
    """Tests para la función insertar_gasto con fecha."""

    @patch("app.database.get_supabase_client")
    def test_insertar_gasto_con_fecha_ayer(self, mock_get_client):
        """Test que inserta un gasto con fecha de ayer."""
        mock_client = Mock()
        mock_table = Mock()
        mock_insert = Mock()
        mock_execute = Mock()

        gasto_insertado = {
            "id": str(uuid4()),
            "user": "test_user",
            "monto": 25000.0,
            "item": "Cena",
            "categoria": "Comida",
            "fecha_gasto": (date.today() - timedelta(days=1)).isoformat(),
            "created_at": datetime.utcnow().isoformat(),
        }

        mock_execute.return_value = Mock(data=[gasto_insertado])
        mock_insert.execute = mock_execute
        mock_table.insert.return_value = mock_insert
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.insertar_gasto(
            user="test_user",
            monto=25000.0,
            item="Cena",
            categoria="Comida",
            fecha_gasto="ayer",
        )

        assert resultado == gasto_insertado
        # Verificar que se llamó a insert
        mock_table.insert.assert_called_once()
        # Verificar que la fecha_gasto sea ayer
        call_args = mock_table.insert.call_args[0][0]
        assert call_args["fecha_gasto"] == (date.today() - timedelta(days=1)).isoformat()


class TestObtenerGastosConPeriodos:
    """Tests adicionales para obtener_gastos con diferentes períodos."""

    @patch("app.database.get_supabase_client")
    def test_obtener_gastos_periodo_hoy(self, mock_get_client):
        """Test que obtiene gastos de hoy."""
        mock_client = Mock()
        mock_table = Mock()
        mock_query = Mock()

        mock_query.execute.return_value = Mock(data=[])
        mock_query.limit.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_table.select.return_value = mock_query
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.obtener_gastos(periodo="hoy")

        assert resultado == []
        # Debe filtrar por fecha exacta de hoy
        mock_query.eq.assert_called_once_with("fecha_gasto", date.today().isoformat())

    @patch("app.database.get_supabase_client")
    def test_obtener_gastos_periodo_ayer(self, mock_get_client):
        """Test que obtiene gastos de ayer."""
        mock_client = Mock()
        mock_table = Mock()
        mock_query = Mock()

        mock_query.execute.return_value = Mock(data=[])
        mock_query.limit.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_table.select.return_value = mock_query
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.obtener_gastos(periodo="ayer")

        assert resultado == []
        ayer = (date.today() - timedelta(days=1)).isoformat()
        mock_query.eq.assert_called_once_with("fecha_gasto", ayer)

    @patch("app.database.get_supabase_client")
    def test_obtener_gastos_periodo_anio(self, mock_get_client):
        """Test que obtiene gastos del año."""
        mock_client = Mock()
        mock_table = Mock()
        mock_query = Mock()

        mock_query.execute.return_value = Mock(data=[])
        mock_query.limit.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.gte.return_value = mock_query
        mock_query.lte.return_value = mock_query
        mock_table.select.return_value = mock_query
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.obtener_gastos(periodo="año")

        assert resultado == []
        # Debe usar rango de fechas
        mock_query.gte.assert_called_once()
        mock_query.lte.assert_called_once()


class TestActualizarGastoConFecha:
    """Tests para actualizar_gasto con fecha."""

    @patch("app.database.get_supabase_client")
    def test_actualizar_gasto_con_fecha_texto(self, mock_get_client):
        """Test que actualiza un gasto con fecha en texto."""
        mock_client = Mock()
        mock_table = Mock()
        mock_update = Mock()
        mock_execute = Mock()

        gasto_id = str(uuid4())
        gasto_actualizado = {
            "id": gasto_id,
            "fecha_gasto": (date.today() - timedelta(days=1)).isoformat(),
        }

        mock_execute.return_value = Mock(data=[gasto_actualizado])
        mock_update.execute = mock_execute
        mock_update.eq.return_value = mock_update
        mock_table.update.return_value = mock_update
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        resultado = database.actualizar_gasto(
            gasto_id=gasto_id,
            campos={"fecha_gasto": "ayer"},
        )

        assert resultado == gasto_actualizado
        # Verificar que se convirtió la fecha de texto a ISO
        call_args = mock_table.update.call_args[0][0]
        assert call_args["fecha_gasto"] == (date.today() - timedelta(days=1)).isoformat()
