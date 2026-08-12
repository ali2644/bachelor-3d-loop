from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from robot.robot_positions import ALL_POSITIONS, RobotPosition, RobotStation


SRC_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = SRC_DIR / "docs" / "ROBOT_POSITIONS.md"


def format_joints(position: RobotPosition) -> str:
    return ", ".join(f"{value:.12f}" for value in position.joints)


def build_documentation() -> str:
    grouped: dict[RobotStation, list[RobotPosition]] = defaultdict(list)

    for position in ALL_POSITIONS:
        grouped[position.station].append(position)

    lines = [
        "# Dokumentation der Roboterpositionen",
        "",
        "Diese Datei wird aus `robot_positions.py` erzeugt. "
        "Positionswerte und Beschreibungen sollen daher nur dort geändert werden.",
        "",
        "## Allgemeine Hinweise",
        "",
        "- Alle Werte sind Gelenkwinkel des Niryo Ned2 in Radiant.",
        "- Der Aufbau aus Drucker, Roboter und Qualitätsstation ist mechanisch fixiert.",
        "- Die Positionen dürfen nur nach einem erneuten sicheren Einlernvorgang geändert werden.",
        "- Schiebebewegungen werden mit reduzierter Armgeschwindigkeit ausgeführt.",
        "- Vor automatischen Gesamttests neue oder geänderte Positionen einzeln testen.",
        "",
        "## Ablaufübersicht",
        "",
        "```text",
        "HOME",
        "→ PRINTER_SAFE",
        "→ PRINTER_PICK",
        "→ PRINTER_BREAK_OFF",
        "→ PRINTER_BREAK_OFF_1",
        "→ PRINTER_OUTSIDE",
        "→ TRANSFER_CLEARANCE",
        "→ QS_SAFE",
        "→ QS_PART_RELEASE",
        "→ QS_SAFE",
        "→ QS_ALIGNMENT_ORIENTATION",
        "→ QS_ALIGNMENT_CONTACT",
        "→ QS_ALIGNMENT_END",
        "→ QS_SAFE",
        "→ QS_FINAL_PUSH_CONTACT",
        "→ QS_FINAL_PUSH_TARGET",
        "→ QS_FINAL_PUSH_CONTACT",
        "→ QS_SAFE",
        "→ QS_LIFT_LEVER_GRIP",
        "→ QS_PART_UNDER_PROBE",
        "→ QS_LIFT_LEVER_END",
        "→ QS_PART_SHIFT_END",
        "→ QS_SAFE",
        "→ HOME",
        "```",
        "",
    ]

    station_order = (
        RobotStation.GENERAL,
        RobotStation.PRINTER,
        RobotStation.QUALITY_STATION,
    )

    for station in station_order:
        lines.extend(
            [
                f"## {station.value}",
                "",
            ]
        )

        for position in grouped[station]:
            lines.extend(
                [
                    f"### `{position.name}`",
                    "",
                    f"**Zweck:** {position.purpose}",
                    "",
                ]
            )

            if position.movement_note:
                lines.extend(
                    [
                        f"**Bewegungshinweis:** {position.movement_note}",
                        "",
                    ]
                )

            lines.extend(
                [
                    "**Gelenkwerte:**",
                    "",
                    "```python",
                    f"{position.name} = JointsPosition(",
                ]
            )

            for value in position.joints:
                lines.append(f"    {value!r},")

            lines.extend(
                [
                    ")",
                    "```",
                    "",
                ]
            )

    return "\n".join(lines)


def main() -> None:
    OUTPUT_FILE.write_text(build_documentation(), encoding="utf-8")
    print(f"Documentation written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()