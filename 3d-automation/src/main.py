from printer.prusalink_service import PrusaLinkService
from orchestrator import PrintOrchestrator

PRINTER_IP = "10.8.170.57"
API_KEY ="uECFo9ZtvraGhNW"
GCODE_PATH = "/home/hs-coburg.de/ali2644s/Schreibtisch/bachelor-3d-loop-feature-prusa-slicer-cli/3d-automation/data/gcode/output.gcode"



printer_service = PrusaLinkService(PRINTER_IP, API_KEY)
orchestrator = PrintOrchestrator(printer_service)

orchestrator.run_single_print_cycle(GCODE_PATH)