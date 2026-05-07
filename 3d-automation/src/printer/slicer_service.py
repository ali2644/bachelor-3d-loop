import subprocess


PRUSASLICER_PATH = r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"
GCODEDIR_PATH = r"C:\Users\User\IdeaProjects\bachelor-3d-loop\3d-automation\data\gcode\output.gcode"

class SlicerService:

    def __init__(self, slicer_path):
        self.slicer_path = slicer_path


    def send_stl_to_slicer(self,stl_file_path, profile, gcode_file_path):
        #command = "{}\\prusa-slicer-console.exe -g --load {} {}".format(PRUSASLICER_PATH,profile, stl_file_path)
        command = [
        self.slicer_path,
        "-g",
        "--load",
        profile,
        stl_file_path,
    "--output",
        gcode_file_path
        ]
        completed_process = subprocess.run(command, capture_output=True, text=True) # check=True -> wenn der Befehl fehlschlägt, wirft Pyhton ein Exception
        print("Slicing completed with return code:", completed_process.returncode)
        print("Standard Output:", completed_process.stdout)
        print("Standard Error:", completed_process.stderr)



if __name__ == "__main__": # This block will only execute if this script is run directly, and not when imported as a module.
    stl_file_path = r"C:\Users\User\IdeaProjects\bachelor-3d-loop\3d-automation\data\models\3003_Brick_2_x_2\3003.stl"
    profile = r"C:\Users\User\IdeaProjects\bachelor-3d-loop\3d-automation\config\slicer_profile.ini"
    slicer = SlicerService(PRUSASLICER_PATH)
    slicer.send_stl_to_slicer(stl_file_path, profile, GCODEDIR_PATH)
