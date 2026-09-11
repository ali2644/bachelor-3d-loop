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
    joints=(-1.4785200813717223, -0.3171468239274198, -1.2748573309985638, 0.12127713583275845, 1.4295774407196247, 0.02770430777173427),
    #joints=(-1.6109277397450201,0.61,-1.3142459215575717,-0.059732597137747145,-0.09980140480235944,0.10900528952967337,),
    
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
    joints=(-1.5896207602366732, -0.6080164157477866, -0.9764130102245414, -0.027519000592148846, 1.5338881342958484, -0.009111231137520992),
    #joints=(-1.7311599812564054,-0.6352854399809461,-0.9536888233635752,-0.33584913895716273,1.5231502687806489,0.013898480680763825,),
    
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
        1.7327461159576845,
        0.61,
        -0.6961480389392919,
        0.004694595953449898,
        -0.09673344322658828,
        0.02770430777173427,
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
    joints=(1.7829697105130733, -0.014157665781204143, -0.8309782143143579, 0.16269461710567068, 0.8589365876261663, -0.1548394059866567

    ),
    #Original: 1.746443459927336,-0.06415087687532972,-0.774925220057308,0.030772269347505876,0.8221210487169106,0.04899473162254786,),

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
# Quality station: Recovery movements
# -------------------------------------------------------------------------
QS_SAFE_RECOVERY: Final = RobotPosition(
    name="QS_SAFE_RECOVERY",
    joints=(
        1.7494873141428138,
        -0.11717397955091746,
        -0.19621592799803622,
        0.21178200231801148,
        0.3189753502904207,
        -0.16250930992608525,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Sichere Zwischenposition für die Recovery nach einem "
        "fehlgeschlagenen finalen Einschub."
    ),
    movement_note=(
        "Nur innerhalb der getesteten Recovery-Sequenz verwenden."
    ),
)

QS_RECOVERY: Final = RobotPosition(
    name="QS_RECOVERY",
    joints=(
        1.746443459927336,
        -0.23685469701867257,
        -0.3749795313043034,
        0.18110238656029853,
        0.41101419756355906,
        -0.16557727150185642,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Aufräumposition zum Entfernen beziehungsweise Verschieben "
        "eines falsch eingelegten Bauteils."
    ),
    movement_note=(
        "Langsam aus QS_SAFE_RECOVERY anfahren und anschließend "
        "zu QS_FINAL_PUSH_CONTACT fahren."
    ),
)
QS_RECOVERY_CLEAR_PART: Final = RobotPosition(
    name="QS_RECOVERY_CLEAR_PART",
    joints=(
        1.7494873141428138,
        0.44184101722885033,
        -1.0748844866220615,
        0.11207325110544453,
        0.6119656807765779,
        0.016966442256534986,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Entfernt das fehlerhaft positionierte Bauteil vollständig "
        "aus dem Arbeitsbereich der Qualitätsstation."
    ),
    movement_note=(
        "Nur während der Recovery direkt aus "
        "QS_FINAL_PUSH_CONTACT anfahren."
    ),
)

# TODO: movement_note-Texte der QS-Positionen überarbeiten,
# sobald die endgültige Bewegungssequenz vollständig getestet ist.
# # -------------------------------------------------------------------------
# Quality station: lift lever and Mitutoyo probe height
# -------------------------------------------------------------------------

QS_LIFT_LEVER_GRIP: Final = RobotPosition(
    name="QS_LIFT_LEVER_GRIP",
    joints=(
        1.2289882432960568,
        -0.41561830032493974,
        -0.2446941933014306,
        -0.35425690841179014,
        0.7837715290197695,
        1.7442288094157665,
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
        1.4207510588711778,
        -0.3322962818347305,
        -0.252268922255086,
        -0.22847048380516766,
        0.5168588719276683,
        1.7380928862642242,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Positioniert das Bauteil unter der Mitutoyo-Messnadel."
    ),
    movement_note=(
        "Langsam aus QS_LIFT_LEVER_GRIP anfahren und vor der "
        "Rauheitsmessung drei Sekunden warten."
    ),
)

QS_LIFT_LEVER_APPROACH: Final = RobotPosition(
    name="QS_LIFT_LEVER_APPROACH",
    joints=(
        1.918421223101849,
        -0.3565354144864278,
        -0.009877595738113643,
        0.06298586589310418,
        -0.11053927031755917,
        -1.7287036943573246,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Sichere Zwischenposition zum Anfahren und Verlassen der "
        "Hebelendposition."
    ),
    movement_note=(
        "Aus QS_SAFE anfahren. Anschließend langsam zu "
        "QS_LIFT_LEVER_END fahren und auf derselben getesteten "
        "Bahn zu dieser Position zurückkehren."
    ),
)

QS_LIFT_LEVER_END: Final = RobotPosition(
    name="QS_LIFT_LEVER_END",
    joints=(
        1.7160049177725551,
        -0.3050272576015711,
        -0.05684091525077695,
        0.1059373279539022,
        -0.1534907323783572,
        -1.7655192332665801,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Endposition der Hebelbewegung nach der Rauheitsmessung."
    ),
    movement_note=(
        "Nur langsam aus QS_LIFT_LEVER_APPROACH anfahren und "
        "anschließend auf derselben getesteten Bahn zurückfahren."
    ),
)


# -------------------------------------------------------------------------
# Quality station: part shift after measurement
# -------------------------------------------------------------------------

QS_PART_SHIFT_APPROACH: Final = RobotPosition(
    name="QS_PART_SHIFT_APPROACH",
    joints=(
        1.1331068355084963,
        -0.44743216193029245,
        -0.13713304215952427,
        -0.4723734290789845,
        0.736218124595315,
        1.8623453300829609,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Sichere Zwischenposition zum Anfahren und Verlassen der "
        "Bauteilverschiebung."
    ),
    movement_note=(
        "Aus QS_SAFE anfahren. Anschließend langsam zu "
        "QS_PART_SHIFT_END fahren und auf derselben getesteten "
        "Bahn zu dieser Position zurückkehren."
    ),
)

QS_PART_SHIFT_END: Final = RobotPosition(
    name="QS_PART_SHIFT_END",
    joints=(
        1.3020407444675315,
        -0.38986422188251146,
        -0.28105289227897656,
        -0.21926659907785373,
        0.7776356058682272,
        1.70434530893074,
    ),
    station=RobotStation.QUALITY_STATION,
    purpose=(
        "Endposition für das Verschieben des Bauteils nach Abschluss "
        "der Rauheitsmessung."
    ),
    movement_note=(
        "Nur langsam aus QS_PART_SHIFT_APPROACH anfahren und "
        "anschließend auf derselben getesteten Bahn zurückfahren."
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
    QS_SAFE_RECOVERY,
    QS_RECOVERY,
    QS_RECOVERY_CLEAR_PART,
    QS_LIFT_LEVER_GRIP,
    QS_PART_UNDER_PROBE,
    QS_LIFT_LEVER_APPROACH,
    QS_LIFT_LEVER_END,
    QS_PART_SHIFT_APPROACH,
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