# Traductor_Morse
App que traduce texto a código morse y viceversa con capacidad de escucha y grabación

MORSE_DECODER.PYel cerebro de la aplicación

__init__: calcula el tamaño del tramo de análisis (5 ms) y el filtro que elimina el zumbido y la componente continua.
Ajustes : set_wpm (velocidad), set_adaptive (modo Auto) y set_sensitivity (nivel mínimo de detección). La propiedad wpm devuelve la velocidad en uso.
reset: deja todo el estado a cero (ruido, grupo en curso, etc.).
feed: punto de entrada. Recibe muestras de audio, las corta en tramos de 5 ms y devuelve el Morse nuevo detectado.
flush: fuerza decodificar lo pendiente, para que no se quede la última letra sin salir al detener la escucha.
_frame_level: calcula el volumen (RMS) de un tramo, tras quitar la componente continua.
_step: decide en cada tramo si hay tono o silencio. Mide primero el ruido de fondo y usa un umbral adaptativo con histéresis y filtro anti-rebotes de 15 ms.
_cambiar_estado y _fin_de_tono: registran la duración de cada bip y de cada pausa. Descartan los clics demasiado cortos y las portadoras demasiado largas.
_comprobar_silencio: cuando la pausa es larga cierra el grupo y decodifica. Después inserta el espacio entre letras (≥ 2 unidades) y la / entre palabras (≥ 5 unidades).
_estimar_unidad: detecta la velocidad automáticamente. Agrupa las duraciones en dos clústeres (cortos y largos) y deduce la unidad de tiempo.
_decodificar_grupo: con esa unidad clasifica cada bip (menos de 2 unidades es ., el resto es -) y coloca los separadores.
_pcm_a_enteros: convierte WAV de 8, 16, 24 o 32 bits, mono o estéreo, a muestras de 16 bits.
decodificar_wav: lee un archivo WAV y lo pasa por el decodificador.

MORSE_RECEPTOR.PY: CAPTURA DE AUDIO Y PANEL (QT)

NivelWidget: la barra de nivel en dB. Es verde con tono y azul sin él, y la línea naranja marca el umbral.
ReceptorMorse: el panel. Define dos señales: morse_decodificado (Morse nuevo en directo) y bloque_decodificado (resultado de un WAV).
_build_ui: crea los botones, el selector de entrada, la velocidad (WPM), la casilla Auto, la sensibilidad, el medidor y el estado.
_llenar_dispositivos: lista las entradas de audio y pone primero la predeterminada.
Aplican los cambios de velocidad, Auto y sensibilidad al decodificador.
alternar / iniciar: piden formato PCM de 16 bits a 8000 Hz, crean el decodificador, abren QAudioInput y arrancan un temporizador de 30 ms que lee el audio.
detener y _liberar_audio: leen lo que queda, hacen flush y liberan el audio y el temporizador.
_on_ready_read: lee los bytes y los convierte en muestras. Mantiene los bytes sobrantes entre lecturas, se queda con el primer canal si es estéreo, llama a feed y emite el texto Morse. Actualiza también el medidor.
_diagnostico: a los ~2 s avisa en rojo si no llega audio o llega solo silencio (permisos).
analizar_wav: abre un archivo, lo decodifica y emite el resultado.

MORSE_GUI.PY

Importa QTextCursor, para escribir al final de la entrada.
Importa el receptor en un try/except. Si falla, la app sigue funcionando sin él, como ya hacías con codmorse.
Crea el panel dentro de la ventana y conecta sus dos señales.
_antes_de_escuchar: si la entrada tiene texto, pregunta si borrarlo. Después cambia automáticamente a modo Morse → Texto.
_recibir_morse: añade el Morse detectado al final de la ventana de entrada. Con «Traducir al escribir» activado se traduce en directo.
_recibir_bloque: igual, pero para un WAV, y lo pone en una línea nueva.
closeEvent: detiene la escucha al cerrar la ventana.

APP.PY

importa decodificar_wav.
la opción 3 pide la ruta de un WAV, lo decodifica y muestra el Morse y su traducción.

OTROS

morse_gui.spec: añade hiddenimports para que PyInstaller incluya QtMultimedia y los módulos nuevos, y NSMicrophoneUsageDescription para el permiso de micrófono en macOS.
test_decoder.py: 19 pruebas con audio sintético (ruido, velocidades, zumbido, cambio de velocidad…). Se ejecuta con python test_decoder.py y conviene lanzarlo si alguna vez tocas el decodificador.




