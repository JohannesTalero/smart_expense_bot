"""Tests para el buffer de mensajes (debounce) en main.py."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app import main


class TestMessageBuffer:
    """Tests para el sistema de buffer de mensajes."""

    @pytest.fixture(autouse=True)
    def reset_buffer(self):
        """Limpia el buffer antes y después de cada test."""
        main.pending_messages.clear()
        main.pending_timers.clear()
        yield
        main.pending_messages.clear()
        main.pending_timers.clear()

    @pytest.fixture
    def mock_telegram_client(self):
        """Mock para httpx.AsyncClient."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        return mock_client

    def create_text_update(self, chat_id: int, user_id: int, text: str) -> dict:
        """Helper para crear un update de Telegram con texto."""
        return {
            "update_id": 123456,
            "message": {
                "message_id": 1,
                "from": {
                    "id": user_id,
                    "first_name": "Test",
                    "last_name": "User",
                },
                "chat": {"id": chat_id},
                "text": text,
            },
        }

    @pytest.mark.asyncio
    async def test_single_message_goes_to_buffer(self, mock_telegram_client):
        """Un mensaje de texto debe ir al buffer, no procesarse inmediatamente."""
        chat_id = 12345
        update = self.create_text_update(chat_id, 999, "Hola")

        with patch("app.main.settings") as mock_settings:
            mock_settings.is_user_allowed.return_value = True
            mock_settings.telegram_bot_token = "fake_token"

            with patch("httpx.AsyncClient", return_value=mock_telegram_client):
                await main.process_update(update)

        # Verificar que el mensaje está en el buffer
        assert chat_id in main.pending_messages
        assert len(main.pending_messages[chat_id]) == 1
        assert main.pending_messages[chat_id][0]["text"] == "Hola"

        # Verificar que hay un timer programado
        assert chat_id in main.pending_timers

    @pytest.mark.asyncio
    async def test_multiple_messages_accumulate_in_buffer(self, mock_telegram_client):
        """Múltiples mensajes del mismo chat deben acumularse en el buffer."""
        chat_id = 12345

        with patch("app.main.settings") as mock_settings:
            mock_settings.is_user_allowed.return_value = True
            mock_settings.telegram_bot_token = "fake_token"

            with patch("httpx.AsyncClient", return_value=mock_telegram_client):
                # Enviar 3 mensajes fragmentados
                await main.process_update(self.create_text_update(chat_id, 999, "Hola"))
                await main.process_update(self.create_text_update(chat_id, 999, "cómo"))
                await main.process_update(self.create_text_update(chat_id, 999, "estás?"))

        # Verificar que los 3 mensajes están en el buffer
        assert chat_id in main.pending_messages
        assert len(main.pending_messages[chat_id]) == 3
        assert main.pending_messages[chat_id][0]["text"] == "Hola"
        assert main.pending_messages[chat_id][1]["text"] == "cómo"
        assert main.pending_messages[chat_id][2]["text"] == "estás?"

    @pytest.mark.asyncio
    async def test_buffer_processes_after_delay(self, mock_telegram_client):
        """Después del delay, el buffer debe procesarse y concatenar mensajes."""
        chat_id = 12345
        original_delay = main.MESSAGE_BUFFER_DELAY

        try:
            # Reducir delay para el test
            main.MESSAGE_BUFFER_DELAY = 0.1

            with patch("app.main.settings") as mock_settings:
                mock_settings.is_user_allowed.return_value = True
                mock_settings.telegram_bot_token = "fake_token"

                with patch("httpx.AsyncClient", return_value=mock_telegram_client):
                    with patch("app.main.procesar_mensaje") as mock_procesar:
                        mock_procesar.return_value = "Respuesta de Miss Toña"

                        # Enviar mensajes fragmentados
                        await main.process_update(self.create_text_update(chat_id, 999, "Hola"))
                        await main.process_update(self.create_text_update(chat_id, 999, "mundo"))

                        # Esperar a que el timer expire
                        await asyncio.sleep(0.3)

                        # Verificar que se llamó a procesar_mensaje con texto concatenado
                        mock_procesar.assert_called_once()
                        call_args = mock_procesar.call_args
                        assert call_args.kwargs["texto"] == "Hola mundo"

        finally:
            main.MESSAGE_BUFFER_DELAY = original_delay

    @pytest.mark.asyncio
    async def test_buffer_cleared_after_processing(self, mock_telegram_client):
        """El buffer debe limpiarse después de procesar los mensajes."""
        chat_id = 12345
        original_delay = main.MESSAGE_BUFFER_DELAY

        try:
            main.MESSAGE_BUFFER_DELAY = 0.1

            with patch("app.main.settings") as mock_settings:
                mock_settings.is_user_allowed.return_value = True
                mock_settings.telegram_bot_token = "fake_token"

                with patch("httpx.AsyncClient", return_value=mock_telegram_client):
                    with patch("app.main.procesar_mensaje") as mock_procesar:
                        mock_procesar.return_value = "Ok"

                        await main.process_update(self.create_text_update(chat_id, 999, "Test"))
                        await asyncio.sleep(0.3)

                        # Buffer debe estar vacío
                        assert chat_id not in main.pending_messages
                        assert chat_id not in main.pending_timers

        finally:
            main.MESSAGE_BUFFER_DELAY = original_delay

    @pytest.mark.asyncio
    async def test_different_chats_have_separate_buffers(self, mock_telegram_client):
        """Cada chat debe tener su propio buffer independiente."""
        chat_id_1 = 11111
        chat_id_2 = 22222

        with patch("app.main.settings") as mock_settings:
            mock_settings.is_user_allowed.return_value = True
            mock_settings.telegram_bot_token = "fake_token"

            with patch("httpx.AsyncClient", return_value=mock_telegram_client):
                await main.process_update(self.create_text_update(chat_id_1, 999, "Mensaje chat 1"))
                await main.process_update(self.create_text_update(chat_id_2, 888, "Mensaje chat 2"))

        # Cada chat tiene su buffer separado
        assert chat_id_1 in main.pending_messages
        assert chat_id_2 in main.pending_messages
        assert main.pending_messages[chat_id_1][0]["text"] == "Mensaje chat 1"
        assert main.pending_messages[chat_id_2][0]["text"] == "Mensaje chat 2"

    @pytest.mark.asyncio
    async def test_timer_resets_with_new_message(self, mock_telegram_client):
        """El timer debe reiniciarse cuando llega un nuevo mensaje."""
        chat_id = 12345
        original_delay = main.MESSAGE_BUFFER_DELAY

        try:
            main.MESSAGE_BUFFER_DELAY = 0.2

            with patch("app.main.settings") as mock_settings:
                mock_settings.is_user_allowed.return_value = True
                mock_settings.telegram_bot_token = "fake_token"

                with patch("httpx.AsyncClient", return_value=mock_telegram_client):
                    with patch("app.main.procesar_mensaje") as mock_procesar:
                        mock_procesar.return_value = "Ok"

                        # Enviar primer mensaje
                        await main.process_update(self.create_text_update(chat_id, 999, "Hola"))

                        # Esperar menos que el delay
                        await asyncio.sleep(0.1)

                        # Enviar segundo mensaje (debe reiniciar timer)
                        await main.process_update(self.create_text_update(chat_id, 999, "mundo"))

                        # Esperar un poco más (pero menos que delay desde el segundo mensaje)
                        await asyncio.sleep(0.15)

                        # Aún no debe haberse procesado
                        assert not mock_procesar.called

                        # Esperar a que expire el timer
                        await asyncio.sleep(0.15)

                        # Ahora sí debe haberse procesado con ambos mensajes
                        mock_procesar.assert_called_once()
                        assert mock_procesar.call_args.kwargs["texto"] == "Hola mundo"

        finally:
            main.MESSAGE_BUFFER_DELAY = original_delay


class TestMediaMessagesImmediate:
    """Tests para verificar que mensajes con media se procesan inmediatamente."""

    @pytest.fixture(autouse=True)
    def reset_buffer(self):
        """Limpia el buffer antes y después de cada test."""
        main.pending_messages.clear()
        main.pending_timers.clear()
        yield
        main.pending_messages.clear()
        main.pending_timers.clear()

    @pytest.fixture
    def mock_telegram_client(self):
        """Mock para httpx.AsyncClient."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        return mock_client

    @pytest.mark.asyncio
    async def test_voice_message_processed_immediately(self, mock_telegram_client):
        """Mensajes de voz deben procesarse inmediatamente, no ir al buffer."""
        chat_id = 12345
        update = {
            "update_id": 123456,
            "message": {
                "message_id": 1,
                "from": {"id": 999, "first_name": "Test"},
                "chat": {"id": chat_id},
                "voice": {"file_id": "voice_file_123", "duration": 5},
            },
        }

        with patch("app.main.settings") as mock_settings:
            mock_settings.is_user_allowed.return_value = True
            mock_settings.telegram_bot_token = "fake_token"

            with patch("httpx.AsyncClient", return_value=mock_telegram_client):
                with patch("app.main.transcribir_audio_telegram") as mock_transcribir:
                    mock_transcribir.return_value = "Texto del audio"

                    with patch("app.main.procesar_mensaje") as mock_procesar:
                        mock_procesar.return_value = "Respuesta"

                        await main.process_update(update)

                        # Debe haberse procesado inmediatamente
                        mock_procesar.assert_called_once()

        # No debe estar en el buffer
        assert chat_id not in main.pending_messages

    @pytest.mark.asyncio
    async def test_photo_message_processed_immediately(self, mock_telegram_client):
        """Mensajes con foto deben procesarse inmediatamente, no ir al buffer."""
        chat_id = 12345
        update = {
            "update_id": 123456,
            "message": {
                "message_id": 1,
                "from": {"id": 999, "first_name": "Test"},
                "chat": {"id": chat_id},
                "photo": [
                    {"file_id": "small_photo", "width": 100, "height": 100},
                    {"file_id": "large_photo", "width": 800, "height": 600},
                ],
            },
        }

        with patch("app.main.settings") as mock_settings:
            mock_settings.is_user_allowed.return_value = True
            mock_settings.telegram_bot_token = "fake_token"

            with patch("httpx.AsyncClient", return_value=mock_telegram_client):
                with patch("app.main.procesar_imagen_telegram") as mock_imagen:
                    mock_imagen.return_value = {
                        "monto": 50000,
                        "descripcion": "Almuerzo",
                        "categoria": "Comida",
                        "establecimiento": "Restaurante",
                        "confianza": 0.9,
                    }

                    with patch("app.main.procesar_mensaje") as mock_procesar:
                        mock_procesar.return_value = "Gasto registrado"

                        await main.process_update(update)

                        # Debe haberse procesado inmediatamente
                        mock_procesar.assert_called_once()

        # No debe estar en el buffer
        assert chat_id not in main.pending_messages

