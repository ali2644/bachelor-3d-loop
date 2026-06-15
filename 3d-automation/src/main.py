from orchestrator import PrintOrchestrator
from printer.prusalink_service import PrusaLinkService
from printer.slicer_service import SlicerService
from pathlib import Path

PRINTER_IP = "10.8.170.57"
API_KEY ="uECFo9ZtvraGhNW"
#TODO Pfade über Path(__file__), damit sie nicht mehr hardcoded sind.

PROJECT_ROOT = Path(__file__).resolve().parents[3]
print ("Project root:", PROJECT_ROOT)
PRUSASLICER_PATH = Path.home() / "apps/prusaslicer/PrusaSlicer-2.9.1-x86_64.AppImage"

STL_PATH = PROJECT_ROOT / "bachelor-3d-loop/3d-automation/data/models/Oberflächenmessung_Testkörper_MK1 (1).stl"
PROFILE_PATH = PROJECT_ROOT / "bachelor-3d-loop/3d-automation/config/slicer_profile.ini"
GCODE_PATH = PROJECT_ROOT / "bachelor-3d-loop/3d-automation/data/gcode/output.gcode"

printer_service = PrusaLinkService(PRINTER_IP, API_KEY)
slicer_service = SlicerService(PRUSASLICER_PATH)

orchestrator = PrintOrchestrator(slicer_service, printer_service)

orchestrator.run_single_print_cycle(
    STL_PATH,
    PROFILE_PATH,
    GCODE_PATH
)




