"""
app_gui.py
-----------
Interface gráfica (CustomTkinter) para o bot de Text-to-Speech de lives do TikTok.

Dependências:
    pip install customtkinter TikTokLive edge-tts pygame

Arquitetura:
    - A GUI roda no thread principal (mainloop do Tkinter).
    - Todo o trabalho assíncrono (TikTokLive + edge-tts + pygame) roda em uma
      Thread separada, com seu próprio event loop asyncio, para nunca travar a GUI.
    - A comunicação Thread -> GUI é feita via queue.Queue (thread-safe), lida
      periodicamente pelo mainloop através de `self.after(...)`.
    - Comandos GUI -> Thread (como "parar") usam asyncio.run_coroutine_threadsafe.
    - A tela inicial mostra só o essencial (usuário, botão play e status); tema,
      voz, prévia de voz e volume ficam numa janela de Configurações separada.
"""

import os
import sys
import uuid
import queue
import asyncio
import logging
import traceback
import threading
import tempfile
import datetime

import customtkinter as ctk

import edge_tts
import pygame

from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent, CommentEvent

# Exceções específicas do TikTokLive (nem todas as versões da lib expõem as
# mesmas classes, então importamos com fallback seguro para não quebrar o app).
try:
    from TikTokLive.client.errors import (
        UserOfflineError,
        UserNotFoundError,
        AlreadyConnectedError,
    )
except ImportError:
    UserOfflineError = UserNotFoundError = AlreadyConnectedError = ()

try:
    from TikTokLive.client.web.routes.fetch_sign import SignAPIError
except ImportError:
    SignAPIError = ()


# ---------------------------------------------------------------------------
# Configurações gerais
# ---------------------------------------------------------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

APP_NAME = "TikVoice"
APP_VERSION = "1.0.0"

VOICES = {
    "Antônio (Masculino - pt-BR-AntonioNeural)": "pt-BR-AntonioNeural",
    "Francisca (Feminino - pt-BR-FranciscaNeural)": "pt-BR-FranciscaNeural",
    "Thalita (Feminino - pt-BR-ThalitaNeural)": "pt-BR-ThalitaNeural",
}

PREVIEW_TEXT = "Olá! Esta é uma prévia da voz selecionada para o seu chat da live."

# Tamanhos da janela principal com o log visível / oculto
WINDOW_SIZE = "550x680"


class _QueueLogHandler(logging.Handler):
    """Encaminha os logs internos de bibliotecas (ex: TikTokLive) para a GUI.

    Muitos erros (ex: 'usuário offline', falhas de rede) acontecem dentro de
    tasks internas da própria lib e nunca chegam até o nosso try/except em
    volta de client.connect(). Capturando o logger delas, garantimos que o
    motivo real apareça no monitor de chat.
    """

    def __init__(self, log_func):
        super().__init__()
        self.log_func = log_func

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self.log_func(f"[TikTokLive-lib] {msg}")
        except Exception:
            pass


# =============================================================================
# Janela de Configurações (tema, voz, prévia de voz, volume)
# =============================================================================
class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, app: "TikTokTTSApp"):
        super().__init__(app)
        self.app = app

        self.title("Configurações")
        self.geometry("420x460")
        self.resizable(False, False)
        self.transient(app)
        # OBS: propositalmente NÃO usamos grab_set() aqui. Uma janela modal
        # que mantém a captura de eventos durante uma troca de tema (que
        # redesenha todas as janelas abertas) pode ficar "presa" bloqueando
        # cliques em todo o app — inclusive o botão de fechar da janela
        # principal — mesmo se ela sumir de vista.
        self.protocol("WM_DELETE_WINDOW", self._on_settings_close)

        pad = 16

        ctk.CTkLabel(
            self, text="⚙️  Configurações", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(pad, 8))

        # ---------- Aparência (dark / light) ----------
        appearance_frame = ctk.CTkFrame(self, corner_radius=12)
        appearance_frame.pack(fill="x", padx=pad, pady=(0, 12))

        ctk.CTkLabel(appearance_frame, text="Aparência:", anchor="w").pack(
            fill="x", padx=16, pady=(14, 4)
        )

        current_mode = ctk.get_appearance_mode()  # "Dark" ou "Light"
        self.appearance_var = ctk.StringVar(
            value="Escuro" if current_mode == "Dark" else "Claro"
        )
        appearance_switcher = ctk.CTkSegmentedButton(
            appearance_frame,
            values=["Escuro", "Claro"],
            variable=self.appearance_var,
            command=self._on_appearance_change,
        )
        appearance_switcher.pack(fill="x", padx=16, pady=(0, 16))

        # ---------- Voz + prévia ----------
        voice_frame = ctk.CTkFrame(self, corner_radius=12)
        voice_frame.pack(fill="x", padx=pad, pady=(0, 12))

        ctk.CTkLabel(voice_frame, text="Voz:", anchor="w").pack(
            fill="x", padx=16, pady=(14, 4)
        )
        self.voice_menu = ctk.CTkOptionMenu(
            voice_frame, values=list(VOICES.keys()), variable=self.app.voice_var
        )
        self.voice_menu.pack(fill="x", padx=16, pady=(0, 12))

        self.preview_button = ctk.CTkButton(
            voice_frame, text="🔊  Testar voz", command=self._preview_voice
        )
        self.preview_button.pack(fill="x", padx=16, pady=(0, 16))

        # ---------- Volume ----------
        volume_frame = ctk.CTkFrame(self, corner_radius=12)
        volume_frame.pack(fill="x", padx=pad, pady=(0, 12))

        ctk.CTkLabel(volume_frame, text="Volume:", anchor="w").pack(
            fill="x", padx=16, pady=(14, 4)
        )
        volume_row = ctk.CTkFrame(volume_frame, fg_color="transparent")
        volume_row.pack(fill="x", padx=16, pady=(0, 16))
        volume_row.grid_columnconfigure(0, weight=1)

        self.volume_label = ctk.CTkLabel(
            volume_row, text=f"{int(self.app.volume_value)}%", width=40
        )

        def _on_volume(value):
            self.volume_label.configure(text=f"{int(value)}%")
            self.app.set_volume(value)

        volume_slider = ctk.CTkSlider(
            volume_row, from_=0, to=100, number_of_steps=100, command=_on_volume
        )
        volume_slider.set(self.app.volume_value)
        volume_slider.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.volume_label.grid(row=0, column=1)

        # ---------- Fechar ----------
        ctk.CTkLabel(
            self,
            text=f"{APP_NAME} v{APP_VERSION}",
            font=ctk.CTkFont(size=11),
            text_color="gray50",
        ).pack(pady=(0, 2))

        ctk.CTkButton(
            self,
            text="Fechar",
            fg_color="gray30",
            hover_color="gray20",
            command=self._on_settings_close,
        ).pack(pady=(4, pad))

    def _on_settings_close(self):
        self.app.settings_window = None
        self.destroy()

    def _on_appearance_change(self, value):
        try:
            ctk.set_appearance_mode("dark" if value == "Escuro" else "light")
        except Exception as e:
            self.app.log(f"⚠️ Erro ao trocar tema: {e}")

    def _preview_voice(self):
        if self.app.running:
            self.app.log(
                "ℹ️ O bot está ativo — a prévia usa o mesmo player de áudio e "
                "vai aguardar a fala atual terminar antes de tocar."
            )
        self.preview_button.configure(state="disabled", text="🔊  Reproduzindo...")
        threading.Thread(
            target=self.app.play_voice_preview,
            args=(self._on_preview_done,),
            daemon=True,
        ).start()

    def _on_preview_done(self, error_message=None):
        def _update():
            if error_message:
                self.app.log(f"⚠️ Erro na prévia de voz: {error_message}")
            if self.winfo_exists():
                self.preview_button.configure(state="normal", text="🔊  Testar voz")

        self.app.after(0, _update)


# =============================================================================
# Janela principal
# =============================================================================
class TikTokTTSApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME} v{APP_VERSION} • TikTok Live TTS")
        self.geometry(WINDOW_SIZE)
        self.resizable(False, False)

        # --- Estado interno -------------------------------------------------
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.client: TikTokLiveClient | None = None
        self.running = False
        self.log_visible = True
        self.volume_value = 80.0
        self.voice_var = ctk.StringVar(value=list(VOICES.keys())[0])
        self.settings_window: SettingsWindow | None = None

        # Evita que o bot e uma prévia de voz usem o mixer do pygame ao mesmo
        # tempo (pygame.mixer.music só toca uma faixa por vez).
        self.playback_lock = threading.Lock()

        self.temp_dir = tempfile.mkdtemp(prefix="tiktok_tts_")

        # --- Monta a interface -----------------------------------------------
        self._build_ui()

        # Fecha de forma segura ao clicar no X da janela
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Começa a "escutar" a fila de logs vinda da thread de trabalho
        self.after(100, self._poll_log_queue)

    # =========================================================================
    # Construção da interface
    # =========================================================================
    def _build_ui(self):
        pad = 16

        # ---------- Barra superior: título + botão de configurações ----------
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=pad, pady=(pad, 4))

        ctk.CTkLabel(
            top_bar, text=f"🎙️ {APP_NAME}", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(side="left")

        ctk.CTkButton(
            top_bar,
            text="⚙",
            width=36,
            height=36,
            font=ctk.CTkFont(size=16),
            command=self.open_settings,
        ).pack(side="right")

        # ---------- Usuário TikTok ----------
        user_frame = ctk.CTkFrame(self, corner_radius=12)
        user_frame.pack(fill="x", padx=pad, pady=(4, pad))

        ctk.CTkLabel(user_frame, text="Usuário do TikTok:", anchor="w").pack(
            fill="x", padx=16, pady=(14, 4)
        )
        self.username_entry = ctk.CTkEntry(
            user_frame, placeholder_text="Ex: controlee2"
        )
        self.username_entry.insert(0, "controlee2")
        self.username_entry.pack(fill="x", padx=16, pady=(0, 14))

        # ---------- Botão Play grande + status ----------
        center_frame = ctk.CTkFrame(self, fg_color="transparent")
        center_frame.pack(fill="both", expand=True)

        self.play_button = ctk.CTkButton(
            center_frame,
            text="▶   Iniciar",
            width=220,
            height=64,
            corner_radius=32,
            font=ctk.CTkFont(size=20, weight="bold"),
            fg_color="#2fa572",
            hover_color="#248a5d",
            command=self.toggle_bot,
        )
        self.play_button.pack(pady=(32, 16))

        self.status_label = ctk.CTkLabel(
            center_frame,
            text="● Parado",
            text_color="gray60",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.status_label.pack()

        # ---------- Botão mostrar/ocultar log ----------
        self.toggle_log_button = ctk.CTkButton(
            self,
            text="🙈  Ocultar Log",
            fg_color="gray30",
            hover_color="gray20",
            command=self.toggle_log,
        )
        self.toggle_log_button.pack(fill="x", padx=pad, pady=(0, 8))

        # ---------- Monitor do chat (pode ser ocultado) ----------
        self.log_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.log_frame.pack(fill="both", expand=True, padx=pad, pady=(0, pad))

        ctk.CTkLabel(self.log_frame, text="Monitor do Chat / Logs:", anchor="w").pack(
            fill="x"
        )

        self.log_box = ctk.CTkTextbox(
            self.log_frame, corner_radius=10, font=ctk.CTkFont(family="Consolas", size=12)
        )
        self.log_box.pack(fill="both", expand=True, pady=(4, 0))
        self.log_box.configure(state="disabled")

    # =========================================================================
    # Configurações / Log toggle
    # =========================================================================
    def open_settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            self.settings_window.focus_force()
            return
        self.settings_window = SettingsWindow(self)

    def toggle_log(self):
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.log_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
            self.toggle_log_button.configure(text="🙈  Ocultar Log")
        else:
            self.log_frame.pack_forget()
            self.toggle_log_button.configure(text="👁  Mostrar Log")

    def set_volume(self, value):
        self.volume_value = float(value)

    # =========================================================================
    # Utilidades de UI
    # =========================================================================
    def log(self, message: str):
        """Thread-safe: pode ser chamado de qualquer thread."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {message}")

    def _poll_log_queue(self):
        """Roda no thread principal via `after`, esvaziando a fila de logs."""
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", msg + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_log_queue)

    def _set_running_state(self, running: bool):
        self.running = running
        self.play_button.configure(state="normal")
        if running:
            self.play_button.configure(
                text="■   Parar", fg_color="#c0392b", hover_color="#a5301f"
            )
            self.username_entry.configure(state="disabled")
            self.status_label.configure(text="● Conectando...", text_color="#f1c40f")
        else:
            self.play_button.configure(
                text="▶   Iniciar", fg_color="#2fa572", hover_color="#248a5d"
            )
            self.username_entry.configure(state="normal")
            self.status_label.configure(text="● Parado", text_color="gray60")

    # =========================================================================
    # Controle do bot (chamado pelo thread principal / botão play)
    # =========================================================================
    def toggle_bot(self):
        if self.running:
            self.stop_bot()
        else:
            self.start_bot()

    def start_bot(self):
        if self.running:
            return

        username = self.username_entry.get().strip()
        if not username:
            self.log("⚠️ Informe um usuário do TikTok válido.")
            return

        self._set_running_state(True)
        self.log(f"Iniciando conexão com @{username.lstrip('@')}...")

        self.worker_thread = threading.Thread(
            target=self._thread_main, args=(username,), daemon=True
        )
        self.worker_thread.start()

    def stop_bot(self):
        if not self.running:
            return

        self.log("Encerrando conexão, aguarde...")
        self.play_button.configure(state="disabled")

        if self.loop is not None and self.client is not None:
            asyncio.run_coroutine_threadsafe(
                self._async_shutdown(), self.loop
            )
        else:
            self._set_running_state(False)

    def _on_close(self):
        """Fechamento seguro da janela."""
        if self.running:
            self.stop_bot()
            # Dá um tempo curto para a thread encerrar de forma limpa
            self.after(600, self._finish_close)
        else:
            self._finish_close()

    def _finish_close(self):
        if self.worker_thread is not None and self.worker_thread.is_alive():
            # Ainda finalizando -> tenta novamente em breve
            self.after(300, self._finish_close)
            return
        self.destroy()

    # =========================================================================
    # Thread de trabalho (asyncio + TikTokLive + edge-tts + pygame)
    # =========================================================================
    def _thread_main(self, username: str):
        """Ponto de entrada da thread em segundo plano."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Captura exceções levantadas dentro de tasks internas da biblioteca
        # (ex: websocket, heartbeat) que não seriam propagadas até o nosso
        # try/except em volta de client.connect().
        self.loop.set_exception_handler(self._loop_exception_handler)

        # Encaminha os logs internos do TikTokLive (erros, avisos, status de
        # conexão) para o monitor de chat da GUI.
        lib_log_handler = _QueueLogHandler(self.log)
        lib_log_handler.setLevel(logging.INFO)
        lib_log_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        tiktok_lib_logger = logging.getLogger("TikTokLive")
        tiktok_lib_logger.setLevel(logging.INFO)
        tiktok_lib_logger.addHandler(lib_log_handler)

        try:
            pygame.mixer.init()
        except Exception as e:
            self.log(f"❌ Erro ao iniciar o mixer de áudio: {e}")
            self.after(0, lambda: self._set_running_state(False))
            return

        try:
            self.loop.run_until_complete(self._async_main(username))
        except Exception as e:
            self.log(f"❌ Erro fatal na thread ({type(e).__name__}): {e}")
            self.log("Detalhes técnicos:\n" + traceback.format_exc())
        finally:
            tiktok_lib_logger.removeHandler(lib_log_handler)
            try:
                pygame.mixer.quit()
            except Exception:
                pass
            try:
                self.loop.close()
            except Exception:
                pass
            self.loop = None
            self.client = None
            self.log("Thread finalizada. Bot parado.")
            self.after(0, lambda: self._set_running_state(False))

    def _loop_exception_handler(self, loop, context):
        """Chamado pelo asyncio quando uma task levanta exceção sem ser
        aguardada diretamente (comum em tasks internas de bibliotecas)."""
        exc = context.get("exception")
        message = context.get("message", "Erro desconhecido no event loop")

        if exc is not None:
            self.log(f"❌ Erro interno não tratado ({type(exc).__name__}): {exc}")
            self.log(
                "Detalhes técnicos:\n"
                + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            )
        else:
            self.log(f"❌ Erro interno não tratado: {message}")

    async def _async_main(self, username: str):
        tiktok_username = username if username.startswith("@") else f"@{username}"

        self.tts_queue: "asyncio.Queue" = asyncio.Queue()

        try:
            self.client = TikTokLiveClient(unique_id=tiktok_username)
        except Exception as e:
            self.log(f"❌ Não foi possível criar o cliente ({type(e).__name__}): {e}")
            self.log("Detalhes técnicos:\n" + traceback.format_exc())
            return

        @self.client.on(ConnectEvent)
        async def on_connect(event: ConnectEvent):
            self.log(f"✅ Conectado à live de {tiktok_username}!")
            self.after(0, lambda: self.status_label.configure(
                text="● Conectado", text_color="#2fa572"
            ))

        @self.client.on(DisconnectEvent)
        async def on_disconnect(event: DisconnectEvent):
            self.log("🔌 Desconectado da live.")

        @self.client.on(CommentEvent)
        async def on_comment(event: CommentEvent):
            try:
                user = event.user.nickname or event.user.unique_id
            except Exception:
                user = "Usuário"
            text = getattr(event, "comment", "") or ""

            if not text.strip():
                return

            self.log(f"[{user}]: {text}")
            await self.tts_queue.put((user, text))

        tts_task = asyncio.create_task(self._tts_worker())

        try:
            # IMPORTANTE: start() NÃO bloqueia — ele apenas dispara a conexão
            # em uma Task e retorna imediatamente. connect() é o método
            # correto aqui, pois ele aguarda (bloqueia) até a live encerrar
            # ou a conexão cair, o que é o comportamento que queremos numa
            # thread dedicada.
            await self.client.connect()
            self.log("ℹ️ A conexão com a live foi encerrada.")
        except UserOfflineError:
            self.log(
                f"⚠️ @{tiktok_username.lstrip('@')} está offline no momento "
                f"(a pessoa não está fazendo live agora)."
            )
        except UserNotFoundError:
            self.log(
                f"⚠️ Usuário @{tiktok_username.lstrip('@')} não foi encontrado. "
                f"Verifique se o nome de usuário está correto."
            )
        except AlreadyConnectedError:
            self.log("⚠️ Já existe uma conexão ativa com essa live.")
        except SignAPIError as e:
            self.log(
                f"⚠️ Erro no servidor de assinatura (Sign API) da TikTokLive: {e}\n"
                f"Isso geralmente significa limite de requisições atingido (rate limit). "
                f"Aguarde alguns minutos antes de tentar novamente."
            )
        except Exception as e:
            self.log(f"❌ Falha na conexão ({type(e).__name__}): {e}")
            self.log("Detalhes técnicos:\n" + traceback.format_exc())
        finally:
            tts_task.cancel()
            try:
                await tts_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    async def _async_shutdown(self):
        """Encerra a conexão do TikTokLive e para o mixer de forma limpa."""
        try:
            if self.client is not None:
                await self.client.disconnect()
        except Exception as e:
            self.log(f"Aviso ao desconectar: {e}")

        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    async def _tts_worker(self):
        """Consome a fila de comentários e lê cada um em voz alta, um por vez."""
        while True:
            try:
                user, text = await self.tts_queue.get()
            except asyncio.CancelledError:
                break

            try:
                await self._speak(text)
            except Exception as e:
                self.log(f"⚠️ Erro ao gerar/reproduzir áudio ({type(e).__name__}): {e}")
                self.log("Detalhes técnicos:\n" + traceback.format_exc())

    async def _speak(self, text: str):
        voice_label = self.voice_var.get()
        voice_id = VOICES.get(voice_label, "pt-BR-AntonioNeural")

        filename = os.path.join(self.temp_dir, f"tts_{uuid.uuid4().hex}.mp3")

        # Gera o áudio com edge-tts
        communicate = edge_tts.Communicate(text, voice_id)
        await communicate.save(filename)

        # Reproduz com pygame, sem travar o event loop. O lock evita conflito
        # com uma eventual prévia de voz tocando ao mesmo tempo.
        with self.playback_lock:
            volume = self.volume_value / 100.0

            pygame.mixer.music.load(filename)
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)

            # Libera o arquivo (essencial no Windows para evitar PermissionError)
            pygame.mixer.music.unload()

        try:
            os.remove(filename)
        except Exception:
            pass

    # =========================================================================
    # Prévia de voz (chamada pela janela de Configurações, em thread própria)
    # =========================================================================
    def play_voice_preview(self, callback):
        """Roda em uma thread dedicada (não a thread do bot), com seu próprio
        event loop, para nunca travar a GUI nem depender do bot estar ativo."""
        error_message = None
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self._generate_and_play_preview())
        except Exception as e:
            error_message = f"{type(e).__name__}: {e}"
        finally:
            loop.close()
            callback(error_message)

    async def _generate_and_play_preview(self):
        voice_label = self.voice_var.get()
        voice_id = VOICES.get(voice_label, "pt-BR-AntonioNeural")

        filename = os.path.join(self.temp_dir, f"preview_{uuid.uuid4().hex}.mp3")

        communicate = edge_tts.Communicate(PREVIEW_TEXT, voice_id)
        await communicate.save(filename)

        # Se o bot não estiver rodando, o mixer ainda não foi inicializado —
        # inicializamos aqui e finalizamos só se fomos nós que iniciamos.
        mixer_already_running = pygame.mixer.get_init() is not None
        if not mixer_already_running:
            pygame.mixer.init()

        try:
            with self.playback_lock:
                volume = self.volume_value / 100.0

                pygame.mixer.music.load(filename)
                pygame.mixer.music.set_volume(volume)
                pygame.mixer.music.play()

                while pygame.mixer.music.get_busy():
                    await asyncio.sleep(0.1)

                pygame.mixer.music.unload()
        finally:
            if not mixer_already_running:
                pygame.mixer.quit()
            try:
                os.remove(filename)
            except Exception:
                pass


if __name__ == "__main__":
    app = TikTokTTSApp()
    app.mainloop()
