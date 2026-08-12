"""Run one automatic printer pickup test with recorded joint positions.

Copy this file to ``src/robot/manual_test_printer_side_pickup.py`` and run it
from the project root, for example::

    PYTHONPATH=src python3 -m robot.manual_test_printer_side_pickup --speed 5

The script executes exactly one complete pickup sequence without asking for
keyboard confirmation. It stops at PRINTER_OUTSIDE while holding the part.

Keep the robot's emergency stop reachable throughout every real test.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from robot.robot_positions import RobotPosition, RobotStation
from robot.robot_service import (
    GRIPPER_SETTLING_TIME_SECONDS,
    ROBOT_IP,
    RobotService,
)


LOGGER = logging.getLogger(__name__)

DEFAULT_TEST_SPEED_PERCENT = 5
MAX_TEST_SPEED_PERCENT = 30


HOME_ORIGINAL = RobotPosition(
    name="HOME_ORIGINAL",
    joints=(
        0.009924629997073886,
        0.3479143782035235,
        -1.34,
        0.015432461468649183,
        -0.09059752007504551,
        0.10747130874178756,
    ),
    station=RobotStation.GENERAL,
    purpose="Urspruengliche Home-Position ohne gedrehten Greifer.",
    movement_note="Ausgangsposition fuer den manuellen Druckertest.",
)

PRINTER_SAFE_ORIGINAL = RobotPosition(
    name="PRINTER_SAFE_ORIGINAL",
    joints=(
        -1.6109277397450201,
        0.61,
        -1.3142459215575717,
        -0.059732597137747145,
        -0.09980140480235944,
        0.10900528952967337,
    ),
    station=RobotStation.PRINTER,
    purpose="Urspruengliche sichere Position vor dem Drucker.",
    movement_note="Hier wird der Greifer vor der Annaeherung geoeffnet.",
)

PRINTER_PICK = RobotPosition(
    name="PRINTER_PICK",
    joints=(
        -1.5256998217116329,
        -0.6296808194458285,
        -0.968838281270886,
        0.08906353928716015,
        1.5200823072048775,
        -0.013713173501177955,
    ),
    station=RobotStation.PRINTER,
    purpose="Greifposition am gedruckten Bauteil nach mechanischem Umbau.",
    movement_note="An dieser Position wird der Greifer geschlossen.",
)

PRINTER_BREAK_OFF = RobotPosition(
    name="PRINTER_BREAK_OFF",
    joints=(
        -1.306542318197209,
        -0.5701427709795098,
        -0.9476290402006509,
        0.09519946243870248,
        1.492470653022936,
        9.265358979293481e-05,
    ),
    station=RobotStation.PRINTER,
    purpose="Abknickposition nach dem Greifen und mechanischen Umbau.",
    movement_note="Nur aus PRINTER_PICK mit geschlossenem Greifer anfahren.",
)

PRINTER_OUTSIDE = RobotPosition(
    name="PRINTER_OUTSIDE",
    joints=(
        -0.9047535617540983,
        -0.3141169323459576,
        -0.7491711416148796,
        0.08906353928716015,
        1.1013055521120974,
        -0.030586962167920007,
    ),
    station=RobotStation.PRINTER,
    purpose="Position ausserhalb des Druckerbereichs nach mechanischem Umbau.",
    movement_note="Nur aus PRINTER_BREAK_OFF mit gehaltenem Bauteil anfahren.",
)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def format_joints(position: RobotPosition) -> str:
    return ", ".join(f"{value:.6f}" for value in position.joints)


def move_to_recorded_position(
    robot_service: RobotService,
    position: RobotPosition,
) -> None:
    """Log one recorded target and move to it immediately."""
    print(f"\nAktuell: {robot_service.get_current_joints()}")
    print(f"Naechstes Ziel: {position.name}")
    print(f"Gelenkwerte: {format_joints(position)}")
    robot_service.move_to(position)


def open_gripper(robot_service: RobotService) -> None:
    LOGGER.info("Opening gripper in PRINTER_SAFE.")
    robot_service.open_gripper(
        max_torque_percentage=70,
        hold_torque_percentage=50,
        settling_time_seconds=GRIPPER_SETTLING_TIME_SECONDS,
    )


def grip_part(robot_service: RobotService) -> None:
    LOGGER.info("Closing gripper in PRINTER_PICK.")
    robot_service.grip_printed_part_securely()


def test_pickup_sequence(robot_service: RobotService) -> None:
    """Run one automatic pickup sequence and stop outside the printer."""
    LOGGER.info("Starting one automatic printer pickup test.")

    move_to_recorded_position(robot_service, HOME_ORIGINAL)
    move_to_recorded_position(robot_service, PRINTER_SAFE_ORIGINAL)
    open_gripper(robot_service)
    move_to_recorded_position(robot_service, PRINTER_PICK)
    grip_part(robot_service)
    move_to_recorded_position(robot_service, PRINTER_BREAK_OFF)
    move_to_recorded_position(robot_service, PRINTER_OUTSIDE)

    LOGGER.info(
        "Pickup test completed outside the printer. The robot keeps holding "
        "the part; no automatic return movement is performed."
    )


def test_speed(value: str) -> int:
    speed = int(value)

    if not 1 <= speed <= MAX_TEST_SPEED_PERCENT:
        raise argparse.ArgumentTypeError(
            f"speed must be between 1 and {MAX_TEST_SPEED_PERCENT}"
        )

    return speed


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one automatic printer pickup test.",
    )
    parser.add_argument(
        "--robot-ip",
        default=ROBOT_IP,
        help=f"Niryo robot IP address (default: {ROBOT_IP})",
    )
    parser.add_argument(
        "--speed",
        type=test_speed,
        default=DEFAULT_TEST_SPEED_PERCENT,
        help=(
            "maximum arm velocity percentage during the test "
            f"(default: {DEFAULT_TEST_SPEED_PERCENT}; "
            f"maximum: {MAX_TEST_SPEED_PERCENT})"
        ),
    )
    return parser.parse_args(arguments)


def print_safety_banner(speed: int) -> None:
    print(
        "\nAUTOMATISCHER ROBOTERTEST: EIN DURCHLAUF\n"
        "- Ablauf: HOME -> SAFE -> Greifer oeffnen -> PICK -> Greifer "
        "schliessen -> BREAK_OFF -> OUTSIDE.\n"
        "- Der Lauf startet ohne Tastatureingabe oder Pause.\n"
        "- Die eingelernten Gelenkwerte werden ohne Grenzpruefung verwendet.\n"
        "- Arbeitsraum raeumen und Kamera-/Druckerabstand pruefen.\n"
        "- Not-Aus waehrend des gesamten Tests erreichbar halten.\n"
        "- Bei Abbruch erfolgt keine automatische Roboterbewegung.\n"
        f"- Testgeschwindigkeit: {speed} %.\n"
    )


def run(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    configure_logging()
    print_safety_banner(args.speed)

    try:
        with RobotService(args.robot_ip) as robot_service:
            robot_service.initialize()

            with robot_service.use_arm_speed(args.speed):
                test_pickup_sequence(robot_service)

    except KeyboardInterrupt as error:
        LOGGER.warning(
            "Test cancelled: %s No automatic robot movement was performed "
            "after cancellation.",
            error,
        )
        return 2
    except Exception:
        LOGGER.exception(
            "Robot test failed. The robot will not perform an automatic "
            "recovery movement."
        )
        return 1

    LOGGER.info("Manual robot test completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())