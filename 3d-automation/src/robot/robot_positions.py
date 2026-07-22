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
        for example PRINTER_APPROACH as PRINTER_RETREAT.
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
        "Sichere Position vor dem Drucker. Von hier beginnt die "
        "kontrollierte Annäherung an das Druckbett."
    ),
    movement_note=(
        "Der Roboter befindet sich außerhalb der unmittelbaren Kollisionszone "
        "von Druckbett, Düse und Bauteil."
    ),
)

PRINTER_APPROACH: Final = RobotPosition(
    name="PRINTER_APPROACH",
    joints=(
        -1.6307127921456277,
        0.182785287013836,
        -0.2068205485331538,
        -0.022917058228491882,
        -0.11360723189333033,
        0.11053927031755917,
    ),
    station=RobotStation.PRINTER,
    purpose=(
        "Annäherungsposition unmittelbar vor dem Greifen des gedruckten "
        "Bauteils."
    ),
    movement_note=(
        "Der Greifer ist geöffnet. Von dieser Position wird nur noch die "
        "kurze Bewegung zur Greifposition ausgeführt."
    ),
)

PRINTER_PICK: Final = RobotPosition(
    name="PRINTER_PICK",
    joints=(
        -1.5880988331289343,
        -0.46409656562833435,
        -0.12198358425221345,
        0.029238288559620074,
        -1.0186558967458583,
        -0.09654813604700241,
    ),
    station=RobotStation.PRINTER,
    purpose=(
        "Exakte Greifposition am gedruckten Bauteil beziehungsweise an "
        "dessen Haltegeometrie."
    ),
    movement_note="An dieser Position wird der Greifer geschlossen.",
)

PRINTER_BREAK_OFF: Final = RobotPosition(
    name="PRINTER_BREAK_OFF",
    joints=(
        -1.7783397215963161,
        -0.43985743297663704,
        -0.10531918055417155,
        -0.004509288773864029,
        -1.0278597814731723,
        -0.09808211683488821,
    ),
    station=RobotStation.PRINTER,
    purpose=(
        "Seitliche Abknickbewegung, mit der das gegriffene Bauteil von "
        "der Druckplatte gelöst wird."
    ),
    movement_note=(
        "Nur mit geschlossenem Greifer und ausgehend von PRINTER_PICK "
        "anfahren."
    ),
)

PRINTER_RETREAT: Final = PRINTER_APPROACH.alias(
    name="PRINTER_RETREAT",
    purpose=(
        "Rückzugsposition nach dem Abknicken, bevor der Roboter wieder "
        "PRINTER_SAFE anfährt."
    ),
    movement_note=(
        "Die getestete Annäherungsposition wird bewusst auch für den "
        "Rückzug verwendet."
    ),
)


# -------------------------------------------------------------------------
# Quality station: depositing the part
# -------------------------------------------------------------------------

QS_SAFE: Final = RobotPosition(
    name="QS_SAFE",
    joints=(
        1.5425052274903028,
        0.5009239030673623,
        -0.49920508614425185,
        0.11053927031755917,
        -0.9987141465033456,
        -0.09348017447123125,
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
        1.6581716876784705,
        -0.46258161983760326,
        0.4915694609938732,
        -0.059732597137747145,
        -1.5509472301421758,
        0.1519567515904714,
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

QS_RETRACT: Final = RobotPosition(
    name="QS_RETRACT",
    joints=(
        1.5881630407224745,
        -0.3247215528810752,
        1.186929578939438,
        0.13201500134795818,
        -1.5356074222633196,
        0.007762557529221059,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Rückzugsposition nach dem Ablegen beziehungsweise nach dem "
        "Loslassen des Hubhebels."
    ),
    movement_note=(
        "Der Greifer entfernt sich kontrolliert aus dem engen Bereich der QS."
    ),
)


# -------------------------------------------------------------------------
# Quality station: first alignment of the released part
# -------------------------------------------------------------------------

QS_ALIGNMENT_ORIENTATION: Final = RobotPosition(
    name="QS_ALIGNMENT_ORIENTATION",
    joints=(
        1.5409833003825635,
        0.5509171141614879,
        -0.49920508614425185,
        0.026170326983848913,
        -0.7302675086233581,
        -1.7655192332665801,
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
        1.5683779883218665,
        0.16006110015286984,
        -0.8385529432680132,
        -0.012364499892878023,
        0.6610530659889187,
        -1.6289949431447581,
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
        1.5333736648438685,
        0.022201033196341702,
        -0.6961480389392919,
        -0.1302957133804865,
        0.5858880073825219,
        -1.4955386145987073,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Endposition der ersten Produktverschiebung. Das Bauteil ist danach "
        "für die finale Einschubbewegung vorpositioniert."
    ),
    movement_note="Nur langsam aus QS_ALIGNMENT_CONTACT anfahren.",
)


# -------------------------------------------------------------------------
# Quality station: final horizontal push
# -------------------------------------------------------------------------

QS_FINAL_PUSH_CONTACT: Final = RobotPosition(
    name="QS_FINAL_PUSH_CONTACT",
    joints=(
        1.4344484028408293,
        -0.35805036027715886,
        0.33855993613003443,
        0.12434509740852961,
        -1.557083153293719,
        -0.12722775180471535,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Kontaktposition für das finale horizontale Einschieben des Bauteils "
        "in die Messvorrichtung."
    ),
    movement_note=(
        "Mit normaler Geschwindigkeit annähern; die eigentliche Bewegung "
        "ab der nächsten Position langsam ausführen."
    ),
)

QS_FINAL_PUSH_INTERMEDIATE: Final = RobotPosition(
    name="QS_FINAL_PUSH_INTERMEDIATE",
    joints=(
        1.4938035600426525,
        -0.7216373500526175,
        0.9081795534449195,
        0.04457809643847632,
        -1.722753078385368,
        -0.04899473162254786,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Zwischenposition für einen kontrollierten und kollisionsfreien "
        "Schubweg innerhalb der Messvorrichtung."
    ),
    movement_note="Teil der langsamen Schiebebewegung.",
)

QS_FINAL_PUSH_END: Final = RobotPosition(
    name="QS_FINAL_PUSH_END",
    joints=(
        1.4983693413658696,
        -0.748906374285777,
        0.917269228189306,
        0.05378198116579025,
        -1.5248695567481199,
        0.009296538317106862,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Vorletzte Schubposition unmittelbar vor der endgültigen horizontalen "
        "Produktposition."
    ),
    movement_note="Teil der langsamen Schiebebewegung.",
)

QS_FINAL_PUSH: Final = RobotPosition(
    name="QS_FINAL_PUSH",
    joints=(
        1.4983693413658696,
        -0.4913655898614938,
        0.450665924644134,
        0.038442173286934,
        -1.0968889169280263,
        -0.05513065477409018,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Endgültige horizontale Schubposition des Bauteils in der "
        "Messvorrichtung."
    ),
    movement_note=(
        "Das Bauteil soll danach korrekt vor dem Hubmechanismus liegen."
    ),
)

QS_FINAL_PUSH_RETREAT: Final = RobotPosition(
    name="QS_FINAL_PUSH_RETREAT",
    joints=(
        1.4755404347497838,
        0.007051575289030998,
        -0.06593058999516344,
        0.16576257868144229,
        -1.4558404212932667,
        -0.22693650301728185,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Rückzugsposition nach dem finalen Produktschub."
    ),
    movement_note=(
        "Wird über QS_FINAL_PUSH_INTERMEDIATE angefahren, damit der Greifer "
        "nicht am positionierten Produkt hängen bleibt."
    ),
)


# -------------------------------------------------------------------------
# Quality station: lift lever and Mitutoyo probe height
# -------------------------------------------------------------------------

QS_LIFT_LEVER_GRIP: Final = RobotPosition(
    name="QS_LIFT_LEVER_GRIP",
    joints=(
        1.4770623618575232,
        -0.6489199520975258,
        0.8051632396752064,
        0.05531596195367605,
        -1.297840400141045,
        -0.03518890453157697,
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
        1.5333736648438685,
        -0.6428601689346015,
        0.800618402303013,
        0.07985965455984623,
        -1.2993743809289309,
        0.006228576741335257,
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
        1.4664088721033495,
        -0.8534376338462214,
        1.1763249584043203,
        -0.22080057986573953,
        -1.5678210188089179,
        -0.12262580944105839,
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


ALL_POSITIONS: Final[tuple[RobotPosition, ...]] = (
    HOME,
    TRANSFER_CLEARANCE,
    PRINTER_SAFE,
    PRINTER_APPROACH,
    PRINTER_PICK,
    PRINTER_BREAK_OFF,
    PRINTER_RETREAT,
    QS_SAFE,
    QS_PART_RELEASE,
    QS_RETRACT,
    QS_ALIGNMENT_ORIENTATION,
    QS_ALIGNMENT_CONTACT,
    QS_ALIGNMENT_END,
    QS_FINAL_PUSH_CONTACT,
    QS_FINAL_PUSH_INTERMEDIATE,
    QS_FINAL_PUSH_END,
    QS_FINAL_PUSH,
    QS_FINAL_PUSH_RETREAT,
    QS_LIFT_LEVER_GRIP,
    QS_PART_UNDER_PROBE,
    QS_LIFT_LEVER_END,
)


def validate_position_names(
    positions: Iterable[RobotPosition] = ALL_POSITIONS,
) -> None:
    """Fail early when two documented positions accidentally share a name."""
    names = [position.name for position in positions]

    if len(names) != len(set(names)):
        raise ValueError("Robot position names must be unique.")


validate_position_names()