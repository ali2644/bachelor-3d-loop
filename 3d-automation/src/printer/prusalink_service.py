import PrusaLinkPy

class PrusaLinkService:
    def __init__(self, printer_ip, api_key):
        self.printer_ip = printer_ip
        self.api_key = api_key
        self.client = PrusaLinkPy.PrusaLinkPy(printer_ip, api_key)

    def is_connected(self):
        pass
        
    def upload_gcode(self, gcode_file_path):
        pass

    def start_print_job(self):
        pass

    def get_status(self):
        pass