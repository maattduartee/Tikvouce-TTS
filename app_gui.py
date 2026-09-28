"""
app_gui.py
-----------
Interface gráfica (CustomTkinter) para o bot de Text-to-Speech de lives do TikTok.

Dependências:
    pip install customtkinter TikTokLive edge-tts pygame Pillow

Arquitetura:
    - A GUI roda no thread principal (mainloop do Tkinter).
    - Todo o trabalho assíncrono (TikTokLive + edge-tts + pygame) roda em uma
      Thread separada, com seu próprio event loop asyncio, para nunca travar a GUI.
    - A comunicação Thread -> GUI é feita via queue.Queue (thread-safe), lida
      periodicamente pelo mainloop através de `self.after(...)`.
    - Comandos GUI -> Thread (como "parar") usam asyncio.run_coroutine_threadsafe.
    - A tela inicial mostra o essencial (foto/nome de quem está ao vivo, status,
      usuário e botão play); tema, voz, idioma, volume e demais opções ficam na
      janela de Configurações, com botões OK (salva) / Cancelar (descarta).
    - Configurações são persistidas em config.json ao lado do executável/script.
    - Em caso de queda de conexão não solicitada pelo usuário, o app tenta
      reconectar automaticamente algumas vezes, com espera crescente.
"""

import os
import io
import sys
import json
import time
import uuid
import queue
import asyncio
import logging
import traceback
import threading
import tempfile
import datetime
import collections

import customtkinter as ctk

import edge_tts
import pygame

from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent, CommentEvent

# Eventos de presente e novo seguidor (nem toda versão da lib expõe os dois
# com o mesmo nome, então importamos com fallback seguro).
try:
    from TikTokLive.events import GiftEvent
except ImportError:
    GiftEvent = None

try:
    from TikTokLive.events import FollowEvent
except ImportError:
    FollowEvent = None

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
APP_VERSION = "1.2.0"

# Idiomas e vozes disponíveis (nome amigável -> id da voz neural do edge-tts)
LANGUAGES: dict[str, dict[str, str]] = {
    "Português (Brasil)": {
        "Antônio (Masculino)": "pt-BR-AntonioNeural",
        "Francisca (Feminino)": "pt-BR-FranciscaNeural",
        "Thalita (Feminino)": "pt-BR-ThalitaNeural",
        "Brenda (Feminino)": "pt-BR-BrendaNeural",
        "Donato (Masculino)": "pt-BR-DonatoNeural",
        "Elza (Feminino)": "pt-BR-ElzaNeural",
        "Fábio (Masculino)": "pt-BR-FabioNeural",
        "Giovanna (Feminino)": "pt-BR-GiovannaNeural",
        "Humberto (Masculino)": "pt-BR-HumbertoNeural",
        "Júlio (Masculino)": "pt-BR-JulioNeural",
        "Leila (Feminino)": "pt-BR-LeilaNeural",
        "Letícia (Feminino)": "pt-BR-LeticiaNeural",
        "Manuela (Feminino)": "pt-BR-ManuelaNeural",
        "Nicolau (Masculino)": "pt-BR-NicolauNeural",
        "Valério (Masculino)": "pt-BR-ValerioNeural",
        "Yara (Feminino)": "pt-BR-YaraNeural",
    },
    "Português (Portugal)": {
        "Duarte (Masculino)": "pt-PT-DuarteNeural",
        "Raquel (Feminino)": "pt-PT-RaquelNeural",
    },
    "Inglês (EUA)": {
        "Guy (Masculino)": "en-US-GuyNeural",
        "Christopher (Masculino)": "en-US-ChristopherNeural",
        "Aria (Feminino)": "en-US-AriaNeural",
        "Jenny (Feminino)": "en-US-JennyNeural",
    },
    "Inglês (Reino Unido)": {
        "Ryan (Masculino)": "en-GB-RyanNeural",
        "Sonia (Feminino)": "en-GB-SoniaNeural",
    },
    "Espanhol (Espanha)": {
        "Álvaro (Masculino)": "es-ES-AlvaroNeural",
        "Elvira (Feminino)": "es-ES-ElviraNeural",
    },
    "Espanhol (México)": {
        "Jorge (Masculino)": "es-MX-JorgeNeural",
        "Dalia (Feminino)": "es-MX-DaliaNeural",
    },
    "Francês (França)": {
        "Henri (Masculino)": "fr-FR-HenriNeural",
        "Denise (Feminino)": "fr-FR-DeniseNeural",
    },
    "Italiano": {
        "Diego (Masculino)": "it-IT-DiegoNeural",
        "Elsa (Feminino)": "it-IT-ElsaNeural",
    },
    "Japonês": {
        "Keita (Masculino)": "ja-JP-KeitaNeural",
        "Nanami (Feminino)": "ja-JP-NanamiNeural",
    },
}

DEFAULT_LANGUAGE = "Português (Brasil)"
DEFAULT_VOICE = "Antônio (Masculino)"

# Textos de prévia de voz, por idioma (cai para o português se não achar)
PREVIEW_TEXTS = {
    "Português (Brasil)": "Olá! Esta é uma prévia da voz selecionada para o seu chat da live.",
    "Português (Portugal)": "Olá! Esta é uma amostra da voz escolhida para o chat da sua live.",
    "Inglês (EUA)": "Hello! This is a preview of the selected voice for your live chat.",
    "Inglês (Reino Unido)": "Hello! This is a preview of the selected voice for your live chat.",
    "Espanhol (Espanha)": "¡Hola! Esta es una vista previa de la voz seleccionada para tu chat en vivo.",
    "Espanhol (México)": "¡Hola! Esta es una vista previa de la voz seleccionada para tu chat en vivo.",
    "Francês (França)": "Bonjour ! Ceci est un aperçu de la voix sélectionnée pour votre chat en direct.",
    "Italiano": "Ciao! Questa è un'anteprima della voce selezionata per la chat dal vivo.",
    "Japonês": "こんにちは！これはライブチャット用に選択された音声のプレビューです。",
}

# Frases faladas (comentário / presente / seguidor novo), por idioma
PHRASES = {
    "Português (Brasil)": {
        "said": "{user} disse: {text}",
        "gift": "{user} mandou um presente: {gift}!",
        "follow": "{user} começou a seguir o canal!",
    },
    "Português (Portugal)": {
        "said": "{user} disse: {text}",
        "gift": "{user} enviou um presente: {gift}!",
        "follow": "{user} começou a seguir o canal!",
    },
    "Inglês (EUA)": {
        "said": "{user} said: {text}",
        "gift": "{user} sent a gift: {gift}!",
        "follow": "{user} started following the channel!",
    },
    "Inglês (Reino Unido)": {
        "said": "{user} said: {text}",
        "gift": "{user} sent a gift: {gift}!",
        "follow": "{user} started following the channel!",
    },
    "Espanhol (Espanha)": {
        "said": "{user} dijo: {text}",
        "gift": "¡{user} envió un regalo: {gift}!",
        "follow": "¡{user} empezó a seguir el canal!",
    },
    "Espanhol (México)": {
        "said": "{user} dijo: {text}",
        "gift": "¡{user} envió un regalo: {gift}!",
        "follow": "¡{user} empezó a seguir el canal!",
    },
    "Francês (França)": {
        "said": "{user} a dit : {text}",
        "gift": "{user} a envoyé un cadeau : {gift} !",
        "follow": "{user} a commencé à suivre la chaîne !",
    },
    "Italiano": {
        "said": "{user} ha detto: {text}",
        "gift": "{user} ha inviato un regalo: {gift}!",
        "follow": "{user} ha iniziato a seguire il canale!",
    },
    "Japonês": {
        "said": "{user}さんが言いました: {text}",
        "gift": "{user}さんがギフトを送りました: {gift}！",
        "follow": "{user}さんがチャンネルのフォローを開始しました！",
    },
}

# Tamanho inicial da janela principal (agora redimensionável)
WINDOW_SIZE = "550x700"
WINDOW_MIN_SIZE = (480, 540)

AVATAR_SIZE = 56

# Reconexão automática
MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_BASE_DELAY_SECONDS = 5

# Anti-flood
RECENT_MESSAGE_WINDOW_SECONDS = 8   # janela para considerar uma mensagem "repetida"
MAX_QUEUE_SIZE = 12                 # tamanho máximo da fila de fala pendente


def _get_base_dir() -> str:
    """Retorna a pasta onde salvar o config.json — funciona tanto rodando
    como script .py quanto empacotado como .exe pelo PyInstaller."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_get_base_dir(), "config.json")


class _QueueLogHandler(logging.Handler):
    """Encaminha os logs internos de bibliotecas (ex: TikTokLive) para a GUI."""

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
# Janela de Configurações
# =============================================================================
class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, app: "TikTokTTSApp"):
        super().__init__(app)
        self.app = app

        # Snapshot do estado atual, para poder reverter se o usuário cancelar.
        # OBS: "appearance_mode" não entra aqui — o tema só é aplicado depois
        # que esta janela fecha (veja _on_ok), então não há nada ao vivo para
        # reverter nesse campo.
        self._snapshot = {
            "language": self.app.language_var.get(),
            "voice": self.app.voice_var.get(),
            "volume": self.app.volume_value,
            "read_username_enabled": self.app.read_username_enabled,
            "read_username_with_at": self.app.read_username_with_at,
            "anti_flood_enabled": self.app.anti_flood_enabled,
            "announce_events_enabled": self.app.announce_events_enabled,
        }

        self.title("Configurações")
        self.geometry("440x660")
        self.resizable(False, False)
        self.transient(app)
        # OBS: propositalmente NÃO usamos grab_set() aqui. Uma janela modal
        # que mantém a captura de eventos durante uma troca de tema (que
        # redesenha todas as janelas abertas) pode ficar "presa" bloqueando
        # cliques em todo o app — inclusive o botão de fechar da janela
        # principal — mesmo se ela sumir de vista.
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        pad = 16

        ctk.CTkLabel(
            self, text="⚙️  Configurações", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(pad, 8))

        # Área rolável para caber todas as seções sem estourar a tela
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # ---------- Aparência (dark / light) ----------
        appearance_frame = ctk.CTkFrame(scroll, corner_radius=12)
        appearance_frame.pack(fill="x", padx=pad, pady=(0, 12))

        ctk.CTkLabel(appearance_frame, text="Aparência:", anchor="w").pack(
            fill="x", padx=16, pady=(14, 4)
        )

        current_mode = ctk.get_appearance_mode()  # "Dark" ou "Light"
        self.appearance_var = ctk.StringVar(
            value="Escuro" if current_mode == "Dark" else "Claro"
        )
        ctk.CTkSegmentedButton(
            appearance_frame,
            values=["Escuro", "Claro"],
            variable=self.appearance_var,
            command=self._on_appearance_change,
        ).pack(fill="x", padx=16, pady=(0, 16))

        # ---------- Idioma + Voz + prévia ----------
        voice_frame = ctk.CTkFrame(scroll, corner_radius=12)
        voice_frame.pack(fill="x", padx=pad, pady=(0, 12))

        ctk.CTkLabel(voice_frame, text="Idioma:", anchor="w").pack(
            fill="x", padx=16, pady=(14, 4)
        )
        self.language_menu = ctk.CTkOptionMenu(
            voice_frame,
            values=list(LANGUAGES.keys()),
            variable=self.app.language_var,
            command=self._on_language_change,
        )
        self.language_menu.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(voice_frame, text="Voz:", anchor="w").pack(
            fill="x", padx=16, pady=(0, 4)
        )
        self.voice_menu = ctk.CTkOptionMenu(
            voice_frame,
            values=list(LANGUAGES[self.app.language_var.get()].keys()),
            variable=self.app.voice_var,
            command=self._on_voice_change,
        )
        self.voice_menu.pack(fill="x", padx=16, pady=(0, 12))

        self.preview_button = ctk.CTkButton(
            voice_frame, text="🔊  Testar voz", command=self._preview_voice
        )
        self.preview_button.pack(fill="x", padx=16, pady=(0, 16))

        # ---------- Volume ----------
        volume_frame = ctk.CTkFrame(scroll, corner_radius=12)
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

        # ---------- Leitura do nome de quem enviou a mensagem ----------
        username_read_frame = ctk.CTkFrame(scroll, corner_radius=12)
        username_read_frame.pack(fill="x", padx=pad, pady=(0, 12))

        self.username_enabled_var = ctk.BooleanVar(value=self.app.read_username_enabled)
        ctk.CTkSwitch(
            username_read_frame,
            text="Falar nome de quem comentou",
            variable=self.username_enabled_var,
            onvalue=True,
            offvalue=False,
            command=self._on_username_read_toggle_change,
        ).pack(fill="x", padx=16, pady=(14, 8))

        self.username_format_var = ctk.StringVar(
            value="Com @" if self.app.read_username_with_at else "Sem @"
        )
        self.username_format_switcher = ctk.CTkSegmentedButton(
            username_read_frame,
            values=["Com @", "Sem @"],
            variable=self.username_format_var,
            command=self._on_username_format_change,
            state="normal" if self.app.read_username_enabled else "disabled",
        )
        self.username_format_switcher.pack(fill="x", padx=16, pady=(0, 4))

        ctk.CTkLabel(
            username_read_frame,
            text='Ex.: "@fulano disse: sua mensagem" ou "fulano disse: sua mensagem". '
                 'Desligado, o bot lê só a mensagem, sem citar quem comentou.',
            font=ctk.CTkFont(size=11),
            text_color="gray50",
            anchor="w",
            wraplength=380,
        ).pack(fill="x", padx=16, pady=(0, 14))

        # ---------- Anti-flood ----------
        antiflood_frame = ctk.CTkFrame(scroll, corner_radius=12)
        antiflood_frame.pack(fill="x", padx=pad, pady=(0, 12))

        self.antiflood_var = ctk.BooleanVar(value=self.app.anti_flood_enabled)
        ctk.CTkSwitch(
            antiflood_frame,
            text="Filtro anti-flood (ignora repetições recentes)",
            variable=self.antiflood_var,
            onvalue=True,
            offvalue=False,
            command=self._on_antiflood_change,
        ).pack(fill="x", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            antiflood_frame,
            text="Evita ler a mesma mensagem várias vezes e mantém a fila "
                 "curta num chat muito ativo.",
            font=ctk.CTkFont(size=11),
            text_color="gray50",
            anchor="w",
            wraplength=380,
        ).pack(fill="x", padx=16, pady=(0, 14))

        # ---------- Presentes / seguidores ----------
        events_frame = ctk.CTkFrame(scroll, corner_radius=12)
        events_frame.pack(fill="x", padx=pad, pady=(0, 12))

        self.events_var = ctk.BooleanVar(value=self.app.announce_events_enabled)
        ctk.CTkSwitch(
            events_frame,
            text="Anunciar presentes e novos seguidores",
            variable=self.events_var,
            onvalue=True,
            offvalue=False,
            command=self._on_events_change,
        ).pack(fill="x", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            events_frame,
            text="Aplica-se na próxima vez que clicar em Iniciar.",
            font=ctk.CTkFont(size=11),
            text_color="gray50",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 14))

        # ---------- Versão ----------
        ctk.CTkLabel(
            self,
            text=f"{APP_NAME} v{APP_VERSION}",
            font=ctk.CTkFont(size=11),
            text_color="gray50",
        ).pack(pady=(4, 2))

        # ---------- OK / Cancelar ----------
        button_row = ctk.CTkFrame(self, fg_color="transparent")
        button_row.pack(fill="x", padx=pad, pady=(4, pad))
        button_row.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            button_row,
            text="Cancelar",
            fg_color="gray30",
            hover_color="gray20",
            command=self._on_cancel,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            button_row,
            text="OK",
            fg_color="#2fa572",
            hover_color="#248a5d",
            command=self._on_ok,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    # -- Mudanças ao vivo (prévia imediata, só persistem se clicar OK) -------
    def _on_appearance_change(self, value):
        # Propositalmente NÃO chamamos ctk.set_appearance_mode() aqui.
        # Trocar o tema enquanto esta janela ainda está aberta é o que
        # causava o bug de a própria janela de Configurações fechar sozinha
        # (o redesenho global do CustomTkinter mexe em todas as janelas
        # abertas, incluindo esta). O tema só é aplicado de fato em _on_ok,
        # já depois desta janela ter sido destruída.
        pass

    def _on_language_change(self, value):
        voices_for_lang = list(LANGUAGES.get(value, {}).keys())
        self.voice_menu.configure(values=voices_for_lang)
        if voices_for_lang:
            self.app.voice_var.set(voices_for_lang[0])

    def _on_voice_change(self, value):
        pass  # voice_var já foi atualizado pela própria variable=

    def _on_username_read_toggle_change(self):
        enabled = self.username_enabled_var.get()
        self.app.read_username_enabled = enabled
        self.username_format_switcher.configure(
            state="normal" if enabled else "disabled"
        )

    def _on_username_format_change(self, value):
        self.app.read_username_with_at = value == "Com @"

    def _on_antiflood_change(self):
        self.app.anti_flood_enabled = self.antiflood_var.get()

    def _on_events_change(self):
        self.app.announce_events_enabled = self.events_var.get()

    # -- OK / Cancelar --------------------------------------------------------
    def _on_ok(self):
        chosen_mode = "dark" if self.appearance_var.get() == "Escuro" else "light"
        self.app.settings_window = None
        self.destroy()
        # O tema só é aplicado (e tudo salvo) depois desta janela já ter
        # sido destruída, com um pequeno atraso para garantir que o Tkinter
        # processou o fechamento antes do redesenho global do tema.
        self.app.after(50, lambda: self.app.apply_appearance_mode_and_save(chosen_mode))

    def _on_cancel(self):
        snap = self._snapshot
        self.app.language_var.set(snap["language"])
        self.app.voice_var.set(snap["voice"])
        self.app.volume_value = snap["volume"]
        self.app.read_username_enabled = snap["read_username_enabled"]
        self.app.read_username_with_at = snap["read_username_with_at"]
        self.app.anti_flood_enabled = snap["anti_flood_enabled"]
        self.app.announce_events_enabled = snap["announce_events_enabled"]

        self.app.settings_window = None
        self.destroy()

    # -- Prévia de voz ---------------------------------------------------------
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

        # Carrega configurações salvas (se existirem) antes de montar a UI,
        # para já abrir com as últimas escolhas do usuário.
        saved_config = self._load_config()

        saved_appearance = saved_config.get("appearance_mode")
        if saved_appearance in ("Dark", "Light"):
            ctk.set_appearance_mode(saved_appearance.lower())

        self.title(f"{APP_NAME} v{APP_VERSION} • TikTok Live TTS")
        self.geometry(WINDOW_SIZE)
        self.minsize(*WINDOW_MIN_SIZE)
        self.resizable(True, True)

        # --- Estado interno -------------------------------------------------
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.client: TikTokLiveClient | None = None
        self.running = False
        # True quando o próprio usuário pediu para parar — usado para não
        # tentar reconectar automaticamente nesse caso.
        self.manual_stop = False
        self.log_visible = True

        self.volume_value = float(saved_config.get("volume", 80.0))

        saved_language = saved_config.get("language")
        default_language = saved_language if saved_language in LANGUAGES else DEFAULT_LANGUAGE
        self.language_var = ctk.StringVar(value=default_language)

        voices_for_language = list(LANGUAGES[default_language].keys())
        saved_voice = saved_config.get("voice")
        default_voice = saved_voice if saved_voice in voices_for_language else voices_for_language[0]
        self.voice_var = ctk.StringVar(value=default_voice)

        self.read_username_enabled = bool(saved_config.get("read_username_enabled", True))
        self.read_username_with_at = bool(saved_config.get("read_username_with_at", True))
        self.anti_flood_enabled = bool(saved_config.get("anti_flood_enabled", True))
        self.announce_events_enabled = bool(saved_config.get("announce_events_enabled", True))
        self.settings_window: SettingsWindow | None = None

        self._saved_username = saved_config.get("username", "controlee2")
        self._current_avatar_image = None  # mantém referência viva (evita GC)

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
    # Configurações persistentes (config.json)
    # =========================================================================
    def _load_config(self) -> dict:
        if not os.path.exists(CONFIG_PATH):
            return {}
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_config(self):
        config = {
            "username": (
                self.username_entry.get().strip()
                if hasattr(self, "username_entry")
                else self._saved_username
            ),
            "language": self.language_var.get(),
            "voice": self.voice_var.get(),
            "volume": self.volume_value,
            "appearance_mode": ctk.get_appearance_mode(),
            "read_username_enabled": self.read_username_enabled,
            "read_username_with_at": self.read_username_with_at,
            "anti_flood_enabled": self.anti_flood_enabled,
            "announce_events_enabled": self.announce_events_enabled,
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"⚠️ Não foi possível salvar as configurações: {e}")

    def apply_appearance_mode_and_save(self, mode: str):
        """Aplica o tema (chamado só depois que a janela de Configurações já
        foi destruída, para evitar o bug do CustomTkinter que fechava a
        própria janela de Configurações ao trocar de tema com ela aberta)."""
        try:
            ctk.set_appearance_mode(mode)
        except Exception as e:
            self.log(f"⚠️ Erro ao trocar tema: {e}")
        self.save_config()

    def get_current_voice_id(self) -> str:
        lang_voices = LANGUAGES.get(self.language_var.get(), {})
        return lang_voices.get(self.voice_var.get(), "pt-BR-AntonioNeural")

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
        self.username_entry.insert(0, self._saved_username)
        self.username_entry.pack(fill="x", padx=16, pady=(0, 14))

        # ---------- Cartão de perfil (foto + nome + status) ----------
        center_frame = ctk.CTkFrame(self, fg_color="transparent")
        center_frame.pack(fill="both", expand=True)

        profile_card = ctk.CTkFrame(center_frame, corner_radius=16)
        profile_card.pack(fill="x", padx=pad, pady=(24, 20))
        profile_card.grid_columnconfigure(1, weight=1)

        self.avatar_label = ctk.CTkLabel(
            profile_card,
            text="👤",
            width=AVATAR_SIZE,
            height=AVATAR_SIZE,
            corner_radius=AVATAR_SIZE // 2,
            fg_color=("gray80", "gray25"),
            font=ctk.CTkFont(size=24),
        )
        self.avatar_label.grid(row=0, column=0, rowspan=2, padx=16, pady=16)

        self.profile_name_label = ctk.CTkLabel(
            profile_card,
            text="Nenhuma conexão ativa",
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
            justify="left",
        )
        self.profile_name_label.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=(16, 0))

        self.status_label = ctk.CTkLabel(
            profile_card,
            text="● Parado",
            text_color="gray60",
            font=ctk.CTkFont(size=13),
            anchor="w",
        )
        self.status_label.grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=(0, 16))

        # ---------- Botão Play grande ----------
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
        self.play_button.pack(pady=(0, 16))

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
            self._reset_profile_display()

    def _reset_profile_display(self):
        self._current_avatar_image = None
        self.avatar_label.configure(image=None, text="👤")
        self.profile_name_label.configure(text="Nenhuma conexão ativa")

    def _set_profile_photo(self, photo):
        self._current_avatar_image = photo  # mantém referência viva
        self.avatar_label.configure(image=photo, text="")

    def _bytes_to_circular_ctk_image(self, image_bytes: bytes, size: int = AVATAR_SIZE):
        try:
            from PIL import Image, ImageDraw

            img = Image.open(io.BytesIO(image_bytes)).convert("RGBA").resize((size, size))
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
            img.putalpha(mask)
            return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
        except Exception as e:
            self.log(f"ℹ️ Não foi possível processar a foto de perfil: {e}")
            return None

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

        self.manual_stop = False
        self._reset_profile_display()
        self._set_running_state(True)
        self.log(f"Iniciando conexão com @{username.lstrip('@')}...")
        self.save_config()

        self.worker_thread = threading.Thread(
            target=self._thread_main, args=(username,), daemon=True
        )
        self.worker_thread.start()

    def stop_bot(self):
        if not self.running:
            return

        self.manual_stop = True
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
        self.save_config()
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
        self._recent_spoken = collections.deque(maxlen=50)

        tts_task = asyncio.create_task(self._tts_worker())

        attempt = 0

        def register_events(client: TikTokLiveClient):
            @client.on(ConnectEvent)
            async def on_connect(event: ConnectEvent):
                nonlocal attempt
                attempt = 0  # reseta o contador após uma conexão bem-sucedida
                self.log(f"✅ Conectado à live de {tiktok_username}!")
                self.after(0, lambda: self.status_label.configure(
                    text="● Conectado", text_color="#2fa572"
                ))

                try:
                    nickname = getattr(event.user, "nickname", None)
                    handle = getattr(event.user, "unique_id", None) or tiktok_username.lstrip("@")
                    if nickname and nickname.lower() != handle.lower():
                        display_name = f"{nickname} (@{handle})"
                    else:
                        display_name = f"@{handle}"
                    self.after(0, lambda: self.profile_name_label.configure(text=display_name))
                except Exception:
                    pass

                try:
                    avatar = getattr(event.user, "avatar_thumb", None)
                    if avatar is not None:
                        image_bytes = await client.web.fetch_image_data(image=avatar)
                        photo = self._bytes_to_circular_ctk_image(image_bytes)
                        if photo is not None:
                            self.after(0, lambda p=photo: self._set_profile_photo(p))
                except Exception as e:
                    self.log(f"ℹ️ Não foi possível carregar a foto de perfil: {e}")

            @client.on(DisconnectEvent)
            async def on_disconnect(event: DisconnectEvent):
                self.log("🔌 Desconectado da live.")

            @client.on(CommentEvent)
            async def on_comment(event: CommentEvent):
                try:
                    user = event.user.nickname or event.user.unique_id
                except Exception:
                    user = "Usuário"
                text = getattr(event, "comment", "") or ""

                if not text.strip():
                    return

                self.log(f"[{user}]: {text}")

                if self.read_username_enabled:
                    phrases = PHRASES.get(self.language_var.get(), PHRASES[DEFAULT_LANGUAGE])
                    prefix = "@" if self.read_username_with_at else ""
                    spoken_text = phrases["said"].format(user=f"{prefix}{user}", text=text)
                else:
                    spoken_text = text
                await self._enqueue_spoken(spoken_text)

            if self.announce_events_enabled and GiftEvent is not None:
                @client.on(GiftEvent)
                async def on_gift(event):
                    try:
                        user = event.user.nickname or event.user.unique_id
                    except Exception:
                        user = "Usuário"
                    try:
                        gift_name = event.gift.name
                    except Exception:
                        gift_name = "um presente"
                    # Presentes "combo" disparam vários eventos seguidos —
                    # só anuncia quando o combo termina, pra não repetir.
                    try:
                        is_streakable = getattr(event.gift, "streakable", False)
                        combo_ended = getattr(event, "repeat_end", True)
                        if is_streakable and not combo_ended:
                            return
                    except Exception:
                        pass
                    self.log(f"🎁 {user} enviou: {gift_name}")
                    phrases = PHRASES.get(self.language_var.get(), PHRASES[DEFAULT_LANGUAGE])
                    await self._enqueue_spoken(phrases["gift"].format(user=user, gift=gift_name))

            if self.announce_events_enabled and FollowEvent is not None:
                @client.on(FollowEvent)
                async def on_follow(event):
                    try:
                        user = event.user.nickname or event.user.unique_id
                    except Exception:
                        user = "Usuário"
                    self.log(f"➕ {user} começou a seguir!")
                    phrases = PHRASES.get(self.language_var.get(), PHRASES[DEFAULT_LANGUAGE])
                    await self._enqueue_spoken(phrases["follow"].format(user=user))

        try:
            while True:
                if self.manual_stop:
                    break

                try:
                    self.client = TikTokLiveClient(unique_id=tiktok_username)
                except Exception as e:
                    self.log(f"❌ Não foi possível criar o cliente ({type(e).__name__}): {e}")
                    self.log("Detalhes técnicos:\n" + traceback.format_exc())
                    break

                register_events(self.client)

                should_retry = False

                try:
                    # IMPORTANTE: start() NÃO bloqueia — ele apenas dispara a
                    # conexão em uma Task e retorna imediatamente. connect()
                    # é o método correto aqui, pois ele aguarda (bloqueia)
                    # até a live encerrar ou a conexão cair.
                    await self.client.connect()
                    self.log("ℹ️ A conexão com a live foi encerrada.")
                    should_retry = True  # queda inesperada -> vale tentar de novo
                except UserOfflineError:
                    self.log(
                        f"⚠️ @{tiktok_username.lstrip('@')} está offline no momento "
                        f"(a pessoa não está fazendo live agora)."
                    )
                    should_retry = False
                except UserNotFoundError:
                    self.log(
                        f"⚠️ Usuário @{tiktok_username.lstrip('@')} não foi encontrado. "
                        f"Verifique se o nome de usuário está correto."
                    )
                    should_retry = False
                except AlreadyConnectedError:
                    self.log("⚠️ Já existe uma conexão ativa com essa live.")
                    should_retry = True
                except SignAPIError as e:
                    self.log(
                        f"⚠️ Erro no servidor de assinatura (Sign API) da TikTokLive: {e}\n"
                        f"Isso geralmente significa limite de requisições atingido (rate limit)."
                    )
                    should_retry = True
                except Exception as e:
                    self.log(f"❌ Falha na conexão ({type(e).__name__}): {e}")
                    self.log("Detalhes técnicos:\n" + traceback.format_exc())
                    should_retry = True

                if self.manual_stop or not should_retry:
                    break

                attempt += 1
                if attempt > MAX_RECONNECT_ATTEMPTS:
                    self.log(
                        f"❌ Número máximo de tentativas de reconexão "
                        f"({MAX_RECONNECT_ATTEMPTS}) atingido. Desistindo."
                    )
                    break

                delay = RECONNECT_BASE_DELAY_SECONDS * attempt
                self.log(
                    f"🔄 Tentando reconectar em {delay}s "
                    f"(tentativa {attempt}/{MAX_RECONNECT_ATTEMPTS})..."
                )
                self.after(0, lambda: self.status_label.configure(
                    text="● Reconectando...", text_color="#f1c40f"
                ))

                # Espera em passos de 1s para responder rápido a um "Parar"
                # clicado pelo usuário durante a contagem regressiva.
                for _ in range(delay):
                    if self.manual_stop:
                        break
                    await asyncio.sleep(1)
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

    async def _enqueue_spoken(self, spoken_text: str):
        """Adiciona um texto à fila de fala, aplicando o filtro anti-flood
        (mensagens repetidas recentemente) e o limite de tamanho da fila."""
        if self.anti_flood_enabled:
            now = time.monotonic()
            normalized = spoken_text.strip().lower()

            while self._recent_spoken and now - self._recent_spoken[0][0] > RECENT_MESSAGE_WINDOW_SECONDS:
                self._recent_spoken.popleft()

            if any(t == normalized for _, t in self._recent_spoken):
                return  # mensagem repetida recentemente -> ignora

            self._recent_spoken.append((now, normalized))

        # Evita que a fila cresça demais num chat muito ativo: descarta as
        # mensagens mais antigas para priorizar as mais recentes.
        while self.tts_queue.qsize() >= MAX_QUEUE_SIZE:
            try:
                self.tts_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        await self.tts_queue.put(spoken_text)

    async def _tts_worker(self):
        """Consome a fila de textos e lê cada um em voz alta, um por vez."""
        while True:
            try:
                spoken_text = await self.tts_queue.get()
            except asyncio.CancelledError:
                break

            try:
                await self._speak(spoken_text)
            except Exception as e:
                self.log(f"⚠️ Erro ao gerar/reproduzir áudio ({type(e).__name__}): {e}")
                self.log("Detalhes técnicos:\n" + traceback.format_exc())

    async def _speak(self, spoken_text: str):
        voice_id = self.get_current_voice_id()

        filename = os.path.join(self.temp_dir, f"tts_{uuid.uuid4().hex}.mp3")

        # Gera o áudio com edge-tts
        communicate = edge_tts.Communicate(spoken_text, voice_id)
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
        voice_id = self.get_current_voice_id()
        preview_text = PREVIEW_TEXTS.get(self.language_var.get(), PREVIEW_TEXTS[DEFAULT_LANGUAGE])

        filename = os.path.join(self.temp_dir, f"preview_{uuid.uuid4().hex}.mp3")

        communicate = edge_tts.Communicate(preview_text, voice_id)
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
