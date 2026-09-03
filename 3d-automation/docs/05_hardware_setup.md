# 05 – Hardware-Setup

> **Gefahr von Sach- und Personenschäden:** Positionswerte sind an eine konkrete mechanische Anordnung gebunden. Nach Umbau, Transport, Werkzeugwechsel oder Firmwareänderung zuerst mit reduzierter Geschwindigkeit, freiem Arbeitsraum und erreichbarem Not-Aus validieren. Direkte Roboterskripte können sich schon beim Start kalibrieren und bewegen.

## Gemeinsame Voraussetzungen

Vor jeder Hardwareprüfung:

1. Drucker, Roboter, Raspberry Pi, SJ-220 und Kamera einschalten.
2. Hauptrechner, Drucker, Roboter und Pi in ein erreichbares Netz bringen.
3. Mechanische Befestigung von Drucker, QS-Station, Greifer, Taster und Kamera prüfen.
4. Druckerbett und komplette Roboterbahn räumen.
5. Not-Aus beziehungsweise sichere Abschaltmöglichkeit lokalisieren.
6. Erst Netzwerk- und Health-Checks, dann `preflight`, danach einzelne Mechanik und zuletzt einen Gesamtzyklus ausführen.

## Prusa MINI/MINI+

### Aufgabe und Verbindung

Der Drucker erhält den von PrusaSlicer erzeugten G-Code über PrusaLink. Der Hauptrechner baut eine unverschlüsselte HTTP-Verbindung zu `http://<PRINTER_IP>` auf; ein besonderer Port ist nicht konfiguriert, daher gilt Port 80.

Der Code bezeichnet das Zielgerät allgemein als Prusa-Drucker; das Basisprofil enthält `printer_model = MINIIS` und einen MINI-Modellcheck. Ob die konkrete Maschine MINI oder MINI+ ist, muss am Gerät bestätigt werden.

### Voraussetzungen und Prüfung

- PrusaLink muss aktiviert und im Netz erreichbar sein.
- Ein gültiger API-Key muss lokal als `PRUSALINK_API_KEY` gesetzt sein.
- Der vom Profil erwartete Düsendurchmesser, Werkstoff und Druckerzustand müssen zur Maschine passen.
- Der USB-Zielpfad aus `REMOTE_GCODE_PATH` muss beschreibbar sein.

**Arbeitsverzeichnis: `3d-automation/`, keine Bewegung**

```bash
curl --fail --show-error "http://${PRINTER_IP:-10.8.170.57}/api/printer" \
  -H "X-Api-Key: $PRUSALINK_API_KEY"
```

Der Orchestrator akzeptiert beim Preflight nur die Druckerzustände `IDLE` oder `FINISHED`. Er wartet beim realen Lauf zunächst auf `PRINTING` oder `PAUSED` und danach auf `FINISHED`.

### Verwendete PrusaLink-Aufrufe

| Zweck | Methode und Pfad | Besonderheit |
| --- | --- | --- |
| Verbindung | `GET /api/printer` | `X-Api-Key`, 10-s-Request-Timeout |
| Status | `GET /api/v1/status` | Fehler werden begrenzt toleriert |
| Upload + Start | `PUT /api/v1/files/usb/{REMOTE_GCODE_PATH}` | `Overwrite: ?1`, `Print-After-Upload: ?1`; 10 s Connect/300 s Read |

Bei unerwartetem Druckerzustand nicht sofort denselben G-Code neu starten. Zuerst am Display prüfen, ob ein Druck noch läuft oder ein Teil auf dem Bett liegt.

## PrusaLink als Softwarekomponente

`src/printer/prusalink_service.py` verwendet `requests` direkt. Es gibt keinen Discovery-Mechanismus und keine TLS-Konfiguration. IP und Schlüssel müssen daher stimmen; die QS-API darf nicht irrtümlich als Druckerziel eingetragen werden.

Der Remote-Pfad wird auf gefährliche Bestandteile geprüft. Absolute Pfade, `..`, leere Segmente und Query-/Fragmentzeichen sind nicht als normaler Dateiname gedacht. Der Default ist `FOLDER/demo.gcode`.

Nach einem Netzwerkfehler:

1. Druckerdisplay und Bett physisch prüfen.
2. `GET /api/v1/status` erneut abfragen.
3. Nur wenn kein Druck aktiv ist entscheiden, ob ein neuer Versuch sicher ist.
4. Im Optimierer ausschließlich den vom Store angebotenen Retry-/Resume-Pfad verwenden.

## Niryo Ned2

### Verbindung und Initialisierung

Der Hauptrechner verbindet sich über PyNiryo mit `ROBOT_IP`, standardmäßig `10.8.170.41`. Port und Transportdetails verwaltet PyNiryo; im Projekt ist kein eigener Roboterport angegeben. `RobotService.initialize()` führt automatische Kalibrierung, Werkzeugaktualisierung, Löschen des Kollisionsflags und eine maximale Armgeschwindigkeit von 50 % aus.

Der Preflight ruft nur `get_joints()` auf und kalibriert oder bewegt den Arm nicht.

### Tatsächliche Bewegungsfolge

Die verbindlichen Wegpunkte stehen in `src/robot/robot_positions.py`, die Reihenfolge in `src/robot/robot_service.py`:

1. `HOME`, Greifer schließen.
2. `PRINTER_SAFE`, Greifer öffnen, `PRINTER_PICK`.
3. Zweistufig greifen, dann `PRINTER_BREAK_OFF_1`, `PRINTER_BREAK_OFF`, `PRINTER_OUTSIDE`.
4. Über `TRANSFER_CLEARANCE` zu `QS_SAFE` und `QS_PART_RELEASE`; Teil ablegen.
5. Über `QS_ALIGNMENT_ORIENTATION`, langsam `QS_ALIGNMENT_CONTACT` → `QS_ALIGNMENT_END` → `QS_ALIGNMENT_CONTACT`, dann `QS_ALIGNMENT_RETREAT`.
6. `QS_FINAL_PUSH_CONTACT`, langsam `QS_FINAL_PUSH_TARGET`, zurück zu Kontakt und `QS_SAFE`.
7. `QS_LIFT_LEVER_GRIP`, drei Sekunden warten, langsam `QS_PART_UNDER_PROBE`, zurück über Greifpunkt nach `QS_SAFE`.
8. Nach der Messung `QS_LIFT_LEVER_APPROACH` → `QS_LIFT_LEVER_END` → Approach → `QS_SAFE`.
9. `QS_PART_SHIFT_APPROACH` → `QS_PART_SHIFT_END` → Approach → `QS_SAFE` → `HOME`.

Langsame Schubbewegungen laufen mit 20 %, die Kollisions-Recovery mit 10 %. Die Gelenkwerte werden hier bewusst nicht dupliziert; nur `robot_positions.py` soll für Änderungen editiert werden.

### Kollisionsverhalten

Nur beim letzten Schub werden Meldungen mit `collision` oder `motor not able to follow` als erwarteter Sonderfall behandelt. Dann löscht der Code das Kollisionsflag und fährt die fest gelehrte Recovery über `QS_FINAL_PUSH_CONTACT`, `QS_SAFE`, `QS_SAFE_RECOVERY`, `QS_RECOVERY`, erneut Kontakt, `QS_RECOVERY_CLEAR_PART`, `QS_SAFE`, `HOME`. Der Orchestrator bricht danach vor der Messung ab.

Alle anderen Roboterfehler werden weitergereicht; es gibt dafür keine allgemeine automatische Rückzugsbahn. Anlage sichern, Position feststellen und erst nach physischer Korrektur einen manuellen Resume vorbereiten.

Die generierten/älteren Positionsdokumente sind teilweise veraltet und dürfen die Service-Reihenfolge nicht ersetzen.

## Mitutoyo SJ-220

### Verbindung

Das Messgerät ist über RS-232C/USB am Raspberry Pi angeschlossen. Die API verwendet fest:

| Einstellung | Wert aus `SJ220Service` / API |
| --- | --- |
| Gerät | `/dev/ttyUSB0` |
| Baud | `38400` |
| Datenformat | 8 Datenbits, keine Parität, 1 Stoppbit |
| Flusssteuerung | RTS/CTS ein; DSR/DTR und XON/XOFF aus |
| Lese-/Schreibtimeout | je 3 s |
| Messfrist / Startfrist | 60 s / 30 s |
| Polling | 0,25 s |
| temporäre Read-Retries | 5, nur Codes `011` und `033` |
| Prozesssperre | `/tmp/sj220_service.lock` |

Verwendete Kommandos sind `RDSTU00` (Status), `RDPSA` (Detektorposition), `CTSTA` (Start), `RDPAR` (Parameteranzahl) und `RDRES02,NN,00` (Ergebnis). Befehle enden mit Carriage Return.

### Sicherer Verbindungstest

`/health` testet **nicht** das serielle Gerät. Eine direkte Messung bewegt den Detektor und darf nur mit korrekt positioniertem Testkörper erfolgen.

**Arbeitsverzeichnis: `3d-automation/` auf dem Pi; physische Messbewegung**

```bash
source .venv-pi/bin/activate
export PYTHONPATH="$PWD/src"
python -m qs.run_sj220
```

Erfolg: Ausgabe enthält `Messung erfolgreich`, `Ra`, `Rz` und Messdauer; Exitcode 0. Typisierte Fehler verwenden Exitcodes 2 bis 8, Abbruch per Tastatur 130.

Bei Fehler `007` versucht `SJ220Service.measure()` intern eine zusätzliche Messung und meldet den Fehler trotzdem weiter. Deshalb erst Werkstück, Messbereich und Detektorposition prüfen; nicht blind erneut auslösen.

## Raspberry Pi 5 und QS-API

Der Pi hostet `qs.api:app`. Die Anwendung serialisiert konkurrierende SJ-Zugriffe über Lockdatei und öffnet den Port pro HTTP-Messung. Die API bietet keine im Projekt implementierte Authentifizierung; Port 8000 deshalb nur in einem kontrollierten lokalen Netz freigeben.

**Arbeitsverzeichnis: `3d-automation/` auf dem Pi**

```bash
source .venv-pi/bin/activate
export PYTHONPATH="$PWD/src"
python -m uvicorn qs.api:app --host 0.0.0.0 --port 8000
```

Es existiert noch kein versionierter systemd-Service. Nach Prozessabbruch wird der serielle Kontext normalerweise geschlossen; bei einem harten Abbruch sind Portbelegung und `/tmp/sj220_service.lock` zu diagnostizieren. Die Lockdatei nicht löschen, solange ein Messprozess laufen könnte.

## Kamera / V4L2

Die Kamera hängt standardmäßig an `/dev/video0`. Vor dem API-Start müssen `v4l2-ctl` und `ffmpeg` im `PATH` liegen. Der Health-Endpunkt prüft genau diese Programme und die Existenz des Gerätepfads.

Für jede Aufnahme setzt der Code standardmäßig Auto-Exposure `1`, Belichtungszeit `220`, Gain `64`, Helligkeit `-30`, Kontrast `80`, Gamma `300`, Schärfe `80`, automatischen Weißabgleich `0`, Weißabgleich `3800`, Sättigung `30` und Backlight-Kompensation `0`. Nicht jede Kamera muss diese Controls unterstützen; ein fehlender Control führt zu einem Aufnahmefehler.

**Arbeitsverzeichnis: beliebig auf dem Pi, keine Roboterbewegung**

```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 -L
v4l2-ctl -d /dev/video0 --list-formats-ext
curl --fail --show-error http://127.0.0.1:8000/camera/health
```

Die API-Aufnahme ist in [11 – API-Referenz](11_api_referenz.md) beschrieben. `show_live()` in `camera_ctrl.py` baut seine Control-Zeichenfolge derzeit aus den explizit übergebenen Controls statt aus den zusammengeführten Defaults; das Livebild ist nicht Teil des Orchestratorpfads, aber diese Abweichung sollte vor Nutzung korrigiert werden.

## QS-Station als Gesamtsystem

Die QS-Station verbindet Ablage, horizontale Ausrichtung, Endschub, Hebemechanik, Tastermessung und Ausschub. Software-Health allein kann folgende physische Fehler nicht erkennen: verdrehter Testkörper, Teil außerhalb der Aufnahme, verklemmter Hebel, falsche Tasterhöhe oder ein vom Druckbett weggeflogenes Teil.

### Sichere Wiederherstellung

1. Automatik stoppen und Bewegungszustand an allen Geräten prüfen.
2. Roboter nicht von Hand gegen aktive Motoren bewegen; Herstellerverfahren beachten.
3. Testkörper und lose Teile entfernen, Taster und Vorrichtung auf Schäden prüfen.
4. Roboter über einen sicheren, vor Ort bestätigten Weg in eine bekannte Stellung bringen.
5. Verbindungen und Health-Endpunkte erneut prüfen.
6. `preflight-only` ausführen.
7. Terminalen Optimiererfehler erst danach mit `--resume-after-manual-intervention --from-run N --preflight-only` freigeben.

Weiter: [06 – Bedienung](06_bedienung.md)
