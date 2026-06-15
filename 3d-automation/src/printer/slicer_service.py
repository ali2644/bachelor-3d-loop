import subprocess
from pathlib import Path



PROJECT_ROOT = Path(__file__).resolve().parents[3]

PRUSASLICER_PATH = Path.home() / "apps/prusaslicer/PrusaSlicer-2.9.1-x86_64.AppImage"

STL_PATH = PROJECT_ROOT / "bachelor-3d-loop/3d-automation/data/models/3003_Brick_2_x_2/3003.stl"
PROFILE_PATH = PROJECT_ROOT / "bachelor-3d-loop/3d-automation/config/slicer_profile_flat.ini"
GCODE_PATH = PROJECT_ROOT / "bachelor-3d-loop/3d-automation/data/gcode/output.gcode"

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
        try:
            completed_process = subprocess.run(command, capture_output=True, text=True) # check=True -> wenn der Befehl fehlschlägt, wirft Pyhton ein Exception
            print("Slicing completed with return code:", completed_process.returncode)
            print("Standard Output:", completed_process.stdout)
        except subprocess.CalledProcessError as e:
            print("Slicing failed with error:", e)
            return False

        return True




if __name__ == "__main__":
    slicer = SlicerService(PRUSASLICER_PATH)
    slicer.send_stl_to_slicer(STL_PATH, PROFILE_PATH, GCODE_PATH)