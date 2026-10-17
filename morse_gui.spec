# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['morse_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['PyQt5.QtMultimedia', 'morse_decoder', 'morse_receptor'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='morse_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='morse_gui',
)
app = BUNDLE(
    coll,
    name='morse_gui.app',
    icon=None,
    bundle_identifier='com.ea4ivw.morsegui',   # identificador estable (necesario para recordar el permiso de micrófono)
    info_plist={
        # Necesario en macOS para que la app pueda usar el micrófono (receptor Morse)
        'NSMicrophoneUsageDescription':
            'Se usa el micrófono para escuchar transmisiones y detectar código Morse.',
    },
)
