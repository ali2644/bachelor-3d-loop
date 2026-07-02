from pyniryo import NiryoRobot

ROBOT_IP = "10.8.170.41"
WORKSPACE_NAME = "workspace_1"   # ggf. anpassen

robot = NiryoRobot(ROBOT_IP)
robot.calibrate_auto()
robot.update_tool()

print("Workspaces:")
print(robot.get_workspace_list())

print("Starte Vision Pick...")

success, shape, color = robot.vision_pick(
    WORKSPACE_NAME,
    height_offset=0.0
)

print("success:", success)
print("shape:", shape)
print("color:", color)

robot.move_to_home_pose()
robot.close_connection()