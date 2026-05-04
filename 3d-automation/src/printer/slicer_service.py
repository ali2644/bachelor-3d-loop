import subprocess


PRUSASLICER_PATH = r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"
GCODEDIR_PATH = r"C:\Users\User\IdeaProjects\bachelor-3d-loop\3d-automation\data\gcode\output.gcode"

def send_stl_to_slicer(stl_file_path, profile):
    # This function would contain the logic to send the STL file to the slicer software
    # and apply the specified profile settings. The implementation would depend on the
    # specific slicer software being used (e.g., Cura, PrusaSlicer, etc.) and may involve
    # using command-line interfaces, APIs, or other methods provided by the slicer.

    # Example pseudo-code:
    # 1. Check if the slicer software is installed and accessible.
    # 2. Use the slicer's command-line interface or API to load the STL file.
    # 3. Apply the profile settings to the slicer.
    # 4. Start the slicing process and monitor for completion.

    #command = "{}\\prusa-slicer-console.exe -g --load {} {}".format(PRUSASLICER_PATH,profile, stl_file_path)
    command = [
    PRUSASLICER_PATH,
    "-g",
    "--load",
    profile,
    stl_file_path,
   "--output",
    GCODEDIR_PATH
    ]
    completed_process = subprocess.run(command, capture_output=True, text=True) # check=True -> wenn der Befehl fehlschlägt, wirft Pyhton ein Exception
    print("Slicing completed with return code:", completed_process.returncode)
    print("Standard Output:", completed_process.stdout)
    print("Standard Error:", completed_process.stderr)



def upload_gcode_to_printer(gcode_file_path):
    # This function would contain the logic to upload the generated G-code file to the 3D printer.
    # The implementation would depend on the specific printer and its communication method (e.g., USB, SD card, network).

    # Example pseudo-code:
    # 1. Check if the printer is connected and accessible.
    # 2. Use the appropriate method to transfer the G-code file to the printer (e.g., copy to SD card, send via API).
    # 3. Verify that the file was successfully uploaded.

    pass  # Replace with actual implementation

def monitor_print_status():
    # This function would contain the logic to monitor the status of the 3D print job.
    # It could involve checking the printer's status through its API, serial communication,
    # or using a monitoring tool that provides real-time updates on the print job.

    # Example pseudo-code:
    # 1. Connect to the printer's API or serial interface.
    # 2. Continuously check for updates on the print job status (e.g., printing, paused, completed).
    # 3. Handle any events or notifications based on the status (e.g., send alerts, log progress).

    pass  # Replace with actual implementation

def start_print_job(stl_file_path, profile):
    # This function would contain the logic to start the print job after the G-code has been uploaded to the printer.
    # The implementation would depend on the specific printer and its communication method.

    # Example pseudo-code:
    # 1. Ensure that the G-code file has been successfully uploaded to the printer.
    # 2. Use the appropriate method to start the print job (e.g., send a command via API, press a button on the printer).
    # 3. Monitor for any errors or issues that may arise when starting the print job.

    pass  # Replace with actual implementation

def run_pipeline(stl_file_path, profile):
    # This function would orchestrate the entire process of sending the STL file to the slicer,
    # starting the print job, and monitoring its status.

    # Step 1: Send the STL file to the slicer and apply the profile settings.
    send_stl_to_slicer(stl_file_path, profile)
    # Step 2: Start the slicing process and wait for it to complete.
    # (This would be handled within the send_stl_to_slicer function.)

    upload_gcode_to_printer(GCODEDIR_PATH)

    start_print_job()

    # Step 3: Monitor the print job status until completion.
    status=monitor_print_status()
    print("Print job status:", status)

    if status == "FINISHED":
        print("Print job completed successfully.")


# Example usage:
# stl_file_path = "path/to/your/model.stl"
# profile = "your_slicer_profile"
# start_print_job(stl_file_path, profile)
stl_file_path = r"C:\Users\User\IdeaProjects\bachelor-3d-loop\3d-automation\data\models\3003_Brick_2_x_2\3003.stl"
profile = r"C:\Users\User\IdeaProjects\bachelor-3d-loop\3d-automation\config\slicer_profile.ini"
send_stl_to_slicer(stl_file_path, profile)
