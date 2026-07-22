#Ablaufsteuerung für die Automatisierung von 3D-Druckern

#Beispielhafter Ablauf:
#while True:
#    params = optimizer.get_next()

#    printer.print(params)

#    printer.wait_until_finished()

#    robot.pick()

#    value = qs.measure()

#    optimizer.update(value)


# orchestrator.py

import time


class PrintOrchestrator:
    def __init__(self, slicer_service,printer_service):
        self.printer_service = printer_service
        self.slicer_service = slicer_service

    def run_single_print_cycle(self, stl_path, profile_path, gcode_path):
        if not self.printer_service.wait_until_connected():
            raise Exception("Printer is not connected")
        
        if not self.slicer_service.send_stl_to_slicer(stl_path, profile_path, gcode_path):
            raise Exception("Slicing failed")

        if not self.printer_service.upload_gcode(gcode_path):
            raise Exception("G-code upload failed")

        if not self.printer_service.start_print_job():
            raise Exception("Print start failed")

        self.wait_until_print_finished()


    def wait_until_print_finished(self, poll_interval_seconds=30):
        while True:
            state = self.printer_service.get_printer_state()
            print("Current printer state:", state)

            if state == "FINISHED":
                print("Print finished successfully.")
                return True

            if state in ["STOPPED", "ERROR", "ATTENTION"]:
                raise Exception(f"Print stopped with state: {state}")

            time.sleep(poll_interval_seconds)