from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

from pyniryo import JointsPosition, NiryoRobot, NiryoRobotException

from robot.robot_positions import (
    HOME,
    PRINTER_BREAK_OFF,
    PRINTER_BREAK_OFF_1,
    PRINTER_OUTSIDE,
    PRINTER_PICK,
    PRINTER_SAFE,
    QS_ALIGNMENT_CONTACT,
    QS_ALIGNMENT_END,
    QS_ALIGNMENT_ORIENTATION,
    QS_ALIGNMENT_RETREAT,
    QS_FINAL_PUSH_CONTACT,
    QS_FINAL_PUSH_TARGET,
    QS_LIFT_LEVER_END,
    QS_LIFT_LEVER_GRIP,
    QS_PART_SHIFT_END,
    QS_PART_RELEASE,
    QS_PART_UNDER_PROBE,
    QS_LIFT_LEVER_APPROACH,
    QS_PART_SHIFT_APPROACH,
    QS_RECOVERY,
    QS_RECOVERY_CLEAR_PART,
    QS_SAFE,
    QS_SAFE_RECOVERY,
    TRANSFER_CLEARANCE,
    RobotPosition,
)


ROBOT_IP = "10.8.170.41"

NORMAL_ARM_SPEED_PERCENT = 50
PUSH_ARM_SPEED_PERCENT = 20

GRIPPER_SETTLING_TIME_SECONDS = 1.0
PART_RELEASE_SETTLING_TIME_SECONDS = 1.5
LEVER_STEP_WAIT_SECONDS = 3.0

PICK_POSITION_SETTLING_TIME_SECONDS = 0.8

PRE_GRIP_MAX_TORQUE_PERCENT = 30
PRE_GRIP_HOLD_TORQUE_PERCENT = 20
PRE_GRIP_SETTLING_TIME_SECONDS = 0.8

FINAL_GRIP_MAX_TORQUE_PERCENT = 80
FINAL_GRIP_HOLD_TORQUE_PERCENT = 75
FINAL_GRIP_SETTLING_TIME_SECONDS = 0.5

LOGGER = logging.getLogger(__name__)

RECOVERY_ARM_SPEED_PERCENT = 10

EXPECTED_FINAL_PUSH_FAILURE_FRAGMENTS = (
    "collision",
    "motor not able to follow",
)


class RobotService:
    """Controls the fixed printer-to-quality-station handling sequence."""

    def __init__(self, robot_ip: str = ROBOT_IP) -> None:
        self._robot = NiryoRobot(robot_ip)

    def __enter__(self) -> "RobotService":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def initialize(self) -> None:
        LOGGER.info("Initializing Niryo robot.")

        self._robot.calibrate_auto()
        self._robot.update_tool()
        self._robot.clear_collision_detected()
        self._robot.set_arm_max_velocity(NORMAL_ARM_SPEED_PERCENT)

        LOGGER.info("Niryo robot initialized.")

    def close(self) -> None:
        try:
            self._robot.close_connection()
            LOGGER.info("Robot connection closed.")
        except NiryoRobotException:
            LOGGER.exception("Could not close the robot connection cleanly.")

    def check_connection(self) -> None:
        """Read the current joints without calibrating or moving the arm."""
        try:
            self._robot.get_joints()
        except NiryoRobotException:
            LOGGER.exception("Robot connection check failed.")
            raise

        LOGGER.info("Robot connection check passed.")

    def move_to(self, position: RobotPosition) -> None:
        """
        Move to one documented waypoint.

        The log name and PyNiryo joint object are derived from the same
        RobotPosition, so callers cannot accidentally pass the wrong name.
        """
        LOGGER.info("Moving to %s.", position.name)

        try:
            self._robot.move(position.to_joints_position())
        except NiryoRobotException:
            LOGGER.exception("Movement to %s failed.", position.name)
            raise

        LOGGER.info("Reached %s.", position.name)

    def open_gripper(
        self,
        *,
        max_torque_percentage: int = 100,
        hold_torque_percentage: int = 30,
        settling_time_seconds: float = 0.0,
    ) -> None:
        LOGGER.info("Opening gripper.")

        try:
            self._robot.open_gripper(
                max_torque_percentage=max_torque_percentage,
                hold_torque_percentage=hold_torque_percentage,
            )
        except NiryoRobotException:
            LOGGER.exception("Could not open the gripper.")
            raise

        if settling_time_seconds > 0:
            time.sleep(settling_time_seconds)

    def close_gripper(
        self,
        *,
        max_torque_percentage: int = 100,
        hold_torque_percentage: int = 80,
        settling_time_seconds: float = 0.0,
    ) -> None:
        LOGGER.info(
            "Closing gripper with max torque %s%% and hold torque %s%%.",
            max_torque_percentage,
            hold_torque_percentage,
        )

        try:
            self._robot.close_gripper(
                max_torque_percentage=max_torque_percentage,
                hold_torque_percentage=hold_torque_percentage,
            )
        except NiryoRobotException:
            LOGGER.exception("Could not close the gripper.")
            raise

        if settling_time_seconds > 0:
            time.sleep(settling_time_seconds)

    @contextmanager
    def use_arm_speed(self, speed_percentage: int) -> Iterator[None]:
        """Temporarily change arm speed and always restore normal speed."""
        self._robot.set_arm_max_velocity(speed_percentage)

        try:
            yield
        finally:
            try:
                self._robot.set_arm_max_velocity(NORMAL_ARM_SPEED_PERCENT)
            except NiryoRobotException:
                LOGGER.exception(
                    "Could not restore normal arm speed after a movement error."
                )

    def grip_printed_part_securely(self) -> None:
        time.sleep(PICK_POSITION_SETTLING_TIME_SECONDS)

        self.close_gripper(
            max_torque_percentage=PRE_GRIP_MAX_TORQUE_PERCENT,
            hold_torque_percentage=PRE_GRIP_HOLD_TORQUE_PERCENT,
            settling_time_seconds=PRE_GRIP_SETTLING_TIME_SECONDS,
        )

        self.close_gripper(
            max_torque_percentage=FINAL_GRIP_MAX_TORQUE_PERCENT,
            hold_torque_percentage=FINAL_GRIP_HOLD_TORQUE_PERCENT,
            settling_time_seconds=FINAL_GRIP_SETTLING_TIME_SECONDS,
        )

    def transfer_part_from_printer_to_qs(self) -> None:
        """Pick, break off, transport and release one printed part."""
        LOGGER.info("Starting transfer from printer to quality station.")

        self.move_to(HOME)
        self.close_gripper()

        self.move_to(PRINTER_SAFE)

        self.open_gripper(
            max_torque_percentage=90,
            hold_torque_percentage=50,
            settling_time_seconds=GRIPPER_SETTLING_TIME_SECONDS,
        )

        self.move_to(PRINTER_PICK)

        self.grip_printed_part_securely()

        
        self.move_to(PRINTER_BREAK_OFF_1)
        self.move_to(PRINTER_BREAK_OFF)
            
        self.move_to(PRINTER_OUTSIDE)

        self.move_to(TRANSFER_CLEARANCE)
        self.move_to(QS_SAFE)
        self.move_to(QS_PART_RELEASE)

        self.open_gripper(
            max_torque_percentage=100,
            hold_torque_percentage=50,
            settling_time_seconds=PART_RELEASE_SETTLING_TIME_SECONDS,
        )


        self.move_to(QS_SAFE)

        # Compact tool shape for the following push movements.
        self.close_gripper()

        LOGGER.info("Part transferred to the quality station.")

    def align_part_in_qs(self) -> None:
        """Perform the first alignment of the released part."""
        LOGGER.info("Starting first quality-station alignment.")

        self.move_to(QS_ALIGNMENT_ORIENTATION)
        

        with self.use_arm_speed(PUSH_ARM_SPEED_PERCENT):
            self.move_to(QS_ALIGNMENT_CONTACT)
            self.move_to(QS_ALIGNMENT_END)
            self.move_to(QS_ALIGNMENT_CONTACT)


        self.move_to(QS_ALIGNMENT_RETREAT)

        LOGGER.info("First quality-station alignment completed.")

    @staticmethod
    def _is_expected_final_push_failure(error: Exception) -> bool:
        message = str(error).lower()
        return any(
            fragment in message
            for fragment in EXPECTED_FINAL_PUSH_FAILURE_FRAGMENTS
        )

    def recover_after_final_push_collision(self) -> None:
        """Clear the failed part after the push movement was aborted."""
        LOGGER.warning(
            "Starting QS recovery after the aborted final push."
        )

        with self.use_arm_speed(RECOVERY_ARM_SPEED_PERCENT):
            # The failed target movement stopped somewhere between CONTACT
            # and TARGET. First retreat on the same taught path.
            self.move_to(QS_FINAL_PUSH_CONTACT)
            self.move_to(QS_SAFE)
            self.move_to(QS_SAFE_RECOVERY)
            self.move_to(QS_RECOVERY)
            self.move_to(QS_FINAL_PUSH_CONTACT)
            self.move_to(QS_RECOVERY_CLEAR_PART)
            self.move_to(QS_SAFE)

        self.move_to(HOME)

        LOGGER.warning(
            "Final-push recovery completed; robot returned to HOME."
        )

    def push_part_into_measurement_fixture(self) -> bool:
        """
        Push the aligned part into its final horizontal position.

        Return False after a collision or trajectory-tracking error was
        handled by the complete recovery sequence.
        """
        LOGGER.info("Starting final product push.")

        self.move_to(QS_FINAL_PUSH_CONTACT)

        try:
            with self.use_arm_speed(PUSH_ARM_SPEED_PERCENT):
                self.move_to(QS_FINAL_PUSH_TARGET)

        except NiryoRobotException as error:
            if not self._is_expected_final_push_failure(error):
                raise

            LOGGER.warning(
                "Final push was aborted by collision detection or trajectory "
                "tracking. Clearing the collision state before recovery: %s",
                error,
            )

            # The failed MOVE command is already stopped by the robot. Clear
            # only its collision flag so the explicitly taught retreat can run.
            self._robot.clear_collision_detected()
            self.recover_after_final_push_collision()
            return False

        with self.use_arm_speed(PUSH_ARM_SPEED_PERCENT):
            self.move_to(QS_FINAL_PUSH_CONTACT)

        self.move_to(QS_SAFE)

        LOGGER.info("Part pushed into its final horizontal position.")
        return True

    def raise_part_to_probe_height(self) -> None:
        """
        Position the part under the Mitutoyo probe.

        The robot moves the lift mechanism to QS_PART_UNDER_PROBE and then
        returns to QS_SAFE. The part remains positioned under the probe so
        that the quality-station measurement can be started.

        No gripper action is required for this movement sequence.
        """
        LOGGER.info(
            "Starting movement for positioning the part under the "
            "Mitutoyo probe."
        )

        self.move_to(QS_SAFE)
        self.move_to(QS_LIFT_LEVER_GRIP)

        time.sleep(LEVER_STEP_WAIT_SECONDS)

        with self.use_arm_speed(PUSH_ARM_SPEED_PERCENT):
            self.move_to(QS_PART_UNDER_PROBE)

        self.move_to(QS_LIFT_LEVER_GRIP)
        self.move_to(QS_SAFE)

        #time.sleep(LEVER_STEP_WAIT_SECONDS)

        LOGGER.info(
            "Part positioned under the Mitutoyo probe; robot returned "
            "to QS_SAFE."
        )

    def complete_part_handling_after_measurement(self) -> None:
        """
        Complete the quality-station movements after a valid measurement.

        This method continues from QS_SAFE, operates the lift-lever end
        position, shifts the measured part and finally moves the robot home.

        It must not be called if the measurement failed or if no valid
        Ra and Rz values were returned. No gripper action is required.
        """
        LOGGER.info(
            "Measurement completed; continuing quality-station handling."
        )

        # Complete the lift-lever movement.
        self.move_to(QS_LIFT_LEVER_APPROACH)

        self.move_to(QS_LIFT_LEVER_END)

        #time.sleep(LEVER_STEP_WAIT_SECONDS)

        self.move_to(QS_LIFT_LEVER_APPROACH)
        self.move_to(QS_SAFE)

        # Shift the measured part.
        self.move_to(QS_PART_SHIFT_APPROACH)

        self.move_to(QS_PART_SHIFT_END)

        #time.sleep(LEVER_STEP_WAIT_SECONDS)

        self.move_to(QS_PART_SHIFT_APPROACH)
        self.move_to(QS_SAFE)
        self.move_to(HOME)

        LOGGER.info("Post-measurement robot handling completed.")

    def prepare_part_for_measurement(self) -> bool:
        """
        Execute the mechanical sequence before QS measurement.

        False means the final push failed, recovery completed and measurement
        must be skipped for this cycle.
        """
        LOGGER.info("Starting complete part-handling cycle.")

        self.transfer_part_from_printer_to_qs()
        self.align_part_in_qs()
        if not self.push_part_into_measurement_fixture():
            LOGGER.warning(
                "Part handling ended after final-push recovery."
            )
            return False

        self.raise_part_to_probe_height()

        #self.close_gripper()


        LOGGER.info("Part is ready for the Mitutoyo measurement.")
        return True

    def get_current_joints(self) -> JointsPosition:
        return self._robot.get_joints()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def main() -> None:
    configure_logging()

    with RobotService(ROBOT_IP) as robot_service:
        robot_service.initialize()
        robot_service.prepare_part_for_measurement()

        LOGGER.info(
            "Current joints: %s",
            robot_service.get_current_joints(),
        )


if __name__ == "__main__":
    main()