# Point d'entrée sans console (double-clic, ou PyInstaller pour faire un .exe)
import sys

from razerlite.__main__ import main

sys.exit(main())
