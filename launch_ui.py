import sys
import os

# Aggiungi la directory parent alla path per importare i moduli del progetto
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ui.agent_ui import main

if __name__ == "__main__":
    main()
