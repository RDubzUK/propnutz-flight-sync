"""PyInstaller entry point for the Electron-owned local server."""
from multiprocessing import freeze_support


if __name__ == "__main__":
    freeze_support()
    from fpv_audio_pairing.desktop import main

    main()
