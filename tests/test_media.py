"""Tests unitarios para el módulo de procesamiento multimedia."""

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

