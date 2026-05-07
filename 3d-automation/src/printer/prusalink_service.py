import PrusaLinkPy

class PrusaLinkService:
    def __init__(self, printer_ip, api_key):
        self.printer_ip = printer_ip
        self.api_key = api_key
        self.client = PrusaLinkPy.PrusaLinkPy(printer_ip, api_key)

    def is_connected(self):
        try:
            self.client.get_printer_info()
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False
        
    def upload_gcode(self, gcode_file_path):
        if not self.is_connected():
            print("Printer is not connected.")
            return False
        try: 
            self.client.put_gcode(gcode_file_path, "FOLDER/test.gcode",printAfterUpload=False,overwrite=True)
            return True
        except Exception as e:
            print(f"Error uploading G-code: {e}")
            return False

    def start_print_job(self):
        if not self.is_connected():
            print("Printer is not connected.")
            return False   
        try:
            self.client.start_print("FOLDER/test.gcode")
            return True
        except Exception as e:
            print(f"Error starting print job: {e}")
            return False

    def get_status(self):
        if not self.is_connected():
            print("Printer is not connected.")
            return False
        try:
            status = self.client.get_status()
            return status
        except Exception as e:
            print(f"Error fetching print status: {e}")
            return False