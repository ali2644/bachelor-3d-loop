from ast import For

from pyniryo import NiryoRobot, JointsPosition, NiryoRobotException

ROBOT_IP = "10.8.170.41"

HOME_POSITION = JointsPosition(
    0.049494734798289475, 
    0.4569904751361611, 
    -1.1385122098327667, 
    0.01083051910499222, 
    -0.9143452031696353, 
    0.09980140480235944,
)

PRINTER_SAFE_POSITION = JointsPosition(
    -1.496783206664591, 
    0.61, 
    0.01284659112285258, 
    -0.1302957133804865, 
    -0.6765781810473608, 
    0.09366548165081712,
)

PRINT_BED_APPROACH_POSITION = JointsPosition(
    -4.528462005280789, 1.6750068908839477, 0.741535516464501, 0.02463634619596311, -1.7426948286278816, -0.04746075083466206,
)
PRINT_BED_APPROACH_POSITION_2 = JointsPosition(-1.551572582543197, -0.38228949292885606, -1.2324388488580935, 0.02156838462019195, 1.4433832678105953, 0.06145188510521837,)

PICK_POSITION = JointsPosition(
    -1.5607041451896313, -0.535299017792695, -0.7673504911036526, -0.012179192713292153, 1.087499725021127, 0.06451984668098998,
)

PICK_POSITION_2 = JointsPosition(
-1.53026560303485, -0.5080299935595355, -0.17349174113707, 0.015432461468649183, -0.7087917775929591, -0.0075772503496351895,
)

BREAK_OFF_RIGHT_POSITION = JointsPosition(
    -1.7889932113504896, -0.30351231181084004, -0.49163035719059645, -0.23307242616882462, -0.09213150086293131, 0.11207325110544453,
)

BREAK_OFF_LEFT_POSITION = JointsPosition(
    -1.606361958421803,
    -1.0791645566651518,
    0.7082067090684172,
    0.03384023092327704,
    -0.6643063347442757,
    -0.002975307985978226,
)
TEMP_PLACE_POSITION = JointsPosition(
    1.3948782980396142,
    -0.6186210362829042,
    -0.2552988138365482,
    0.285413080136522,
    -0.6551024500169618,
    0.0031606151655640957,
)

HELPER_POSITION = JointsPosition(
    -1.4663446645098097,
    -1.0306862913617576,
    0.6370042569040566,
    0.007762557529221059,
    -0.5691995258953657,
    0.1028693663781306
)
PICK_LIFT_POSITION = None
QUALITY_STATION_APPROACH_POSITION = None
PLACE_POSITION = None



#damit die Positionen wo Fehler passieren, direkt erkannt werden und nicht erst am Ende, wenn die ganze Sequenz durchgelaufen
def move_to(robot, position, name):
    print(f"Moving to {name}...")
    try:
        robot.move(position)
        print(f"Reached {name}")
    except NiryoRobotException as e:
        print(f"Error while moving to {name}: {e}")
        raise

def pickup_from_printer_test(robot):

    move_to(robot, HOME_POSITION, "HOME_POSITION")

    robot.grasp_with_tool()

    move_to(robot, PRINTER_SAFE_POSITION, "PRINTER_SAFE_POSITION")
    #move_to(robot, PRINT_BED_APPROACH_POSITION, "PRINT_BED_APPROACH_POSITION2")

    robot.open_gripper(max_torque_percentage=100, hold_torque_percentage=30)

    #robot.clear_collision_detected()

    move_to(robot, PICK_POSITION_2, "PICK_POSITION")
    robot.grasp_with_tool()

    #move_to(robot, BREAK_OFF_RIGHT_POSITION, "BREAK_OFF_RIGHT_POSITION")
    #move_to(robot, BREAK_OFF_LEFT_POSITION, "BREAK_OFF_LEFT_POSITION")
    move_to(robot, PRINTER_SAFE_POSITION, "PRINTER_SAFE_POSITION")

    #for x in range(10):
     #   move_to(robot, BREAK_OFF_RIGHT_POSITION, "BREAK_OFF_RIGHT_POSITION")
      #  move_to(robot, BREAK_OFF_LEFT_POSITION, "BREAK_OFF_LEFT_POSITION")

    #move_to(robot, PRINT_BED_APPROACH_POSITION, "PRINT_BED_APPROACH_POSITION")

    move_to(robot, TEMP_PLACE_POSITION, "TEMP_PLACE_POSITION")

    robot.open_gripper(max_torque_percentage=100, hold_torque_percentage=30)
    move_to(robot, HOME_POSITION, "HOME_POSITION")
    robot.grasp_with_tool()


def main():
    try:
        robot = NiryoRobot(ROBOT_IP)
        robot.calibrate_auto()
        robot.update_tool()
        robot.clear_collision_detected()

        robot.move(BREAK_OFF_RIGHT_POSITION)
        #pickup_from_printer_test(robot)

        
        #robot.open_gripper(max_torque_percentage=100, hold_torque_percentage=30)
        #robot.move(ABOVE_PRINT)
        #robot.move(PICK_PRINT)
        #robot.grasp_with_tool()
        #robot.close_gripper(
        #max_torque_percentage=100,
        #hold_torque_percentage=80
        #)
        #robot.move(ABOVE_PRINT)
        #robot.move(PLACE_POSITION)
        #robot.release_with_tool()
        #robot.move(HOME_POSITION)

        joints_read = robot.get_joints()
        print("Aktuelle Joints:")
        print(joints_read)

        #robot.move_home()

    finally:
        robot.close_connection()


if __name__ == "__main__":
    main()