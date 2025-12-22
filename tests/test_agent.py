"""Tests unitarios para el módulo de agente LLM."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from uuid import uuid4

from app import agent, database, sheets


class TestTools:
    """Tests para las tools individuales del agente."""

    @patch("app.agent.database.insertar_gasto")
    @patch("app.agent.sheets.obtener_presupuesto")
    @patch("app.agent.database.obtener_gastos")
    def test_registrar_gasto_exitoso(
        self, mock_obtener_gastos, mock_obtener_presupuesto, mock_insertar_gasto
    ):
        """Test que registra un gasto correctamente."""
        # Mock de datos
        gasto_id = str(uuid4())
        mock_insertar_gasto.return_value = {
            "id": gasto_id,
            "user": "test_user",
            "monto": 25000.0,
            "item": "Pizza",
            "categoria": "Comida",
            "created_at": datetime.utcnow().isoformat(),
        }
        
        mock_obtener_presupuesto.return_value = 200000.0
        mock_obtener_gastos.return_value = [
            {"monto": 25000.0},
        ]
        
        # Ejecutar tool
        resultado = agent.registrar_gasto.invoke({
            "monto": 25000.0,
            "item": "Pizza",
            "categoria": "Comida",
        })
        
        # Verificaciones
        assert "Gasto registrado exitosamente" in resultado
        assert "25,000" in resultado or "25000" in resultado  # Acepta formato con o sin comas
        assert "Pizza" in resultado
        assert "Comida" in resultado
        mock_insertar_gasto.assert_called_once()

    @patch("app.agent.database.insertar_gasto")
    def test_registrar_gasto_error_validacion(self, mock_insertar_gasto):
        """Test que maneja errores de validación."""
        mock_insertar_gasto.side_effect = ValueError("El monto debe ser mayor a 0")
        
        resultado = agent.registrar_gasto.invoke({
            "monto": -100,
            "item": "Test",
            "categoria": "Test",
        })
        
        assert "Error de validación" in resultado

    @patch("app.agent.database.actualizar_gasto")
    def test_editar_gasto_exitoso(self, mock_actualizar_gasto):
        """Test que edita un gasto correctamente."""
        gasto_id = str(uuid4())
        mock_actualizar_gasto.return_value = {
            "id": gasto_id,
            "monto": 30000.0,
            "item": "Pizza Grande",
        }
        
        resultado = agent.editar_gasto.invoke({
            "gasto_id": gasto_id,
            "campo": "monto",
            "nuevo_valor": 30000.0,
        })
        
        assert "Gasto actualizado exitosamente" in resultado
        assert gasto_id in resultado
        mock_actualizar_gasto.assert_called_once()

    @patch("app.agent.database.eliminar_gasto")
    def test_eliminar_gasto_exitoso(self, mock_eliminar_gasto):
        """Test que elimina un gasto correctamente."""
        gasto_id = str(uuid4())
        mock_eliminar_gasto.return_value = True
        
        resultado = agent.eliminar_gasto.invoke({"gasto_id": gasto_id})
        
        assert "Gasto eliminado exitosamente" in resultado
        assert gasto_id in resultado
        mock_eliminar_gasto.assert_called_once_with(gasto_id)

    @patch("app.agent.database.obtener_gastos")
    def test_listar_gastos_exitoso(self, mock_obtener_gastos):
        """Test que lista gastos correctamente."""
        mock_obtener_gastos.return_value = [
            {
                "id": str(uuid4()),
                "monto": 25000.0,
                "item": "Pizza",
                "categoria": "Comida",
                "created_at": datetime.utcnow().isoformat(),
            },
            {
                "id": str(uuid4()),
                "monto": 50000.0,
                "item": "Taxi",
                "categoria": "Transporte",
                "created_at": datetime.utcnow().isoformat(),
            },
        ]
        
        resultado = agent.listar_gastos.invoke({"periodo": "mes"})
        
        assert "Encontré 2 gasto(s)" in resultado
        assert "75000" in resultado or "75,000" in resultado
        assert "Pizza" in resultado
        assert "Taxi" in resultado
        mock_obtener_gastos.assert_called_once()

    @patch("app.agent.database.obtener_gastos")
    def test_listar_gastos_vacio(self, mock_obtener_gastos):
        """Test que maneja cuando no hay gastos."""
        mock_obtener_gastos.return_value = []
        
        resultado = agent.listar_gastos.invoke({"periodo": "mes"})
        
        assert "No se encontraron gastos" in resultado

    @patch("app.agent.database.obtener_gastos")
    @patch("app.agent.sheets.obtener_presupuesto")
    def test_verificar_presupuesto_exitoso(
        self, mock_obtener_presupuesto, mock_obtener_gastos
    ):
        """Test que verifica presupuesto correctamente."""
        mock_obtener_presupuesto.return_value = 200000.0
        mock_obtener_gastos.return_value = [
            {"monto": 50000.0},
            {"monto": 30000.0},
        ]
        
        resultado = agent.verificar_presupuesto.invoke({"categoria": "Comida"})
        
        assert "Presupuesto de Comida" in resultado
        assert "200000" in resultado or "200,000" in resultado
        assert "80000" in resultado or "80,000" in resultado
        assert "40.0%" in resultado or "40%" in resultado

    @patch("app.agent.sheets.obtener_presupuesto")
    def test_verificar_presupuesto_no_encontrado(self, mock_obtener_presupuesto):
        """Test que maneja cuando no hay presupuesto definido."""
        mock_obtener_presupuesto.return_value = None
        
        resultado = agent.verificar_presupuesto.invoke({"categoria": "CategoriaInexistente"})
        
        assert "No se encontró un presupuesto definido" in resultado

    @patch("app.agent.database.obtener_gastos")
    @patch("app.agent.sheets.obtener_presupuesto")
    def test_generar_reporte_exitoso(
        self, mock_obtener_presupuesto, mock_obtener_gastos
    ):
        """Test que genera un reporte correctamente."""
        mock_obtener_gastos.return_value = [
            {
                "monto": 25000.0,
                "categoria": "Comida",
            },
            {
                "monto": 50000.0,
                "categoria": "Transporte",
            },
        ]
        
        # Mock para obtener presupuestos
        def mock_presupuesto(categoria):
            if categoria == "Comida":
                return 200000.0
            elif categoria == "Transporte":
                return 100000.0
            return None
        
        mock_obtener_presupuesto.side_effect = mock_presupuesto
        
        resultado = agent.generar_reporte.invoke({"periodo": "mes"})
        
        assert "Reporte de gastos" in resultado
        assert "75000" in resultado or "75,000" in resultado
        assert "Comida" in resultado
        assert "Transporte" in resultado


class TestProcesarMensaje:
    """Tests para la función procesar_mensaje."""

    @patch("app.agent.obtener_agente")
    def test_procesar_mensaje_exitoso(self, mock_obtener_agente):
        """Test que procesa un mensaje correctamente."""
        # Mock del agente
        mock_agente = Mock()
        mock_agente.invoke.return_value = {
            "output": "¡Anotado, miau! 🐱 $25.000 en Pizza 🍕 (Comida)."
        }
        mock_obtener_agente.return_value = mock_agente
        
        resultado = agent.procesar_mensaje("Gasté 25 mil en pizza", user="test_user")
        
        assert "Anotado" in resultado or "miau" in resultado.lower()
        mock_agente.invoke.assert_called_once()

    @patch("app.agent.obtener_agente")
    def test_procesar_mensaje_con_error(self, mock_obtener_agente):
        """Test que maneja errores al procesar mensaje."""
        mock_agente = Mock()
        mock_agente.invoke.side_effect = Exception("Error de conexión")
        mock_obtener_agente.return_value = mock_agente
        
        resultado = agent.procesar_mensaje("Test", user="test_user")
        
        assert "Miau" in resultado or "error" in resultado.lower()
        assert "intentar de nuevo" in resultado.lower() or "intenta" in resultado.lower()

    @patch("app.agent.crear_agente")
    def test_obtener_agente_singleton(self, mock_crear_agente):
        """Test que el agente se crea solo una vez (singleton)."""
        mock_agente = Mock()
        mock_crear_agente.return_value = mock_agente
        
        # Resetear el singleton
        agent._agente = None
        
        # Llamar múltiples veces
        agente1 = agent.obtener_agente()
        agente2 = agent.obtener_agente()
        
        # Debe ser la misma instancia
        assert agente1 is agente2
        # Debe haberse creado solo una vez
        assert mock_crear_agente.call_count == 1


class TestCrearAgente:
    """Tests para la creación del agente."""

    @patch("app.agent.ChatOpenAI")
    @patch("app.agent.create_openai_tools_agent")
    @patch("app.agent.AgentExecutor")
    @patch("app.agent.get_settings")
    def test_crear_agente_configuracion(
        self, mock_get_settings, mock_agent_executor, mock_create_agent, mock_chat_openai
    ):
        """Test que el agente se crea con la configuración correcta."""
        # Mock de settings
        mock_settings = Mock()
        mock_settings.openai_model = "gpt-4o-mini"
        mock_settings.openai_api_key = "test-key"
        mock_get_settings.return_value = mock_settings
        
        # Mock de componentes
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm
        
        mock_agent = Mock()
        mock_create_agent.return_value = mock_agent
        
        mock_executor = Mock()
        mock_agent_executor.return_value = mock_executor
        
        # Resetear singleton
        agent._agente = None
        
        # Crear agente
        resultado = agent.crear_agente()
        
        # Verificaciones
        assert resultado == mock_executor
        mock_chat_openai.assert_called_once_with(
            model="gpt-4o-mini",
            temperature=0.7,
            api_key="test-key",
        )
        mock_create_agent.assert_called_once()
        mock_agent_executor.assert_called_once()

