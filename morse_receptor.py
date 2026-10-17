# Receptor de Morse por audio: escucha el micrófono / entrada de línea (p. ej. la salida de
# audio de un receptor de radio) y detecta el código Morse: bip corto = ".", bip largo = "-".
# Usa QtMultimedia (ya presente en PyQt5), sin dependencias adicionales.
# Proyecto: Traductor Morse - quicastillo@gmail.com EA4IVW

# morse_receptor.py
import math
import sys
from array import array

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtWidgets import (
    QGroupBox, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox,
    QSpinBox, QCheckBox, QSlider, QFileDialog, QMessageBox, QSizePolicy
)

from morse_decoder import MorseAudioDecoder, decodificar_wav

# QtMultimedia se carga de forma tolerante, igual que en el emisor de morse_gui.py
try:
    from PyQt5.QtMultimedia import QAudioInput, QAudioFormat, QAudioDeviceInfo, QAudio
    _MM_ERROR = None
except Exception as e:                      # pragma: no cover
    _MM_ERROR = e


# ─────────────────────────────────────────────────────────────────────────────
# Medidor de nivel con marca de umbral
# ─────────────────────────────────────────────────────────────────────────────
class NivelWidget(QWidget):
    """Barra de nivel (escala dB) con la marca del umbral de detección."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(18)
        self.setMaximumHeight(18)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._nivel = 0.0
        self._umbral = 0.0
        self._tono = False

    @staticmethod
    def _pos(v: float) -> float:
        """Nivel lineal (0..1) → posición 0..1 en una escala de -60 dB a 0 dB."""
        db = 20.0 * math.log10(max(v, 1e-5))
        return min(1.0, max(0.0, (db + 60.0) / 60.0))

    def actualizar(self, nivel: float, umbral: float, tono: bool):
        self._nivel, self._umbral, self._tono = nivel, umbral, tono
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, QColor(35, 35, 35))
        ancho = int(r.width() * self._pos(self._nivel))
        color = QColor(60, 200, 90) if self._tono else QColor(90, 130, 200)
        p.fillRect(0, 0, ancho, r.height(), color)
        x = int(r.width() * self._pos(self._umbral))
        p.setPen(QPen(QColor(255, 170, 0), 2))
        p.drawLine(x, 0, x, r.height())
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# Panel del receptor
# ─────────────────────────────────────────────────────────────────────────────
class ReceptorMorse(QGroupBox):
    """
    Panel "Receptor Morse".

    Señales:
      morse_decodificado(str)  → código Morse nuevo detectado en directo (hay que añadirlo).
      bloque_decodificado(str) → resultado completo de analizar un archivo WAV.
    """
    morse_decodificado = pyqtSignal(str)
    bloque_decodificado = pyqtSignal(str)

    def __init__(self, antes_de_escuchar=None, parent=None):
        """
        antes_de_escuchar: función opcional sin argumentos que devuelve False para cancelar
        el inicio de la escucha (la usa la ventana principal para preparar la entrada).
        """
        super().__init__("Receptor Morse (escuchar transmisión)", parent)
        self._antes = antes_de_escuchar
        self._audio = None
        self._io = None
        self._decoder = None
        self._resto = b""
        self._canales = 1
        self._big_endian = False
        self._dispositivos = []
        self._timer = None
        self._info = ""
        self._bytes_total = 0
        self._max_abs = 0
        self._ticks = 0
        self._aviso_dado = False

        self._build_ui()
        self._llenar_dispositivos()

        if _MM_ERROR is not None:
            self.btn_escuchar.setEnabled(False)
            self.cmb_dispositivo.setEnabled(False)
            self.lbl_estado.setText(f"Audio no disponible (QtMultimedia): {_MM_ERROR}")

    # ── Interfaz ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        lay = QVBoxLayout(self)

        fila1 = QHBoxLayout()
        self.btn_escuchar = QPushButton("🎧 Escuchar")
        self.btn_wav = QPushButton("Analizar WAV…")
        self.cmb_dispositivo = QComboBox()
        self.cmb_dispositivo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_dispositivo.setMinimumContentsLength(18)
        fila1.addWidget(self.btn_escuchar)
        fila1.addWidget(self.btn_wav)
        fila1.addStretch()
        fila1.addWidget(QLabel("Entrada de audio:"))
        fila1.addWidget(self.cmb_dispositivo, 1)
        lay.addLayout(fila1)

        fila2 = QHBoxLayout()
        fila2.addWidget(QLabel("Velocidad:"))
        self.spin_wpm = QSpinBox()
        self.spin_wpm.setRange(5, 40)
        self.spin_wpm.setValue(10)
        self.spin_wpm.setSuffix(" WPM")
        self.spin_wpm.setToolTip("10 WPM = punto de 120 ms (la misma velocidad que el emisor).")
        fila2.addWidget(self.spin_wpm)
        self.chk_auto = QCheckBox("Auto")
        self.chk_auto.setChecked(True)
        self.chk_auto.setToolTip("Detecta automáticamente la velocidad de la transmisión.")
        fila2.addWidget(self.chk_auto)
        fila2.addSpacing(20)
        fila2.addWidget(QLabel("Sensibilidad:"))
        self.slider_sens = QSlider(Qt.Horizontal)
        self.slider_sens.setRange(1, 100)
        self.slider_sens.setValue(80)
        self.slider_sens.setToolTip("Súbela si la señal es débil; bájala si detecta ruido como bips.")
        fila2.addWidget(self.slider_sens, 1)
        lay.addLayout(fila2)

        self.nivel = NivelWidget()
        lay.addWidget(self.nivel)

        self.lbl_estado = QLabel("Detenido. Pulsa «Escuchar» para captar una transmisión.")
        self.lbl_estado.setStyleSheet("color: #666;")
        lay.addWidget(self.lbl_estado)

        self.btn_escuchar.clicked.connect(self.alternar)
        self.btn_wav.clicked.connect(self.analizar_wav)
        self.spin_wpm.valueChanged.connect(self._cambia_wpm)
        self.chk_auto.toggled.connect(self._cambia_auto)
        self.slider_sens.valueChanged.connect(self._cambia_sensibilidad)

    def _llenar_dispositivos(self):
        self.cmb_dispositivo.clear()
        self._dispositivos = []
        if _MM_ERROR is not None:
            return
        try:
            predet = QAudioDeviceInfo.defaultInputDevice()
            if not predet.isNull():
                self._dispositivos.append(predet)
                self.cmb_dispositivo.addItem(f"(Predeterminado) {predet.deviceName()}")
            for d in QAudioDeviceInfo.availableDevices(QAudio.AudioInput):
                if not predet.isNull() and d.deviceName() == predet.deviceName():
                    continue
                self._dispositivos.append(d)
                self.cmb_dispositivo.addItem(d.deviceName())
        except Exception as e:
            self.lbl_estado.setText(f"No se pudieron listar los dispositivos: {e}")
        if not self._dispositivos:
            self.btn_escuchar.setEnabled(False)
            self.lbl_estado.setText("No se encontró ninguna entrada de audio (micrófono).")

    # ── Parámetros en caliente ───────────────────────────────────────────────
    def _cambia_wpm(self, valor):
        if self._decoder is not None:
            self._decoder.set_wpm(valor)

    def _cambia_auto(self, activo):
        if self._decoder is not None:
            self._decoder.set_adaptive(activo)

    def _cambia_sensibilidad(self, valor):
        if self._decoder is not None:
            self._decoder.set_sensitivity(valor)

    # ── Escucha en directo ───────────────────────────────────────────────────
    def alternar(self):
        if self._audio is None:
            self.iniciar()
        else:
            self.detener()

    @property
    def escuchando(self) -> bool:
        return self._audio is not None

    def iniciar(self):
        if _MM_ERROR is not None or not self._dispositivos:
            return
        if self._antes is not None and self._antes() is False:
            return

        dev = self._dispositivos[max(0, self.cmb_dispositivo.currentIndex())]

        fmt = QAudioFormat()
        fmt.setSampleRate(8000)          # suficiente para tonos de Morse y muy ligero
        fmt.setChannelCount(1)
        fmt.setSampleSize(16)
        fmt.setCodec("audio/pcm")
        fmt.setByteOrder(QAudioFormat.LittleEndian)
        fmt.setSampleType(QAudioFormat.SignedInt)
        if not dev.isFormatSupported(fmt):
            fmt = dev.nearestFormat(fmt)

        if (fmt.codec() != "audio/pcm" or fmt.sampleSize() != 16
                or fmt.sampleType() != QAudioFormat.SignedInt):
            QMessageBox.warning(
                self, "Formato de audio no soportado",
                "El dispositivo seleccionado no ofrece audio PCM de 16 bits con signo.\n"
                "Prueba con otra entrada de audio."
            )
            return

        self._canales = max(1, fmt.channelCount())
        self._big_endian = (fmt.byteOrder() == QAudioFormat.BigEndian)
        self._resto = b""

        self._decoder = MorseAudioDecoder(
            fmt.sampleRate(),
            wpm=self.spin_wpm.value(),
            adaptive=self.chk_auto.isChecked(),
            sensitivity=self.slider_sens.value(),
        )

        self._audio = QAudioInput(dev, fmt, self)
        self._io = self._audio.start()
        if self._io is None or self._audio.error() != QAudio.NoError:
            QMessageBox.warning(
                self, "No se pudo abrir la entrada de audio",
                "Comprueba que el micrófono está conectado y que la aplicación tiene "
                "permiso para usarlo (Configuración del sistema → Privacidad → Micrófono)."
            )
            self._liberar_audio()
            return

        # Se sondea el dispositivo cada 30 ms (más fiable que la señal readyRead,
        # que en algunas plataformas no se emite).
        self._bytes_total = 0
        self._max_abs = 0
        self._ticks = 0
        self._aviso_dado = False
        self._info = (f"{dev.deviceName()} · {fmt.sampleRate()} Hz · "
                      f"{self._canales} canal(es)")
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._on_ready_read)
        self._timer.start()
        self.lbl_estado.setStyleSheet("color: #666;")
        self.btn_escuchar.setText("⏹ Detener")
        self.btn_wav.setEnabled(False)
        self.cmb_dispositivo.setEnabled(False)
        self.lbl_estado.setText(f"Escuchando… {self._info}")

    def detener(self):
        if self._audio is None:
            return
        # Lee lo que quede en el búfer y cierra la letra en curso
        try:
            self._on_ready_read()
        except Exception:
            pass
        if self._decoder is not None:
            resto = self._decoder.flush()
            if resto:
                self.morse_decodificado.emit(resto)
        self._liberar_audio()
        self.nivel.actualizar(0.0, 0.0, False)
        self.btn_escuchar.setText("🎧 Escuchar")
        self.btn_wav.setEnabled(True)
        self.cmb_dispositivo.setEnabled(_MM_ERROR is None)
        self.lbl_estado.setText("Detenido.")

    def _liberar_audio(self):
        try:
            if self._timer is not None:
                self._timer.stop()
                self._timer.deleteLater()
            if self._audio is not None:
                self._audio.stop()
                self._audio.deleteLater()
        except Exception:
            pass
        self._timer = None
        self._audio = None
        self._io = None
        self._decoder = None
        self._resto = b""

    def _on_ready_read(self):
        if self._io is None or self._decoder is None:
            return
        datos = bytes(self._io.readAll())
        self._ticks += 1
        self._bytes_total += len(datos)
        self._diagnostico()
        if not datos:
            return

        datos = self._resto + datos
        tam = 2 * self._canales                       # bytes por muestra multicanal
        util = len(datos) - (len(datos) % tam)
        self._resto = datos[util:]
        if util == 0:
            return

        muestras = array('h')
        muestras.frombytes(datos[:util])
        if self._big_endian != (sys.byteorder == 'big'):
            muestras.byteswap()
        if self._canales > 1:
            muestras = muestras[::self._canales]      # solo el primer canal

        pico = max(max(muestras), -min(muestras))
        if pico > self._max_abs:
            self._max_abs = pico

        texto = self._decoder.feed(muestras)
        d = self._decoder
        self.nivel.actualizar(d.chunk_level, d.threshold, d.tone_on)
        db = 20.0 * math.log10(max(d.chunk_level, 1e-5))
        db_u = 20.0 * math.log10(max(d.threshold, 1e-5))
        modo = "auto" if d.adaptive else "manual"
        if not self._aviso_dado:
            self.lbl_estado.setText(
                f"Escuchando… nivel {db:.0f} dB (umbral {db_u:.0f} dB) · "
                f"{d.wpm:.0f} WPM ({modo}) · {self._info}")
        if texto:
            self.morse_decodificado.emit(texto)

    def _diagnostico(self):
        """A los ~2 s de escuchar, avisa si no llega audio o llega silencio absoluto."""
        if self._aviso_dado or self._ticks != 66:
            return
        if self._bytes_total == 0:
            msg = ("⚠ No está llegando ningún dato de la entrada de audio. "
                   "Prueba con otra entrada del desplegable.")
        elif self._max_abs == 0:
            msg = ("⚠ La entrada entrega silencio absoluto (todo ceros): casi seguro falta el "
                   "permiso de micrófono para esta aplicación (o para el Terminal/IDE desde el "
                   "que la ejecutas), o está seleccionada una entrada sin señal.")
        else:
            return
        self._aviso_dado = True
        self.lbl_estado.setText(msg)
        self.lbl_estado.setStyleSheet("color: #b00020;")

    # ── Análisis de un archivo WAV ───────────────────────────────────────────
    def analizar_wav(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Abrir grabación de audio", "", "Audio WAV (*.wav);;Todos (*.*)"
        )
        if not ruta:
            return
        self.setCursor(Qt.WaitCursor)
        try:
            morse = decodificar_wav(
                ruta,
                wpm=self.spin_wpm.value(),
                adaptive=self.chk_auto.isChecked(),
                sensitivity=self.slider_sens.value(),
            )
        except Exception as e:
            QMessageBox.warning(
                self, "No se pudo analizar el archivo",
                f"Solo se admiten archivos WAV PCM (8, 16, 24 o 32 bits).\n\nDetalles: {e}"
            )
            return
        finally:
            self.unsetCursor()

        if not morse:
            QMessageBox.information(
                self, "Sin resultados",
                "No se ha detectado código Morse en el archivo.\n"
                "Prueba a aumentar la sensibilidad."
            )
            return
        self.lbl_estado.setText(f"Archivo analizado: {ruta}")
        self.bloque_decodificado.emit(morse)
