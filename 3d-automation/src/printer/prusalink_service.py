import PrusaLinkPy
import time 
import os

class PrusaLinkService:
    REMOTE_GCODE_PATH = "FOLDER/demo.gcode"
    def __init__(self, printer_ip, api_key):
        self.printer_ip = printer_ip
        self.api_key = api_key
        self.client = PrusaLinkPy.PrusaLinkPy(printer_ip, api_key)

    def is_connected(self):
        try:
            r = self.client.get_printer()
            return r.status_code == 200
        except Exception as e:
            print(f"Connection error: {e}")
            return False
      
        
    def upload_gcode(self, gcode_file_path):
        if not os.path.isfile(gcode_file_path):
            print(f"G-code file not found: {gcode_file_path}")
            return False
        # TODO: remove is_connected() check.
        if not self.is_connected():
            print("Printer is not connected.")
            return False
        try: 
            r = self.client.put_gcode(
                gcode_file_path,
                self.REMOTE_GCODE_PATH,
                printAfterUpload=False,
                overwrite=True)
            
            print ("Upload: ", r.status_code, r.text)
            time.sleep(3) # Give the printer some time to process the uploaded file TODO: use get_transfer_status instead of sleep

            return r.status_code in [200, 201,204]
        except Exception as e:
            print(f"Error uploading G-code: {e}")
            return False    



    def start_print_job(self):
        # TODO: remove is_connected() check.
        if not self.is_connected():
            print("Printer is not connected.")
            return False   
        try:
            r = self.client.post_gcode(self.REMOTE_GCODE_PATH)
            print("Start:", r.status_code, r.text)
            return r.status_code in [200, 201, 204]
        except Exception as e:
            print(f"Error starting print job: {e}")
            return False

    def get_status(self):
        
        try:
            status = self.client.get_status()
            return status.json()
        except Exception as e:
            print(f"Error fetching print status: {e}")
            return False
        
    def wait_until_connected(self, retries=10, delay_seconds=3):
        for attempt in range(1, retries +1):           
            if self.is_connected():
                print("Successfully connected to the printer.")
                return True
            print(f"Attempt {attempt} of {retries} failed. Retrying in {delay_seconds} seconds...")
            time.sleep(delay_seconds)
            
        print("Failed to connect to the printer after multiple attempts.")
        return False