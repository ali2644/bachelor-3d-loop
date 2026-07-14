from __future__ import annotations

import logging
import sys

from qs.sj220_exceptions import (
    SJ220ConnectionError,
    SJ220DeviceError,
    SJ220Error,
    SJ220ProtocolError,
    SJ220ResultError,
    SJ220StateError,
    SJ220TimeoutError,
)
from qs.sj220_service import SJ220Service


DEVICE_ERROR_HINTS: dict[str, str] = {
    "007": (
        "Detektorposition, Werkstückposition und "
        "Messbereich prüfen."
    ),
    "018": (
        "Die Startposition des Detektors ist ungültig."
    ),
    "022": (
        "Prüfen, ob der Detektor korrekt angeschlossen ist."
    ),
    "030": (
        "Der gesendete Befehl ist für das SJ-220 ungültig."
    ),
    "031": (
        "Befehlsformat und abschließendes CR-Zeichen prüfen."
    ),
    "032": (
        "Mindestens ein übergebener Befehlswert ist ungültig."
    ),
    "071": (
        "SPC-Verbindung und eingestellten Ausgabemodus prüfen."
    ),
    "101": (
        "Für den angefragten Parameter existiert kein "
        "Berechnungsergebnis."
    ),
    "102": (
        "Das berechnete Ergebnis liegt außerhalb "
        "des zulässigen Bereichs."
    ),
    "103": (
        "Die Messung wurde aufgrund eines Overrange "
        "abgebrochen."
    ),
}


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    try:
        with SJ220Service(
            port="/dev/ttyUSB0",
            baudrate=38400,
        ) as quality_station:
            report = quality_station.measure(
                required_parameters=("Ra", "Rz"),
            )

        print("\nMessung erfolgreich")
        print("=" * 50)

        for result in report.results:
            print(
                f"{result.parameter}: "
                f"{result.value} {result.unit}"
            )

        print("-" * 50)
        print(
            f"Messdauer: "
            f"{report.duration_seconds:.2f} Sekunden"
        )

        result_values = report.as_dict()

        print(f"Ra für Orchestrator: {result_values['Ra']}")
        print(f"Rz für Orchestrator: {result_values['Rz']}")

        return 0

    except SJ220DeviceError as error:
        print("\nSJ-220 hat einen Gerätefehler gemeldet.")
        print(error)

        hint = DEVICE_ERROR_HINTS.get(error.code)

        if hint is not None:
            print(f"Hinweis: {hint}")

        return 2

    except SJ220ConnectionError as error:
        print("\nVerbindungsfehler")
        print(error)
        print(
            "Prüfe Kabel, Port, Berechtigungen und "
            "ob das SJ-220 eingeschaltet ist."
        )
        return 3

    except SJ220TimeoutError as error:
        print("\nZeitüberschreitung")
        print(error)
        return 4

    except SJ220StateError as error:
        print("\nUngültiger Gerätezustand")
        print(error)
        return 5

    except SJ220ResultError as error:
        print("\nUngültiges oder unvollständiges Messergebnis")
        print(error)
        return 6

    except SJ220ProtocolError as error:
        print("\nProtokollfehler")
        print(error)
        return 7

    except SJ220Error as error:
        print("\nAllgemeiner SJ-220-Fehler")
        print(error)
        return 8

    except KeyboardInterrupt:
        print("\nProgramm wurde vom Benutzer abgebrochen.")
        return 130

    except Exception:
        logging.exception(
            "Unexpected error outside the SJ-220 error handling."
        )
        return 99


if __name__ == "__main__":
    sys.exit(main())