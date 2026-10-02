from pathlib import Path

from chem_agent.config import Settings
from chem_agent.ui import launch

if __name__ == "__main__":
    launch(Settings.load(Path(__file__).parent))
