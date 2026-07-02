# Robot Positions Documentation

## Goal

This document describes the fixed robot positions used for the first printer-to-robot integration prototype.

The setup consists of:
- Prusa Mini+ printer
- Niryo Ned2 robot arm
- Quality station

The goal is that the robot moves safely from its home position to the print bed, picks up the printed part, and places it in the quality station.

---

## Coordinate System

The robot coordinate system is based on the Niryo Ned2 reference frame.

All positions must be tested slowly before they are used in the automatic process.

---

## Defined Positions

| Name | Purpose | Status | Risk |
|---|---|---|---|
| HOME_POSITION | Start and end position | TODO | Low |
| PRINTER_SAFE_POSITION | Safe position near printer | TODO | Medium |
| PRINT_BED_APPROACH_POSITION | Position above printed part | TODO | Medium |
| PICK_POSITION | Position to grip the part | TODO | High |
| BREAK_OFF_POSITION | Position to remove part from bed | TODO | High |
| PICK_LIFT_POSITION | Lifted position after gripping | TODO | Medium |
| QUALITY_STATION_APPROACH_POSITION | Safe position near quality station | TODO | Medium |
| PLACE_POSITION | Final placing position | TODO | Medium |

---

## Safety Rules

- The robot must never move directly from HOME_POSITION to PICK_POSITION.
- The robot must always move through safe approach positions.
- First tests must be done without gripping the part.
- First tests must be done with low speed.
- The pick position is considered dangerous until it has been tested several times.
- The robot must not touch the print bed, nozzle, or printer frame.

---

## Open Questions

- How can the robot remove the part if it sticks to the print bed?
- Is a special gripping geometry needed on the printed part?
- Does the part need to cool down before removal?
- Is a break-off movement safe for the printer and the robot?