"""Tests unitarios para el módulo de procesamiento multimedia."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pathlib import Path

from app import media


class TestTranscribirAudio:
    """Tests para la función transcribir_audio."""

    @patch("app.media.get_openai_client")
    def test_transcribir_audio_exitoso(self, mock_get_client):
        """Test que transcribe audio correctamente."""
        # Mock del cliente OpenAI
        mock_client = Mock()
        mock_transcript = Mock()
        mock_transcript.text = "  Gasté cincuenta mil en taxi  "
        mock_client.audio.transcriptions.create.return_value = mock_transcript
        mock_get_client.return_value = mock_client
        
        # Simular bytes de audio (no importa el contenido para el mock)
        audio_bytes = b"fake audio content"
        
        resultado = media.transcribir_audio(audio_bytes, "test.ogg")
        
        # Verificar resultado
        assert resultado == "Gasté cincuenta mil en taxi"
        mock_client.audio.transcriptions.create.assert_called_once()
        
        # Verificar que se pasó el modelo y lenguaje correctos
        call_kwargs = mock_client.audio.transcriptions.create.call_args
        assert call_kwargs.kwargs["model"] == "whisper-1"
        assert call_kwargs.kwargs["language"] == "es"

    @patch("app.media.get_openai_client")
    def test_transcribir_audio_error(self, mock_get_client):
        """Test que maneja errores de transcripción."""
        mock_client = Mock()
        mock_client.audio.transcriptions.create.side_effect = Exception("API Error")
        mock_get_client.return_value = mock_client
        
        audio_bytes = b"fake audio content"
        
        with pytest.raises(Exception, match="API Error"):
            media.transcribir_audio(audio_bytes)


class TestDescargarArchivoTelegram:
    """Tests para la función descargar_archivo_telegram."""

    @pytest.mark.asyncio
    @patch("app.media.get_settings")
    async def test_descargar_archivo_exitoso(self, mock_get_settings):
        """Test que descarga un archivo de Telegram correctamente."""
        # Mock de settings
        mock_settings = Mock()
        mock_settings.telegram_bot_token = "test_token"
        mock_get_settings.return_value = mock_settings
        
        # Mock de respuestas HTTP
        file_info_response = {
            "ok": True,
            "result": {"file_path": "voice/file_123.ogg"}
        }
        file_content = b"fake audio content bytes"
        
        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance
            
            # Primera llamada: getFile
            mock_get_response = Mock()
            mock_get_response.status_code = 200
            mock_get_response.json.return_value = file_info_response
            
            # Segunda llamada: descargar archivo
            mock_download_response = Mock()
            mock_download_response.status_code = 200
            mock_download_response.content = file_content
            
            mock_client_instance.get.side_effect = [mock_get_response, mock_download_response]
            
            resultado = await media.descargar_archivo_telegram("file_id_123")
            
            assert resultado == file_content
            assert mock_client_instance.get.call_count == 2

    @pytest.mark.asyncio
    @patch("app.media.get_settings")
    async def test_descargar_archivo_error_get_file(self, mock_get_settings):
        """Test que maneja error al obtener info del archivo."""
        mock_settings = Mock()
        mock_settings.telegram_bot_token = "test_token"
        mock_get_settings.return_value = mock_settings
        
        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance
            
            mock_response = Mock()
            mock_response.status_code = 404
            mock_client_instance.get.return_value = mock_response
            
            with pytest.raises(Exception, match="Error obteniendo info del archivo"):
                await media.descargar_archivo_telegram("invalid_file_id")


class TestTranscribirAudioTelegram:
    """Tests para la función transcribir_audio_telegram (flujo completo)."""

    @pytest.mark.asyncio
    @patch("app.media.transcribir_audio")
    @patch("app.media.descargar_archivo_telegram")
    async def test_transcribir_audio_telegram_exitoso(
        self, mock_descargar, mock_transcribir
    ):
        """Test del flujo completo: descargar → transcribir."""
        mock_descargar.return_value = b"audio content"
        mock_transcribir.return_value = "Gasté veinte mil en pizza"
        
        resultado = await media.transcribir_audio_telegram("file_id_123")
        
        assert resultado == "Gasté veinte mil en pizza"
        mock_descargar.assert_called_once_with("file_id_123")
        mock_transcribir.assert_called_once_with(b"audio content")

    @pytest.mark.asyncio
    @patch("app.media.descargar_archivo_telegram")
    async def test_transcribir_audio_telegram_error_descarga(self, mock_descargar):
        """Test que propaga errores de descarga."""
        mock_descargar.side_effect = Exception("Error de red")
        
        with pytest.raises(Exception, match="Error de red"):
            await media.transcribir_audio_telegram("file_id_123")


class TestGetOpenAIClient:
    """Tests para el singleton del cliente OpenAI."""

    @patch("app.media.get_settings")
    @patch("app.media.OpenAI")
    def test_get_openai_client_singleton(self, mock_openai_class, mock_get_settings):
        """Test que el cliente se crea solo una vez."""
        mock_settings = Mock()
        mock_settings.openai_api_key = "test-key"
        mock_get_settings.return_value = mock_settings
        
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        # Resetear singleton
        media._openai_client = None
        
        # Llamar múltiples veces
        client1 = media.get_openai_client()
        client2 = media.get_openai_client()
        
        # Debe ser la misma instancia
        assert client1 is client2
        # Debe haberse creado solo una vez
        mock_openai_class.assert_called_once_with(api_key="test-key")


class TestExtraerRecibo:
    """Tests para la función extraer_recibo."""

    @patch("app.media.get_openai_client")
    def test_extraer_recibo_exitoso(self, mock_get_client):
        """Test que extrae datos de un recibo correctamente."""
        # Mock del cliente OpenAI
        mock_client = Mock()
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        
        # Respuesta JSON simulada
        respuesta_json = json.dumps({
            "monto": 25000,
            "descripcion": "Almuerzo ejecutivo",
            "categoria": "Comida",
            "establecimiento": "Restaurante La Cocina",
            "fecha": "2024-01-15",
            "confianza": 0.95
        })
        
        mock_message.content = respuesta_json
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        # Simular bytes de imagen JPEG (magic bytes)
        image_bytes = b'\xff\xd8fake image content'
        
        resultado = media.extraer_recibo(image_bytes)
        
        # Verificar resultado
        assert resultado["monto"] == 25000.0
        assert resultado["descripcion"] == "Almuerzo ejecutivo"
        assert resultado["categoria"] == "Comida"
        assert resultado["establecimiento"] == "Restaurante La Cocina"
        assert resultado["fecha"] == "2024-01-15"
        assert resultado["confianza"] == 0.95
        
        # Verificar que se llamó al modelo correcto
        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4o-mini"

    @patch("app.media.get_openai_client")
    def test_extraer_recibo_con_codigo_markdown(self, mock_get_client):
        """Test que maneja respuestas con bloques de código markdown."""
        mock_client = Mock()
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        
        # Respuesta con bloques de código markdown
        respuesta_con_markdown = """```json
{
    "monto": 15000,
    "descripcion": "Taxi al aeropuerto",
    "categoria": "Transporte",
    "establecimiento": null,
    "fecha": null,
    "confianza": 0.8
}
```"""
        
        mock_message.content = respuesta_con_markdown
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        # Simular bytes de imagen PNG (magic bytes)
        image_bytes = b'\x89PNG\r\n\x1a\nfake png content'
        
        resultado = media.extraer_recibo(image_bytes)
        
        assert resultado["monto"] == 15000.0
        assert resultado["categoria"] == "Transporte"
        assert resultado["establecimiento"] is None

    @patch("app.media.get_openai_client")
    def test_extraer_recibo_json_invalido(self, mock_get_client):
        """Test que maneja respuestas con JSON inválido."""
        mock_client = Mock()
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        
        # Respuesta no válida
        mock_message.content = "No puedo leer este recibo, está muy borroso"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        image_bytes = b'\xff\xd8fake image'
        
        with pytest.raises(ValueError, match="No se pudo parsear"):
            media.extraer_recibo(image_bytes)

    @patch("app.media.get_openai_client")
    def test_extraer_recibo_error_api(self, mock_get_client):
        """Test que maneja errores de la API."""
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("API rate limit exceeded")
        mock_get_client.return_value = mock_client
        
        image_bytes = b'\xff\xd8fake image'
        
        with pytest.raises(Exception, match="API rate limit exceeded"):
            media.extraer_recibo(image_bytes)

    @patch("app.media.get_openai_client")
    def test_extraer_recibo_confianza_normalizada(self, mock_get_client):
        """Test que normaliza la confianza al rango 0.0-1.0."""
        mock_client = Mock()
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        
        # Respuesta con confianza fuera de rango
        respuesta_json = json.dumps({
            "monto": 5000,
            "descripcion": "Café",
            "categoria": "Comida",
            "establecimiento": None,
            "fecha": None,
            "confianza": 1.5  # Fuera de rango
        })
        
        mock_message.content = respuesta_json
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        image_bytes = b'\xff\xd8fake image'
        
        resultado = media.extraer_recibo(image_bytes)
        
        # Confianza debe estar normalizada a 1.0
        assert resultado["confianza"] == 1.0


class TestProcesarImagenTelegram:
    """Tests para la función procesar_imagen_telegram (flujo completo)."""

    @pytest.mark.asyncio
    @patch("app.media.extraer_recibo")
    @patch("app.media.descargar_archivo_telegram")
    async def test_procesar_imagen_telegram_exitoso(
        self, mock_descargar, mock_extraer
    ):
        """Test del flujo completo: descargar → extraer datos."""
        mock_descargar.return_value = b"image content"
        mock_extraer.return_value = {
            "monto": 30000.0,
            "descripcion": "Supermercado",
            "categoria": "Compras",
            "establecimiento": "Éxito",
            "fecha": "2024-01-20",
            "confianza": 0.9
        }
        
        resultado = await media.procesar_imagen_telegram("file_id_456")
        
        assert resultado["monto"] == 30000.0
        assert resultado["categoria"] == "Compras"
        mock_descargar.assert_called_once_with("file_id_456")
        mock_extraer.assert_called_once_with(b"image content")

    @pytest.mark.asyncio
    @patch("app.media.descargar_archivo_telegram")
    async def test_procesar_imagen_telegram_error_descarga(self, mock_descargar):
        """Test que propaga errores de descarga."""
        mock_descargar.side_effect = Exception("Error de red")
        
        with pytest.raises(Exception, match="Error de red"):
            await media.procesar_imagen_telegram("file_id_456")

