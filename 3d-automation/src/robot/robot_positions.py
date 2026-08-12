from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Final, Iterable

from pyniryo import JointsPosition


JointValues = tuple[float, float, float, float, float, float]


class RobotStation(Enum):
    """Physical area to which a robot position belongs."""

    GENERAL = "Allgemein"
    PRINTER = "Druckerstation"
    QUALITY_STATION = "Qualitätsstation"


@dataclass(frozen=True, slots=True)
class RobotPosition:
    """
    Immutable description of one taught robot waypoint.

    The numerical joint values, semantic name and documentation are kept
    together so that the service and the documentation use one source.
    """

    name: str
    joints: JointValues
    station: RobotStation
    purpose: str
    movement_note: str = ""

    def __post_init__(self) -> None:
        if len(self.joints) != 6:
            raise ValueError(
                f"{self.name} must contain exactly six joint values."
            )

    def to_joints_position(self) -> JointsPosition:
        """Create the PyNiryo object required by robot.move()."""
        return JointsPosition(*self.joints)

    def alias(
        self,
        *,
        name: str,
        purpose: str,
        movement_note: str = "",
    ) -> "RobotPosition":
        """
        Give tested joint values another semantic role.

        This is useful when one physical waypoint is intentionally reused,
        for example HOME as TRANSFER_CLEARANCE.
        """
        return replace(
            self,
            name=name,
            purpose=purpose,
            movement_note=movement_note,
        )


# -------------------------------------------------------------------------
# General positions
# -------------------------------------------------------------------------

HOME: Final = RobotPosition(
    name="HOME",
    joints=(
        0.009924629997073886,
        0.3479143782035235,
        -1.34,
        0.015432461468649183,
        -0.09059752007504551,
        0.10747130874178756,
    ),
    station=RobotStation.GENERAL,
    purpose=(
        "Definierte Ausgangs- und Endposition des Roboters. Der Arm ist "
        "kompakt und befindet sich außerhalb der engen Stationsbereiche."
    ),
    movement_note=(
        "Wird zusätzlich als getestete, kollisionsfreie Übergangsposition "
        "zwischen Drucker und Qualitätsstation verwendet."
    ),
)

TRANSFER_CLEARANCE: Final = HOME.alias(
    name="TRANSFER_CLEARANCE",
    purpose=(
        "Kollisionsfreie Zwischenposition für den Wechsel von der "
        "Druckerstation zur Qualitätsstation."
    ),
    movement_note="Verwendet bewusst dieselben Gelenkwerte wie HOME.",
)


# -------------------------------------------------------------------------
# Printer station
# -------------------------------------------------------------------------

PRINTER_SAFE: Final = RobotPosition(
    name="PRINTER_SAFE",
    joints=(
        -1.6109277397450201,
        0.61,
        -1.3142459215575717,
        -0.059732597137747145,
        -0.09980140480235944,
        0.10900528952967337,
    ),
    station=RobotStation.PRINTER,
    purpose=(
        "Sichere Position vor dem Drucker. Von hier beginnt die direkte "
        "kontrollierte Annäherung an die neue Greifposition."
    ),
    movement_note=(
        "Der Roboter befindet sich außerhalb der unmittelbaren Kollisionszone "
        "von Druckbett, Düse und Bauteil."
    ),
)

PRINTER_PICK: Final = RobotPosition(
    name="PRINTER_PICK",
    joints=(
        -1.7311599812564054,
        -0.6352854399809461,
        -0.9536888233635752,
        -0.33584913895716273,
        1.5231502687806489,
        0.013898480680763825,
    ),
    station=RobotStation.PRINTER,
    purpose=(
        "Neue diagonale Greifposition am gedruckten Bauteil nach dem "
        "mechanischen Umbau des Greifers."
    ),
    movement_note=(
        "Mit geöffnetem Greifer direkt aus PRINTER_SAFE anfahren. An dieser "
        "Position wird der Greifer geschlossen."
    ),
)


PRINTER_BREAK_OFF: Final = RobotPosition(
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
    purpose=(
        "Neue Abknickbewegung, mit der das diagonal gegriffene Bauteil von "
        "der Druckplatte gelöst wird."
    ),
    movement_note=(
        "Nur mit geschlossenem Greifer und ausgehend von PRINTER_PICK "
        "anfahren."
    ),
)
PRINTER_BREAK_OFF_1: Final = RobotPosition(
    name="PRINTER_BREAK_OFF_1",
    joints=(
        -1.5637479994051093,
        -0.6352854399809461,
        -0.9748980644338103,
        -0.14716950204722856,
        1.556897846114133,
        0.04151013486270516,
    ),
    station=RobotStation.PRINTER,
    purpose=(
        "Neue Abknickbewegung, mit der das diagonal gegriffene Bauteil von "
        "der Druckplatte gelöst wird."
    ),
    movement_note=(
        "Nur mit geschlossenem Greifer und ausgehend von PRINTER_PICK "
        "anfahren."
    ),
)

PRINTER_OUTSIDE: Final = RobotPosition(
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
    purpose=(
        "Position außerhalb des Druckerbereichs nach dem Abknicken des "
        "Bauteils."
    ),
    movement_note=(
        "Nur mit gehaltenem Bauteil direkt aus PRINTER_BREAK_OFF anfahren. "
        "Von hier beginnt der Transport zur Qualitätsstation."
    ),
)


# -------------------------------------------------------------------------
# Quality station: depositing the part
# -------------------------------------------------------------------------

QS_SAFE: Final = RobotPosition(
    name="QS_SAFE",
    joints=(
        1.609470020230821,
        0.4221467219493463,
        -0.06290069841370127,
        0.1059373279539022,
        -0.9051413184423214,
        -0.12569377101682955,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Sichere Position vor der Qualitätsstation. Sie trennt weiträumige "
        "Transportbewegungen von den engen Bewegungen innerhalb der QS."
    ),
    movement_note=(
        "Diese Position wird vor und nach mehreren QS-Teilsequenzen verwendet."
    ),
)

QS_PART_RELEASE: Final = RobotPosition(
    name="QS_PART_RELEASE",
    joints=(
        1.5759876238605615,
        -0.0095231536646244095,
        -0.7343205995221904,
        -0.1302957133804865,
       0.6917326817466312,
        0.030772269347505876,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Ablageposition, an der das transportierte Bauteil in der "
        "Qualitätsstation losgelassen wird."
    ),
    movement_note=(
        "Nach dem Öffnen kurz warten, damit der Arm das Bauteil nicht durch "
        "eine unmittelbar folgende Bewegung verschiebt."
    ),
)

# -------------------------------------------------------------------------
# Quality station: first alignment of the released part
# -------------------------------------------------------------------------

QS_ALIGNMENT_ORIENTATION: Final = RobotPosition(
    name="QS_ALIGNMENT_ORIENTATION",
    joints=(
        1.5425052274903028,
        0.61,
        -1.1476018845771532,
        0.07353842422871804,
        0.5628782955642375,
        1.6429860774153142,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Position zum Drehen und Ausrichten des Greifers für die erste "
        "Produktverschiebung."
    ),
    movement_note=(
        "Diese Bewegung erfolgt mit normaler Armgeschwindigkeit; erst der "
        "Kontakt mit dem Produkt wird langsam ausgeführt."
    ),
)

QS_ALIGNMENT_CONTACT: Final = RobotPosition(
    name="QS_ALIGNMENT_CONTACT",
    joints=(
        1.5303298106283898,
        0.08279886482558485,
        -0.8309782143143579,
        -0.08887823210757428,
        0.8006453176865116,
        1.532539460687548,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Kontaktposition für die erste Produktverschiebung nach dem Ablegen."
    ),
    movement_note=(
        "Ab dieser Position wird die reduzierte Schiebegeschwindigkeit verwendet."
    ),
)

QS_ALIGNMENT_END: Final = RobotPosition(
    name="QS_ALIGNMENT_END",
    joints=(
        1.5288078835206513,
        -0.017187557362666306,
        -0.7415964126612242,
        -0.09961609762277401,
        0.8251890102926822,
        1.5356074222633196,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Endposition der ersten Produktverschiebung. Das Bauteil ist danach "
        "für die finale Einschubbewegung vorpositioniert."
    ),
    movement_note="Nur langsam aus QS_ALIGNMENT_CONTACT anfahren.",
)

QS_ALIGNMENT_RETREAT: Final = RobotPosition(
    name="QS_ALIGNMENT_RETREAT",
    joints=(
        1.609470020230821,
        0.4221467219493463,
        -0.06290069841370127,
        0.1059373279539022,
        -0.9051413184423214,
        -0.12569377101682955,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Neue Rückzugsposition unmittelbar nach der ersten "
        "Produktverschiebung. Sie ersetzt an dieser Stelle QS_SAFE."
    ),
    movement_note="Direkt aus QS_ALIGNMENT_END anfahren.",
)


# -------------------------------------------------------------------------
# Quality station: final horizontal push
# -------------------------------------------------------------------------

QS_FINAL_PUSH_CONTACT: Final = RobotPosition(
    name="QS_FINAL_PUSH_CONTACT",
    joints=(
        1.746443459927336,
        -0.06415087687532972,
        -0.774925220057308,
        0.030772269347505876,
        0.8221210487169106,
        0.04899473162254786,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Kontaktposition für das finale horizontale Einschieben des Bauteils "
        "in die Messvorrichtung."
    ),
    movement_note=(
        "Mit normaler Geschwindigkeit annähern; die einzelne Bewegung zu "
        "QS_FINAL_PUSH_TARGET langsam ausführen."
    ),
)
QS_FINAL_PUSH_TARGET: Final = RobotPosition(
    name="QS_FINAL_PUSH_TARGET",
    joints=(
        1.7007856466951643,
        -0.31108704076449545,
        -0.37952436867649664,
        -0.0031606151655640957,
        0.6917326817466312,
        -0.026170326983848913,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Einzige Zielposition des finalen Produktschubs. Sie ersetzt die "
        "früheren Zwischen-, End- und Finalpositionen."
    ),
    movement_note=(
        "Langsam aus QS_FINAL_PUSH_CONTACT anfahren und anschließend auf "
        "derselben getesteten Bahn zu QS_FINAL_PUSH_CONTACT zurückfahren."
    ),
)


# -------------------------------------------------------------------------
# Quality station: lift lever and Mitutoyo probe height
# -------------------------------------------------------------------------

QS_LIFT_LEVER_GRIP: Final = RobotPosition(
    name="QS_LIFT_LEVER_GRIP",
    joints=(
        1.402702881177702,
        -0.3041169323459576,
        -0.2308957276631326,
        -0.2928976768963647,
        0.5291307182307534,
        0.25013152201515254,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Start- und Greifposition am Hubhebel der Qualitätsstation."
    ),
    movement_note=(
        "Greifer vor dem Anfahren öffnen und an dieser Position schließen."
    ),
)

QS_PART_UNDER_PROBE: Final = RobotPosition(
    name="QS_PART_UNDER_PROBE",
    joints=(
        1.6186015828772553,
        -0.2883628539035292,
        -0.22651484381265785,
        -0.11802386707740142,
        0.4263540054424153,
        0.1059373279539022,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Zwischenposition der Hebelbewegung, durch die das Bauteil unter "
        "der Mitutoyo-Messnadel positioniert wird."
    ),
    movement_note=(
        "Langsam anfahren und vor dem nächsten Hebelschritt drei Sekunden warten."
    ),
)

QS_LIFT_LEVER_END: Final = RobotPosition(
    name="QS_LIFT_LEVER_END",
    joints=(
        1.3674836101003112,
        -0.3065422033923022,
        -0.1901561448351119,
        -0.1118879439258591,
        0.33124719659350577,
        0.05684994274156141,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Endposition der Hebelbewegung. Der Hubmechanismus bringt das "
        "Bauteil auf die erforderliche Höhe für die Rauheitsmessung."
    ),
    movement_note=(
        "Langsam anfahren, drei Sekunden halten und danach langsam zum "
        "Hebelstart zurückfahren."
    ),
)

QS_PART_SHIFT_END: Final = RobotPosition(
    name="QS_PART_SHIFT_END",
    joints=(
        1.4046633504402222,
        -0.33023649867180615,
        -0.2765080549067833,
        -0.3011015616236786,
        0.6100918921098358,
        0.1254227708025856,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Endposition der Bauteilverschiebung nach der Bewegung "
        "über QS_LIFT_LEVER_END."
    ),
    movement_note=(
        "Langsam anfahren und anschließend den Greifer öffnen."
    ),
)


ALL_POSITIONS: Final[tuple[RobotPosition, ...]] = (
    HOME,
    TRANSFER_CLEARANCE,
    PRINTER_SAFE,
    PRINTER_PICK,
    PRINTER_BREAK_OFF,
    PRINTER_BREAK_OFF_1,    
    PRINTER_OUTSIDE,
    QS_SAFE,
    QS_PART_RELEASE,
    QS_ALIGNMENT_ORIENTATION,
    QS_ALIGNMENT_CONTACT,
    QS_ALIGNMENT_END,
    QS_FINAL_PUSH_CONTACT,
    QS_FINAL_PUSH_TARGET,
    QS_LIFT_LEVER_GRIP,
    QS_PART_UNDER_PROBE,
    QS_LIFT_LEVER_END,
    QS_PART_SHIFT_END,
)


def validate_position_names(
    positions: Iterable[RobotPosition] = ALL_POSITIONS,
) -> None:
    """Fail early when two documented positions accidentally share a name."""
    names = [position.name for position in positions]

    if len(names) != len(set(names)):
        raise ValueError("Robot position names must be unique.")


validate_position_names()