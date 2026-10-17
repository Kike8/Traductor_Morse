# Aplicación que convierte el texto en código morse y viceversa
# Autor quicastillo@gmail.com EA4IVW

# app.py
from codmorse import MORSE, MORSE_INV
from morse_decoder import decodificar_wav

def texto_a_morse(texto: str) -> str:
    resultado = []
    for char in texto.upper():
        if char in MORSE:
            resultado.append(MORSE[char])
        else:
            resultado.append('?')  # Caracter no reconocido
    return ' '.join(resultado)

def morse_a_texto(morse: str) -> str:
    resultado = []
    for code in morse.split():
        if code in MORSE_INV:
            resultado.append(MORSE_INV[code])
        else:
            resultado.append('?')  # Código no reconocido
    return ''.join(resultado)

def main():
    print("=== Traductor Código Morse ⇄ Texto ===")
    print("1) Texto a Morse")
    print("2) Morse a Texto")
    print("3) Grabación de audio (WAV) a Morse y Texto")
    opcion = input("Elige una opción: ")

    if opcion == "1":
        texto = input("Introduce el texto: ")
        print("Morse:", texto_a_morse(texto))

    elif opcion == "2":
        codigo = input("Introduce el código Morse (separa con espacios): ")
        print("Texto:", morse_a_texto(codigo))

    elif opcion == "3":
        ruta = input("Ruta del archivo WAV: ").strip().strip('"')
        try:
            morse = decodificar_wav(ruta)
        except Exception as e:
            print("No se pudo analizar el archivo:", e)
        else:
            if morse:
                print("Morse detectado:", morse)
                print("Texto:", morse_a_texto(morse))
            else:
                print("No se ha detectado código Morse en el archivo.")

    else:
        print("Opción no válida")

if __name__ == "__main__":
    main()
