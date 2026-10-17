
# Traductor de Código Morse: Traduce de Texto a Código Morse y viceversa
# Reproduce el código morse generado y escucha transmisiones para detectar código morse
# Autor quicastillo@gmail.com  EA4IVW 


# morse_gui.py
import sys
import re
import unicodedata

from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QTimer, QBuffer, QByteArray
from PyQt5.QtGui import QIcon, QTextCursor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QRadioButton, QButtonGroup, QLabel, QFileDialog, QMessageBox, QCheckBox,
    QGroupBox, QSlider
)

# ─────────────────────────────────────────────────────────────────────────────
# Clase personalizada para capturar ENTER en la entrada
# ─────────────────────────────────────────────────────────────────────────────
class EntradaTexto(QTextEdit):
    enter_pressed = QtCore.pyqtSignal()

    def keyPressEvent(self, event):
        # Dejamos que el widget haga el salto de línea normal
        super().keyPressEvent(event)
        # Luego avisamos a la GUI para reflejarlo en la salida
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.enter_pressed.emit()


# ─────────────────────────────────────────────────────────────────────────────
# Intentar cargar equivalencias desde codmorse.py
# ─────────────────────────────────────────────────────────────────────────────
try:
    from codmorse import MORSE as _MORSE
    try:
        from codmorse import MORSE_INV as _MORSE_INV
    except Exception:
        _MORSE_INV = {v: k for k, v in _MORSE.items()}
except Exception as e:
    _MORSE, _MORSE_INV = None, None
    _IMPORT_ERROR = e
else:
    _IMPORT_ERROR = None

# Módulo receptor (escucha de audio). Si falla, la aplicación sigue funcionando sin él.
try:
    from morse_receptor import ReceptorMorse
    _RECEPTOR_ERROR = None
except Exception as e:
    ReceptorMorse = None
    _RECEPTOR_ERROR = e


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades de traducción (ahora preservan saltos de línea)
# ─────────────────────────────────────────────────────────────────────────────
def normalize_text(s: str) -> str:
    """
    Normaliza el texto a ASCII básico: elimina tildes (á→a, ü→u, ñ→n, etc.).
    """
    normalized = unicodedata.normalize('NFD', s)
    without_marks = ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')
    return without_marks


def _texto_linea_a_morse(linea: str, MORSE: dict) -> str:
    """
    Convierte una línea de texto a una línea de morse.
    Espacios ' ' o '\t' → '/', otros caracteres no mapeados → '?'.
    (No maneja '\n' aquí; eso se hace fuera a nivel de líneas)
    """
    res = []
    for ch in linea.upper():
        if ch in MORSE:
            res.append(MORSE[ch])
        elif ch in (' ', '\t'):
            res.append('/')
        else:
            res.append('?')
    out = ' '.join(res)
    # Colapsa separadores repetidos y espacios extra dentro de la línea
    out = re.sub(r'(?:\s*/\s*){2,}', ' / ', out)
    out = re.sub(r'\s{2,}', ' ', out).strip()
    return out


def texto_a_morse(texto: str, MORSE: dict, normalizar: bool = True) -> str:
    """
    Convierte texto a morse preservando saltos de línea.
    Cada línea de entrada produce una línea en la salida.
    """
    if normalizar:
        texto = normalize_text(texto)

    # Preservar el número de líneas (incluye líneas vacías)
    lineas = texto.split('\n')
    morse_lineas = [_texto_linea_a_morse(l, MORSE) for l in lineas]
    return '\n'.join(morse_lineas)


def _morse_linea_a_texto(morse_line: str, MORSE_INV: dict) -> str:
    """
    Convierte una línea de morse a una línea de texto.
    Usa '/' o '|' como separador de palabra.
    """
    morse_line = morse_line.strip()
    if not morse_line:
        return ''
    # triples o más espacios como separador de palabra → '/'
    morse_line = re.sub(r'\s{3,}', ' / ', morse_line)
    tokens = morse_line.split()
    letras = []
    for tok in tokens:
        if tok in ('/', '|'):
            letras.append(' ')
        elif tok in MORSE_INV:
            letras.append(MORSE_INV[tok])
        else:
            letras.append('?')
    texto = ''.join(letras)
    texto = re.sub(r'\s{2,}', ' ', texto).strip()
    return texto


def morse_a_texto(morse: str, MORSE_INV: dict) -> str:
    """
    Convierte morse a texto preservando saltos de línea.
    """
    lineas = morse.split('\n')
    texto_lineas = [_morse_linea_a_texto(l, MORSE_INV) for l in lineas]
    return '\n'.join(texto_lineas)


# ─────────────────────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────────────────────
class MorseGUI(QWidget):
    def __init__(self):
        super().__init__()

        # Si falló la importación, avisamos pero NO cerramos la app.
        self.MORSE = _MORSE or {}
        self.MORSE_INV = _MORSE_INV or {}

        self.setWindowTitle("Traductor Código Morse ⇄ Texto")
        self.setMinimumSize(780, 680)
        try:
            self.setWindowIcon(QIcon.fromTheme("applications-education"))
        except Exception:
            pass

        self._build_ui()

        if _IMPORT_ERROR is not None:
            QMessageBox.warning(
                self,
                "Advertencia",
                f"No se pudo importar 'codmorse.py'. La traducción/sonido puede estar deshabilitada.\n\n"
                f"Detalles: {str(_IMPORT_ERROR)}"
            )
            # Deshabilitar funciones dependientes
            self.btn_traducir.setEnabled(False)
            self.btn_beep.setEnabled(False)
            self.lbl_hint.setText("Copia 'codmorse.py' en esta carpeta para habilitar la traducción.")

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Modo de traducción ───────────────────────────────────────────────
        mode_box = QGroupBox("Modo de traducción")
        mode_layout = QHBoxLayout(mode_box)
        self.rb_texto_a_morse = QRadioButton("Texto → Morse")
        self.rb_morse_a_texto = QRadioButton("Morse → Texto")
        self.rb_texto_a_morse.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.rb_texto_a_morse, 1)
        self.mode_group.addButton(self.rb_morse_a_texto, 2)
        mode_layout.addWidget(self.rb_texto_a_morse)
        mode_layout.addWidget(self.rb_morse_a_texto)
        mode_layout.addStretch()
        layout.addWidget(mode_box)

        # ── Opciones ─────────────────────────────────────────────────────────
        opts_box = QGroupBox("Opciones")
        opts_layout = QHBoxLayout(opts_box)
        self.chk_normalizar = QCheckBox("Normalizar acentos (á→a, ñ→n)")
        self.chk_normalizar.setChecked(True)
        self.chk_auto = QCheckBox("Traducir al escribir")
        self.chk_auto.setChecked(False)
        self.lbl_hint = QLabel("Consejo: cada ENTER en la entrada crea una nueva línea en la salida.")
        self.lbl_hint.setStyleSheet("color: #666;")
        opts_layout.addWidget(self.chk_normalizar)
        opts_layout.addWidget(self.chk_auto)
        opts_layout.addStretch()
        opts_layout.addWidget(self.lbl_hint)
        layout.addWidget(opts_box)

        # ── Áreas de texto ───────────────────────────────────────────────────
        self.txt_entrada = EntradaTexto()
        self.txt_entrada.setPlaceholderText("Escribe aquí el texto o el código Morse…")
        self.txt_salida = QTextEdit()
        self.txt_salida.setPlaceholderText("Resultado…")
        self.txt_salida.setReadOnly(True)

        edits = QHBoxLayout()
        edits.addWidget(self.txt_entrada, 1)
        edits.addWidget(self.txt_salida, 1)
        layout.addLayout(edits)

        # Conectar ENTER para reflejar salto de línea en la salida
        self.txt_entrada.enter_pressed.connect(self._entrada_newline)

        # ── Botones ──────────────────────────────────────────────────────────
        btns_top = QHBoxLayout()
        self.btn_traducir = QPushButton("Traducir")
        self.btn_intercambiar = QPushButton("Intercambiar ⇄")
        self.btn_limpiar = QPushButton("Limpiar")
        btns_top.addWidget(self.btn_traducir)
        btns_top.addWidget(self.btn_intercambiar)
        btns_top.addWidget(self.btn_limpiar)
        btns_top.addStretch()

        btns_bottom = QHBoxLayout()
        self.btn_pegar = QPushButton("Pegar en entrada")
        self.btn_copiar = QPushButton("Copiar resultado")
        self.btn_abrir = QPushButton("Abrir…")
        self.btn_guardar = QPushButton("Guardar resultado…")
        btns_bottom.addWidget(self.btn_pegar)
        btns_bottom.addWidget(self.btn_copiar)
        btns_bottom.addStretch()
        btns_bottom.addWidget(self.btn_abrir)
        btns_bottom.addWidget(self.btn_guardar)

        layout.addLayout(btns_top)
        layout.addLayout(btns_bottom)

        # ── Conexiones ───────────────────────────────────────────────────────
        self.btn_traducir.clicked.connect(self.translate_now)
        self.btn_limpiar.clicked.connect(self.clear_all)
        self.btn_intercambiar.clicked.connect(self.swap_mode_and_text)
        self.btn_copiar.clicked.connect(self.copy_output)
        self.btn_pegar.clicked.connect(self.paste_input)
        self.btn_abrir.clicked.connect(self.open_file)
        self.btn_guardar.clicked.connect(self.save_result)
        self.txt_entrada.textChanged.connect(self._maybe_autotranslate)

        # --- Estado del beeper ---
        self.audio_output = None
        self._beep_buffer = None
        self._beep_bytes = None
        self._beep_playing = False

        # ============================================================
        #      EMISOR DE MORSE (BEEPER)
        # ============================================================
        box_beep = QGroupBox("Emisor Morse")
        lay_beep = QHBoxLayout(box_beep)

        self.btn_beep = QPushButton("▶ Reproducir Morse")
        lay_beep.addWidget(self.btn_beep)

        lay_beep.addSpacing(20)
        lay_beep.addWidget(QLabel("Volumen:"))
        self.slider_vol = QSlider(Qt.Horizontal)
        self.slider_vol.setRange(1, 100)
        self.slider_vol.setValue(50)
        lay_beep.addWidget(self.slider_vol)

        layout.addWidget(box_beep)

        # conexión del botón
        self.btn_beep.clicked.connect(self.send_beep)

        # ============================================================
        #      RECEPTOR DE MORSE (ESCUCHA DE UNA TRANSMISIÓN)
        # ============================================================
        self.receptor = None
        if ReceptorMorse is not None:
            self.receptor = ReceptorMorse(antes_de_escuchar=self._antes_de_escuchar)
            self.receptor.morse_decodificado.connect(self._recibir_morse)
            self.receptor.bloque_decodificado.connect(self._recibir_bloque)
            layout.addWidget(self.receptor)
        else:
            lbl = QLabel(f"Receptor de Morse no disponible: {_RECEPTOR_ERROR}")
            lbl.setStyleSheet("color: #a00;")
            layout.addWidget(lbl)

    # ────────────────────────────────────────────────────────────────────────
    # Acciones
    # ────────────────────────────────────────────────────────────────────────
    def current_mode(self) -> str:
        return "T2M" if self.rb_texto_a_morse.isChecked() else "M2T"

    def translate_now(self):
        if not self.MORSE or not self.MORSE_INV:
            QMessageBox.critical(
                self,
                "Sin equivalencias",
                "No se han podido cargar las equivalencias desde 'codmorse.py'."
            )
            return

        src = self.txt_entrada.toPlainText()
        if not src:
            self.txt_salida.clear()
            return

        if self.current_mode() == "T2M":
            out = texto_a_morse(src, self.MORSE,
                                normalizar=self.chk_normalizar.isChecked())
        else:
            out = morse_a_texto(src, self.MORSE_INV)
        self.txt_salida.setPlainText(out)

    def _maybe_autotranslate(self):
        if self.chk_auto.isChecked():
            self.translate_now()

    def _entrada_newline(self):
        """
        Cuando el usuario presiona ENTER en la entrada,
        reflejamos también una nueva línea en la salida.
        - Si autotraducción está activa: re-traducimos (preserva líneas).
        - Si no: añadimos únicamente un '\n' para mantener estructura.
        """
        if self.chk_auto.isChecked():
            self.translate_now()
        else:
            self.txt_salida.setPlainText(self.txt_salida.toPlainText() + '\n')

    def clear_all(self):
        self.txt_entrada.clear()
        self.txt_salida.clear()

    def swap_mode_and_text(self):
        # Cambia el modo
        if self.current_mode() == "T2M":
            self.rb_morse_a_texto.setChecked(True)
        else:
            self.rb_texto_a_morse.setChecked(True)
        # Intercambia contenidos
        entrada = self.txt_entrada.toPlainText()
        salida = self.txt_salida.toPlainText()
        self.txt_entrada.setPlainText(salida)
        self.txt_salida.setPlainText(entrada)
        # Lanza traducción si corresponde
        self._maybe_autotranslate()

    def copy_output(self):
        QApplication.clipboard().setText(self.txt_salida.toPlainText())

    def paste_input(self):
        self.txt_entrada.paste()

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir archivo de entrada", "", "Texto (*.txt);;Todos (*.*)"
        )
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.txt_entrada.setPlainText(f.read())
        except Exception as e:
            QMessageBox.warning(self, "No se pudo abrir", str(e))

    def save_result(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar resultado", "resultado.txt", "Texto (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.txt_salida.toPlainText())
        except Exception as e:
            QMessageBox.warning(self, "No se pudo guardar", str(e))

    # ============================================================
    #      RECEPTOR MORSE (el código detectado aparece en la ventana de entrada)
    # ============================================================
    def _antes_de_escuchar(self) -> bool:
        """
        Prepara la ventana de entrada para recibir código Morse.
        Devuelve False si el usuario cancela.
        """
        if self.current_mode() == "T2M" and self.txt_entrada.toPlainText().strip():
            r = QMessageBox.question(
                self, "Receptor Morse",
                "La ventana de entrada contiene texto.\n\n"
                "¿Borrarla para recibir el código Morse?\n"
                "(Si pulsas «No», el código se añadirá al final.)",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )
            if r == QMessageBox.Cancel:
                return False
            if r == QMessageBox.Yes:
                self.txt_entrada.clear()
                self.txt_salida.clear()
        self.rb_morse_a_texto.setChecked(True)
        return True

    def _recibir_morse(self, texto: str):
        """Añade al final de la entrada el código Morse detectado en directo."""
        if self.current_mode() != "M2T":
            self.rb_morse_a_texto.setChecked(True)
        self.txt_entrada.moveCursor(QTextCursor.End)
        self.txt_entrada.insertPlainText(texto)   # con «Traducir al escribir» se traduce solo
        self.txt_entrada.moveCursor(QTextCursor.End)

    def _recibir_bloque(self, texto: str):
        """Añade el resultado del análisis de un archivo WAV (en una línea nueva)."""
        actual = self.txt_entrada.toPlainText()
        if actual and not actual.endswith("\n"):
            texto = "\n" + texto
        self._recibir_morse(texto)

    def closeEvent(self, event):
        if getattr(self, "receptor", None) is not None:
            self.receptor.detener()
        super().closeEvent(event)

    # ============================================================
    #      EMISOR MORSE (SEGURO, MULTI-REPRODUCCIÓN)
    # ============================================================
    def send_beep(self):
        """
        Reproduce el contenido actual en código Morse como audio PCM.
        Si estás en modo Texto→Morse, convierte primero.
        """
        # Importes locales para no romper si QtMultimedia no está disponible
        try:
            from PyQt5.QtMultimedia import QAudioOutput, QAudioFormat, QAudioDeviceInfo, QAudio
        except Exception as e:
            QMessageBox.warning(
                self, "Audio no disponible",
                f"No se pudo cargar QtMultimedia.\n\nDetalles: {e}"
            )
            return

        import array, math

        if getattr(self, "_beep_playing", False):
            self._beep_cleanup()

        morse = self.txt_entrada.toPlainText()
        if not morse.strip():
            return

        if self.current_mode() == "T2M":
            if not self.MORSE:
                QMessageBox.warning(self, "Sin equivalencias", "No hay mapa MORSE cargado.")
                return
            morse = texto_a_morse(
                morse,
                self.MORSE,
                normalizar=self.chk_normalizar.isChecked()
            )

        # Duraciones (ms)
        dot_ms = 120
        dash_ms = 3 * dot_ms
        intra_gap = dot_ms
        letter_gap = 3 * dot_ms
        word_gap = 7 * dot_ms

        # Parámetros de tono
        freq = 700.0
        vol = self.slider_vol.value() / 100.0

        # Formato PCM
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleSize(16)
        fmt.setCodec("audio/pcm")
        fmt.setByteOrder(QAudioFormat.LittleEndian)
        fmt.setSampleType(QAudioFormat.SignedInt)

        dev = QAudioDeviceInfo.defaultOutputDevice()
        if not dev.isFormatSupported(fmt):
            fmt = dev.nearestFormat(fmt)

        sr_out = fmt.sampleRate()

        # Generación de tono y silencio
        def tone(ms):
            L = int(sr_out * (ms / 1000))
            buf = array.array('h')
            attack = max(1, int(sr_out * 0.005))   # 5 ms
            release = attack
            for n in range(L):
                amp = vol
                if n < attack:
                    amp *= n / float(attack)
                elif n > L - release:
                    amp *= max(0.0, (L - n) / float(release))
                s = int(32767 * amp * math.sin(2 * math.pi * freq * (n / sr_out)))
                buf.append(s)
            return buf.tobytes()

        def silence(ms):
            L = int(sr_out * (ms / 1000))
            return (array.array('h', [0] * L)).tobytes()

        # Construcción del flujo PCM
        full = bytearray()

        # Nota: los saltos de línea en 'morse' no son significativos para el audio,
        # así que simplemente se ignoran al dividir en tokens.
        tokens = morse.split()
        for idx, token in enumerate(tokens):
            if token == "/":
                full.extend(silence(word_gap))
                continue
            for i, ch in enumerate(token):
                full.extend(tone(dot_ms if ch == "." else dash_ms))
                if i != len(token) - 1:
                    full.extend(silence(intra_gap))
            if idx != len(tokens) - 1 and tokens[idx + 1] != "/":
                full.extend(silence(letter_gap))

        data = bytes(full)

        # Arranque de audio
        self.audio_output = QAudioOutput(dev, fmt, self)
        self.audio_output.setVolume(1.0)  # ganancia del dispositivo (0..1). La amplitud la controla 'vol'

        self._beep_bytes = QByteArray(data)
        self._beep_buffer = QBuffer()
        self._beep_buffer.setData(self._beep_bytes)
        self._beep_buffer.open(QBuffer.ReadOnly)

        self.audio_output.stateChanged.connect(self._on_beep_state_changed)
        self._beep_playing = True
        self.btn_beep.setEnabled(False)

        self.audio_output.start(self._beep_buffer)

    def _on_beep_state_changed(self, state):
        try:
            from PyQt5.QtMultimedia import QAudio
        except Exception:
            # Si no está disponible, limpiamos directamente
            self._beep_cleanup()
            return

        if not self._beep_playing:
            return

        if state in (QAudio.IdleState, QAudio.StoppedState):
            self._beep_cleanup()

    def _beep_cleanup(self):
        """
        Limpieza segura: evita cierres inesperados y permite nueva reproducción.
        """
        try:
            if self.audio_output:
                try:
                    self.audio_output.stateChanged.disconnect(self._on_beep_state_changed)
                except Exception:
                    pass
                try:
                    self.audio_output.stop()
                except Exception:
                    pass
                try:
                    self.audio_output.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if self._beep_buffer and self._beep_buffer.isOpen():
                self._beep_buffer.close()
        except Exception:
            pass

        self.audio_output = None
        self._beep_buffer = None
        self._beep_bytes = None
        self._beep_playing = False

        # reactiva botón
        self.btn_beep.setEnabled(True)


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    gui = MorseGUI()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
