# Pruebas del decodificador con audio sintético.
# Ejecutar:  python test_decoder.py
import math
import random
import wave
from array import array

from codmorse import MORSE
from morse_decoder import MorseAudioDecoder, decodificar_wav
from app import morse_a_texto


def sintetizar(texto, wpm=10, sr=8000, freq=700, amp=0.5, ruido=0.02,
               jitter=0.0, seed=1, silencio_ini=0.6, silencio_fin=1.0):
    """Genera audio PCM16 de `texto` en Morse. jitter = variación aleatoria de tiempos (0.1 = ±10 %)."""
    rnd = random.Random(seed)
    u = 1.2 / wpm  # segundos por unidad

    def j():
        return 1.0 + rnd.uniform(-jitter, jitter)

    seg = [('s', silencio_ini)]
    palabras = texto.upper().split()
    for pi, pal in enumerate(palabras):
        for li, ch in enumerate(pal):
            code = MORSE[ch]
            for si, s in enumerate(code):
                seg.append(('t', u * (1 if s == '.' else 3) * j()))
                if si != len(code) - 1:
                    seg.append(('s', u * j()))
            if li != len(pal) - 1:
                seg.append(('s', 3 * u * j()))
        if pi != len(palabras) - 1:
            seg.append(('s', 7 * u * j()))
    seg.append(('s', silencio_fin))

    out = array('h')
    fase = 0
    for tipo, dur in seg:
        n = int(sr * dur)
        if tipo == 't':
            rampa = int(sr * 0.005)
            for k in range(n):
                a = amp
                if k < rampa:
                    a *= k / rampa
                elif k > n - rampa:
                    a *= (n - k) / rampa
                v = a * math.sin(2 * math.pi * freq * (fase / sr)) + rnd.gauss(0, ruido)
                out.append(max(-32767, min(32767, int(v * 32767))))
                fase += 1
        else:
            for k in range(n):
                out.append(max(-32767, min(32767, int(rnd.gauss(0, ruido) * 32767))))
                fase += 1
    return out


def decodificar(audio, sr, trozo=1000, **kw):
    """Alimenta el decodificador en trozos pequeños, como haría la captura en vivo."""
    d = MorseAudioDecoder(sr, **kw)
    partes = []
    for i in range(0, len(audio), trozo):
        partes.append(d.feed(audio[i:i + trozo]))
    partes.append(d.flush())
    txt = ''.join(partes).strip()
    return txt.rstrip('/ ').strip(), d


def caso(nombre, texto, esperado_ok=True, **kw):
    sr = kw.pop('sr', 8000)
    dec_kw = kw.pop('dec', {})
    audio = sintetizar(texto, sr=sr, **kw)
    morse, d = decodificar(audio, sr, **dec_kw)
    leido = morse_a_texto(morse)
    ok = (leido == texto.upper())
    print(f"[{'OK ' if ok else 'FALLO'}] {nombre:<46} -> '{leido}'  (WPM detectado ≈ {d.wpm:.1f})")
    if not ok:
        print("        esperado:", texto.upper())
        print("        morse   :", morse)
    return ok


if __name__ == '__main__':
    resultados = []
    resultados.append(caso("10 WPM limpio", "HOLA MUNDO", ruido=0.0))
    resultados.append(caso("10 WPM con ruido", "CQ CQ DE EA4IVW", ruido=0.03))
    resultados.append(caso("15 WPM, velocidad ajustada", "HOLA MUNDO 73", wpm=15, dec=dict(wpm=15)))
    resultados.append(caso("20 WPM, arranque a 10 WPM (adaptativo)", "CQ CQ DE EA4IVW K", wpm=20))
    resultados.append(caso("6 WPM, arranque a 10 WPM (adaptativo)", "SOS SOS", wpm=6))
    resultados.append(caso("Tono 500 Hz", "QRZ", freq=500, wpm=12, dec=dict(wpm=12)))
    resultados.append(caso("Tono 1000 Hz", "TEST 123", freq=1000))
    resultados.append(caso("44100 Hz de muestreo", "HOLA", sr=44100))
    resultados.append(caso("Señal débil (amp 0.05) con ruido 0.005", "HOLA MUNDO", amp=0.05, ruido=0.005,
                           dec=dict(sensitivity=80)))
    resultados.append(caso("Tiempos humanos (±12 %)", "CQ DE EA4IVW", jitter=0.12, ruido=0.02,
                           wpm=12, dec=dict(wpm=12)))
    resultados.append(caso("Todos los números", "0123456789"))

    resultados.append(caso("Manual 12 WPM", "CQ CQ DE EA4IVW", wpm=12, dec=dict(wpm=12, adaptive=False)))
    resultados.append(caso("Auto 18 WPM, tiempos humanos ±18 %", "HOLA QUE TAL EA4IVW", wpm=18,
                           jitter=0.18, ruido=0.03, seed=3))
    resultados.append(caso("Auto 25 WPM, texto largo", "EL RAPIDO ZORRO MARRON SALTA SOBRE EL PERRO 73", wpm=25))

    # Zumbido de 50 Hz + componente continua
    base = sintetizar("HOLA MUNDO", ruido=0.02)
    zumb = array('h', [max(-32767, min(32767, int(v + 0.15 * 32767 * math.sin(2 * math.pi * 50 * i / 8000) + 3000)))
                       for i, v in enumerate(base)])
    m, _ = decodificar(zumb, 8000)
    ok = morse_a_texto(m).strip() == "HOLA MUNDO"
    print(f"[{'OK ' if ok else 'FALLO'}] Zumbido 50 Hz + componente continua              -> '{morse_a_texto(m).strip()}'")
    resultados.append(ok)

    # Cambio de velocidad a mitad de la transmisión (10 → 20 WPM)
    m, _ = decodificar(sintetizar("CQ CQ DE EA4IVW", wpm=10, silencio_fin=1.5) +
                       sintetizar("HOLA MUNDO TEST", wpm=20, silencio_ini=0.3), 8000)
    ok = morse_a_texto(m).strip() == "CQ CQ DE EA4IVW HOLA MUNDO TEST"
    print(f"[{'OK ' if ok else 'FALLO'}] Cambio de velocidad 10 → 20 WPM                  -> '{morse_a_texto(m).strip()}'")
    resultados.append(ok)

    # WAV de ida y vuelta
    audio = sintetizar("HOLA MUNDO", ruido=0.02)
    with wave.open('/tmp/prueba.wav', 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(audio.tobytes())
    m = decodificar_wav('/tmp/prueba.wav')
    ok = morse_a_texto(m) == "HOLA MUNDO"
    print(f"[{'OK ' if ok else 'FALLO'}] decodificar_wav (mono 16 bits)                  -> '{morse_a_texto(m)}'")
    resultados.append(ok)

    # WAV estéreo 8 bits
    st = array('h')
    for s in audio:
        st.append(s); st.append(0)
    with wave.open('/tmp/prueba_st.wav', 'wb') as w:
        w.setnchannels(2); w.setsampwidth(1); w.setframerate(8000)
        w.writeframes(bytes(((x >> 8) + 128) & 0xFF for x in st))
    m = decodificar_wav('/tmp/prueba_st.wav')
    ok = morse_a_texto(m) == "HOLA MUNDO"
    print(f"[{'OK ' if ok else 'FALLO'}] decodificar_wav (estéreo 8 bits)                -> '{morse_a_texto(m)}'")
    resultados.append(ok)

    # Solo ruido: no debe inventar símbolos
    rnd = random.Random(5)
    ruido = array('h', [int(rnd.gauss(0, 0.05) * 32767) for _ in range(8000 * 10)])
    morse, _ = decodificar(ruido, 8000)
    ok = morse == ''
    print(f"[{'OK ' if ok else 'FALLO'}] 10 s de ruido solo (no debe detectar nada)      -> '{morse}'")
    resultados.append(ok)

    print(f"\n{sum(resultados)}/{len(resultados)} pruebas correctas")
