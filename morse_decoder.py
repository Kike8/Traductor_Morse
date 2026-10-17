# Decodificador de código Morse a partir de audio (un bip corto = ".", un bip largo = "-", un espacio en blanco "/")
# Python puro: no requiere numpy ni librerías de audio. Es independiente de la interfaz
# gráfica, así que se puede usar desde la GUI (micrófono), desde consola (archivos WAV)
# o en pruebas automáticas.
# Proyecto: Traductor Morse - quicastillo@gmail.com EA4IVW

# morse_decoder.py
import math
import sys
import wave
from array import array


class MorseAudioDecoder:
    """
    Detecta el código Morse en un flujo de audio PCM de 16 bits (mono).

    Funcionamiento:
      1. El audio se divide en tramos de 5 ms y se mide su nivel (RMS, sin componente continua).
      2. Un umbral adaptativo (con histéresis y filtro anti-rebotes) decide si hay tono o silencio.
         Se registra la duración de cada tono y de cada pausa.
      3. Cuando hay una pausa larga se decodifica el grupo acumulado (normalmente una palabra):
           · modo automático: la unidad de tiempo se estima agrupando las duraciones de los
             tonos en dos clústeres (cortos = puntos, largos = rayas), de modo que funciona
             aunque la velocidad real sea muy distinta de la configurada;
           · modo manual: la unidad sale de la velocidad en WPM indicada.
         Punto = 1 unidad, raya = 3 unidades; el límite entre ambos está en 2 unidades.
         Pausa ≥ 2 unidades → fin de letra (espacio); pausa ≥ 5 unidades → fin de palabra ('/').

    La salida usa el mismo formato que el resto de la aplicación:
    letras separadas por un espacio y palabras separadas por ' / '.

    Todos los tiempos se miden en muestras de audio, no con el reloj del sistema,
    por lo que un retraso de la interfaz no distorsiona la detección.

    Limitación conocida: al empezar se dedican ~40 ms a medir el ruido de fondo; si el audio
    arranca justo con un tono (sin ruido ni silencio previos) se puede perder el primer bip.
    """

    HOP_MS = 5.0           # resolución temporal del análisis
    DEBOUNCE_MS = 15.0     # un cambio de estado debe durar al menos esto para ser válido
    WARMUP_MS = 40.0       # calibración inicial del ruido de fondo (sin detectar tonos)
    MIN_CIERRE_MS = 700.0  # pausa mínima para cerrar el primer grupo (aún sin calibrar)
    MAX_GRUPO = 48         # nº de tonos a partir del cual se fuerza el cierre en un fin de letra

    def __init__(self, sample_rate: int, wpm: float = 10.0,
                 adaptive: bool = True, sensitivity: int = 50):
        self.sample_rate = int(sample_rate)
        self.frame_len = max(1, int(self.sample_rate * self.HOP_MS / 1000.0))
        self.hop_ms = self.frame_len * 1000.0 / self.sample_rate
        # Filtro paso-alto de ~60 Hz para eliminar componente continua / zumbidos
        self._hp_k = 1.0 - math.exp(-2.0 * math.pi * 60.0 / self.sample_rate)
        # El "pico" de referencia decae con una vida media de ~4 s
        self._peak_decay = 0.5 ** (self.hop_ms / 1000.0 / 4.0)

        self.adaptive = bool(adaptive)
        self.set_sensitivity(sensitivity)
        self.set_wpm(wpm)
        self.reset()

    # ── Configuración ────────────────────────────────────────────────────────
    def set_wpm(self, wpm: float):
        """Velocidad nominal en palabras por minuto (10 WPM = punto de 120 ms)."""
        wpm = min(50.0, max(3.0, float(wpm)))
        self._base_unit_ms = 1200.0 / wpm
        self.unit_ms = self._base_unit_ms
        self._calibrado = False

    def set_adaptive(self, adaptive: bool):
        self.adaptive = bool(adaptive)
        if not self.adaptive:
            self.unit_ms = self._base_unit_ms

    def set_sensitivity(self, sensitivity: int):
        """
        Sensibilidad 1..100. Fija el nivel mínimo que se considera tono:
        1 ≈ -20 dB (hace falta señal muy fuerte), 50 ≈ -40 dB, 100 ≈ -60 dB.
        """
        s = min(100, max(1, int(sensitivity)))
        self._min_level = 10 ** ((-20.0 - 0.4 * s) / 20.0)

    @property
    def wpm(self) -> float:
        """Velocidad en uso (en modo automático, la estimada)."""
        return 1200.0 / self.unit_ms

    # ── Estado ───────────────────────────────────────────────────────────────
    def reset(self):
        self.unit_ms = self._base_unit_ms
        self._calibrado = False
        self._buf = []
        self._dc = 0.0
        self._noise = 0.0
        self._warmup = max(1, int(round(self.WARMUP_MS / self.hop_ms)))
        self._warm_seen = 0
        self._peak = self._min_level * 3.0
        self._tone = False          # estado confirmado (tono / silencio)
        self._run_ms = 0.0          # duración del estado confirmado actual
        self._pending = 0           # fotogramas consecutivos que contradicen el estado
        self._grp = []              # grupo en curso: [duración_tono, pausa_posterior]
        self._gap_acc = 0.0         # silencio acumulado desde el último tono válido
        self._letter_open = False   # hay símbolos emitidos sin cerrar la letra
        self._word_pending = False  # letra cerrada, falta decidir si termina la palabra
        # Datos para los medidores de la interfaz
        self.level = 0.0
        self.chunk_level = 0.0
        self.threshold = self._min_level
        self.tone_on = False

    # ── Entrada de audio ─────────────────────────────────────────────────────
    def feed(self, samples) -> str:
        """
        Procesa muestras enteras de 16 bits (lista o array('h')) y devuelve el
        texto Morse nuevo detectado (puede ser una cadena vacía).
        """
        buf = self._buf
        buf.extend(samples)
        n = self.frame_len
        total = len(buf)
        i = 0
        out = []
        self.chunk_level = 0.0
        while i + n <= total:
            level = self._frame_level(buf[i:i + n])
            i += n
            if level > self.chunk_level:
                self.chunk_level = level
            piece = self._step(level)
            if piece:
                out.append(piece)
        del buf[:i]
        self.tone_on = self._tone
        return ''.join(out)

    def flush(self) -> str:
        """Fuerza la decodificación de lo pendiente (al detener la escucha o acabar un archivo)."""
        u = self.unit_ms
        cierre = 5.0 * u if (self._calibrado or not self.adaptive) \
            else max(5.0 * u, self.MIN_CIERRE_MS)
        ms = max(cierre, 2.1 * u) + self.DEBOUNCE_MS + 2 * self.HOP_MS + 20.0
        texto = self.feed([0] * int(ms / 1000.0 * self.sample_rate))
        if texto.endswith('/ '):          # no dejar un separador de palabra colgando
            texto = texto[:-2]
        return texto

    # ── Internos: nivel y detección de tono ──────────────────────────────────
    def _frame_level(self, chunk) -> float:
        dc = self._dc
        k = self._hp_k
        acc = 0.0
        for x in chunk:
            dc += k * (x - dc)
            y = x - dc
            acc += y * y
        self._dc = dc
        return math.sqrt(acc / len(chunk)) / 32768.0

    def _step(self, level: float) -> str:
        hop = self.hop_ms
        self.level = level

        # Calibración inicial: se estima el ruido de fondo antes de buscar tonos
        if self._warmup > 0:
            self._warmup -= 1
            self._noise = (self._noise * self._warm_seen + level) / (self._warm_seen + 1)
            self._warm_seen += 1
            self.threshold = max(self._min_level, self._noise * 2.5)
            return ''

        # Pico de referencia: sube rápido pero no de golpe (un "clic" no lo dispara)
        if level > self._peak:
            self._peak += 0.3 * (level - self._peak)
        else:
            self._peak = max(self._peak * self._peak_decay, self._min_level * 2.0)

        # Umbral adaptativo: entre el ruido de fondo y el pico, con mínimo absoluto
        # y exigiendo ~8 dB sobre el ruido de fondo.
        noise = self._noise
        thr = max(self._min_level, noise * 2.5, noise + 0.35 * (self._peak - noise))
        self.threshold = thr

        # Histéresis: para seguir en tono basta superar el 60 % del umbral
        raw = level > (thr * 0.6 if self._tone else thr)

        # El ruido de fondo solo se estima durante el silencio
        if not self._tone and not raw:
            rate = 0.2 if level < noise else 0.02
            self._noise += rate * (level - noise)

        if raw == self._tone:
            # Estado estable (los fotogramas "dudosos" previos se absorben: era un glitch)
            self._run_ms += (self._pending + 1) * hop
            self._pending = 0
        else:
            self._pending += 1
            if self._pending * hop >= self.DEBOUNCE_MS:
                self._cambiar_estado()

        return '' if self._tone else self._comprobar_silencio()

    def _cambiar_estado(self):
        if self._tone:
            self._fin_de_tono(self._run_ms)
            self._tone = False
        else:
            self._gap_acc += self._run_ms
            self._tone = True
        # Los fotogramas pendientes ya pertenecen al nuevo estado
        self._run_ms = self._pending * self.hop_ms
        self._pending = 0

    def _fin_de_tono(self, dur_ms: float):
        u = self.unit_ms
        limite_sup = max(8.0 * u, 1500.0 if self.adaptive else 0.0)
        # Demasiado corto (clic / ruido) o demasiado largo (portadora continua): se descarta
        # y su duración cuenta como silencio.
        if dur_ms < max(self.DEBOUNCE_MS * 1.5, 0.3 * u) or dur_ms > limite_sup:
            self._gap_acc += dur_ms
            return
        if self._grp:
            self._grp[-1][1] = self._gap_acc
        self._grp.append([dur_ms, None])
        self._gap_acc = 0.0

    # ── Internos: segmentación y decodificación ──────────────────────────────
    def _comprobar_silencio(self) -> str:
        out = ''
        u = self.unit_ms
        sil = self._gap_acc + self._run_ms

        if self._grp:
            cierre = 5.0 * u if (self._calibrado or not self.adaptive) \
                else max(5.0 * u, self.MIN_CIERRE_MS)
            if sil >= cierre or (len(self._grp) >= self.MAX_GRUPO and sil >= 2.0 * u):
                texto = self._decodificar_grupo()
                if texto:
                    out += texto
                    self._letter_open = True
                    self._word_pending = False
                u = self.unit_ms      # puede haberse recalibrado

        if self._letter_open and sil >= 2.0 * u:
            out += ' '
            self._letter_open = False
            self._word_pending = True
        if self._word_pending and sil >= 5.0 * u:
            out += '/ '
            self._word_pending = False
        return out

    @staticmethod
    def _estimar_unidad(durs):
        """
        Estima la unidad de tiempo (ms) agrupando las duraciones de los tonos en dos
        clústeres. Devuelve None si no hay mezcla clara de puntos y rayas.
        """
        if len(durs) < 2:
            return None
        lo, hi = min(durs), max(durs)
        if hi < 2.0 * lo:
            return None
        c1, c2 = lo, hi
        for _ in range(12):
            a = [d for d in durs if abs(d - c1) <= abs(d - c2)]
            b = [d for d in durs if abs(d - c1) > abs(d - c2)]
            if not a or not b:
                return None
            n1, n2 = sum(a) / len(a), sum(b) / len(b)
            estable = abs(n1 - c1) < 0.5 and abs(n2 - c2) < 0.5
            c1, c2 = n1, n2
            if estable:
                break
        if not (2.0 <= c2 / c1 <= 5.0):   # una raya debería durar ≈ 3 puntos
            return None
        return min(400.0, max(24.0, (c1 + c2 / 3.0) / 2.0))

    def _decodificar_grupo(self) -> str:
        grupo, self._grp = self._grp, []
        if not grupo:
            return ''
        u = self.unit_ms
        if self.adaptive:
            est = self._estimar_unidad([g[0] for g in grupo])
            if est is not None:
                # El grupo se decodifica con su propia estimación; la unidad "global"
                # (para el cierre de grupos y los espacios) se suaviza.
                self.unit_ms = est if not self._calibrado else 0.35 * self.unit_ms + 0.65 * est
                self._calibrado = True
                u = est

        partes = []
        ultimo = len(grupo) - 1
        for i, (dur, pausa) in enumerate(grupo):
            partes.append('.' if dur < 2.0 * u else '-')
            if i != ultimo and pausa is not None:
                if pausa >= 5.0 * u:
                    partes.append(' / ')
                elif pausa >= 2.0 * u:
                    partes.append(' ')
        return ''.join(partes)


# ─────────────────────────────────────────────────────────────────────────────
# Lectura de archivos WAV
# ─────────────────────────────────────────────────────────────────────────────
def _pcm_a_enteros(raw: bytes, sampwidth: int, canales: int):
    """Convierte datos PCM del WAV a muestras de 16 bits (primer canal)."""
    if sampwidth == 2:
        a = array('h')
        a.frombytes(raw[:len(raw) - len(raw) % 2])
        if sys.byteorder == 'big':
            a.byteswap()
        muestras = a
    elif sampwidth == 1:                                  # 8 bits: sin signo
        muestras = array('h', [(b - 128) << 8 for b in raw])
    elif sampwidth == 3:                                  # 24 bits con signo
        muestras = array('h', [
            int.from_bytes(raw[i:i + 3], 'little', signed=True) >> 8
            for i in range(0, len(raw) - 2, 3)
        ])
    elif sampwidth == 4:                                  # 32 bits con signo
        a = array('i')
        a.frombytes(raw[:len(raw) - len(raw) % 4])
        if sys.byteorder == 'big':
            a.byteswap()
        muestras = array('h', [x >> 16 for x in a])
    else:
        raise ValueError(f"Formato WAV no soportado ({sampwidth * 8} bits)")

    if canales > 1:
        muestras = muestras[::canales]
    return muestras


def decodificar_wav(ruta: str, wpm: float = 10.0, adaptive: bool = True,
                    sensitivity: int = 50) -> str:
    """Decodifica un archivo WAV (PCM) y devuelve el código Morse detectado."""
    with wave.open(ruta, 'rb') as w:
        canales = w.getnchannels()
        ancho = w.getsampwidth()
        sr = w.getframerate()
        dec = MorseAudioDecoder(sr, wpm=wpm, adaptive=adaptive, sensitivity=sensitivity)
        partes = []
        while True:
            raw = w.readframes(max(1, sr // 2))
            if not raw:
                break
            partes.append(dec.feed(_pcm_a_enteros(raw, ancho, canales)))
    partes.append(dec.flush())
    texto = ''.join(partes).strip()
    if texto.endswith('/'):
        texto = texto[:-1].rstrip()
    return texto
