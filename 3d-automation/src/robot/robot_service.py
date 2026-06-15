from pyniryo import NiryoRobot, JointsPosition

ABOVE_PRINT = JointsPosition(-1.5059147693110253, -0.5701427709795098, 0.6339743653225944, -0.01831511586483492, -0.2071800599543545, 0.01083051910499222)
PICK_PRINT = JointsPosition(-1.5043928422032862, -0.9806930802676318, 0.21584932708081705, 0.08446159692350319, -0.2930829840759501, -0.0443927892588909)
PLACE_POSITION = JointsPosition(1.390312516716397, -0.8761618207071876, 0.19766997759204408, -0.013713173501177955, -0.29461696486383593, -0.04285880847100509)
HOME_POSITION = JointsPosition(0.00535884867385672, 0.05098500322023225, -1.0506453539703642, 0.04151013486270516, -0.29461696486383593, -0.04132482768311929)


robot = NiryoRobot("10.8.170.41")

try:
    robot.calibrate_auto()
    robot.update_tool()

    
    robot.open_gripper(max_torque_percentage=100, hold_torque_percentage=30)
    robot.move(ABOVE_PRINT)
    robot.move(PICK_PRINT)
    #robot.grasp_with_tool()
    robot.close_gripper(
    max_torque_percentage=100,
    hold_torque_percentage=80
    )
    robot.move(ABOVE_PRINT)
    robot.move(PLACE_POSITION)
    robot.release_with_tool()
    robot.move(HOME_POSITION)

    joints_read = robot.get_joints()
    print("Aktuelle Joints:")
    print(joints_read)

    #robot.move_home()

finally:
    robot.close_connection()