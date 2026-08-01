# Stabiler End-to-End-Einzelzyklus

## Ziel

Ein vollständiger Zyklus wird mit festen Druckparametern ausgeführt:

1. Vorbedingungen prüfen
2. STL mit PrusaSlicer in G-Code umwandeln
3. G-Code über PrusaLink hochladen
4. Druck starten und Status überwachen
5. Erst nach `PRINTING -> FINISHED` den Roboter starten
6. Bauteil entnehmen, in der QS ausrichten und unter die Messnadel anheben
7. Messung über die Raspberry-Pi-API starten und auf Ra/Rz warten
8. Erst nach gültigen Messwerten die Hebelsequenz beenden
9. Ra, Rz, Profil-Hash und Druckparameter als CSV speichern

Der Optimierer ist noch nicht Teil dieses Meilensteins.

## Sicherheitsverhalten

- `preflight` startet keinen Druck und bewegt den Roboter nicht.
- Ein altes `FINISHED` wird nicht als Ende des neuen Drucks akzeptiert. Der
  Orchestrator muss vorher `PRINTING` oder `PAUSED` gesehen haben.
- `STOPPED`, `ERROR` und `ATTENTION` brechen den Zyklus ab.
- Nach zu vielen fehlgeschlagenen Statusabfragen wird abgebrochen.
- Nach einem Roboterfehler wird keine Messung gestartet.
- Eine fehlgeschlagene Messanfrage wird nicht automatisch wiederholt, weil
  unklar sein kann, ob sich der SJ-220 bereits bewegt.
- Bei einem Messfehler wird die Hebelsequenz nicht fortgesetzt. Der Roboter
  bleibt an der Messposition stehen und muss nach Prüfung des realen Zustands
  kontrolliert zurückgesetzt werden.
- Nach einem Bewegungsfehler fährt der Roboter nicht automatisch nach HOME.
  Erst Ursache und reale Armposition prüfen und anschließend kontrolliert
  zurücksetzen.

Der Not-Aus des Roboters muss erreichbar sein. Vor `robot-qs` und `full`
müssen Drucker, Roboter und QS mechanisch in der eingelernten Anordnung stehen.

## Einmalige Einrichtung am Hauptrechner

Im Ordner `3d-automation`:

```bash
python -m pip install -r requirements.txt
cp config/end_to_end.env.example config/end_to_end.env
chmod 600 config/end_to_end.env
nano config/end_to_end.env
```

In `config/end_to_end.env` müssen mindestens der neue PrusaLink-API-Key, die
Raspberry-Pi-IP und der lokale Pfad zur PrusaSlicer-AppImage eingetragen
werden. Der früher im Quellcode gespeicherte API-Key sollte nicht
weiterverwendet werden.

Konfiguration in die aktuelle Shell laden:

```bash
set -a
source config/end_to_end.env
set +a
export PYTHONPATH="$PWD/src"
```

Der QS-Dienst auf dem Raspberry Pi bleibt wie bisher als
`qs-station.service` aktiv.

## Testreihenfolge

### 1. Softwaretests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Alle Tests müssen mit `OK` enden.

### 2. Preflight ohne Hardwarebewegung

```bash
PYTHONPATH=src python -m main --mode preflight
```

Erwartung:

- STL und Slicerprofil wurden gefunden.
- Die PrusaSlicer-AppImage ist vorhanden und ausführbar.
- Die QS-API antwortet mit `status=ok`.
- Die Roboterverbindung wurde durch das reine Auslesen der Gelenke geprüft.
- PrusaLink ist erreichbar.
- Der Drucker meldet `IDLE` oder `FINISHED`.
- Kein Druck und keine Roboterbewegung wird gestartet.

### 3. Roboter-QS-Teilkette

Ein vorhandenes Testbauteil muss genau an der eingelernten Position auf dem
Druckbett liegen.

```bash
PYTHONPATH=src python -m main --mode robot-qs
```

Diesen Test zunächst unter ständiger Beobachtung und danach insgesamt dreimal
erfolgreich durchführen. Nach jedem Lauf prüfen:

- Bauteil korrekt gegriffen und abgelöst
- gerade in der QS abgelegt und ausgerichtet
- korrekt unter der Messnadel positioniert
- gültige Werte für Ra und Rz zurückgegeben
- neue Zeile in `data/results/cycles.csv`

### 4. Vollständiger Einzelzyklus

```bash
PYTHONPATH=src python -m main --mode full
```

Der Standardwert `PART_COOLING_SECONDS=60` ist nur ein Startwert. Vor dem
unbeaufsichtigten Betrieb muss praktisch geprüft werden, wie lange das
Bauteil nach Druckende für ein reproduzierbares Abknicken abkühlen muss.

## Abnahmekriterien

Der Einzelzyklus gilt erst als stabil, wenn:

- drei `robot-qs`-Durchläufe hintereinander erfolgreich sind,
- ein vollständiger Zyklus mit einem Befehl endet,
- die beobachtete Druckerfolge `PRINTING -> FINISHED` enthält,
- zwischen Drucker, Roboter und QS kein manueller Eingriff nötig ist,
- Ra und Rz plausibel und endlich sind,
- `data/results/cycles.csv` Parameter und Messwerte enthält,
- jeder provozierte Softwarefehler die nachfolgenden Schritte verhindert.

## Relevante Konfiguration

| Variable | Bedeutung | Standard |
|---|---|---:|
| `PRINT_POLL_SECONDS` | Abstand der Statusabfragen | 15 s |
| `PRINT_START_TIMEOUT_SECONDS` | Zeit bis `PRINTING`/`PAUSED` | 180 s |
| `PRINT_TIMEOUT_SECONDS` | Maximale Gesamtdruckdauer | 8 h |
| `MAX_STATUS_ERRORS` | Aufeinanderfolgende fehlende Statusantworten | 5 |
| `PART_COOLING_SECONDS` | Wartezeit vor Roboterstart | 60 s |

Die CSV enthält auch fehlgeschlagene Versuche. So bleiben Fehlerphase und
Ursache für die spätere Auswertung nachvollziehbar.

## Bewusste Grenze dieses Meilensteins

Nach der Messung bleibt das Bauteil zunächst in der QS. Der Projektpitch zeigt
als späteren Schritt das robotergestützte Ablegen im Bauteillager. Diese
Sequenz darf erst ergänzt werden, nachdem sichere Lager-, Annäherungs- und
Rückzugspositionen mechanisch eingelernt und einzeln getestet wurden. Sie ist
für den wiederholten Optimierungsloop notwendig, aber nicht für den Nachweis
des ersten End-to-End-Einzelzyklus.