# 09 – Fehlerbehandlung

## Erst sichern, dann fortsetzen

Bei jedem unbekannten Hardwarezustand gilt:

1. Keine weitere Automatik starten.
2. Druckerdisplay, Druckbett, Roboter, Greifer, QS und Taster physisch prüfen.
3. Bei akuter Kollisionsgefahr die vorgesehene sichere Abschaltung/Not-Aus verwenden.
4. Laufverzeichnis und Konsolen-/Dateilog sichern.
5. `failed_stage`, Run-Status, Attempt und Cycle-ID bestimmen.
6. Erst nach Behebung einen Preflight und den passenden Resume-Pfad ausführen.

## Troubleshooting-Matrix

„Automatisch?“ bezieht sich auf die aktuelle Optimierer-Hardwarelogik, nicht auf eine allgemeine technische Empfehlung.

| Sichtbarer Fehler / Situation | Komponente | Wahrscheinliche Ursache | Diagnose und Lösung | Automatisch? | Vollstopp / Fortsetzung |
| --- | --- | --- | --- | --- | --- |
| `Required environment variable ... is not set` | Startkonfiguration | `PRUSALINK_API_KEY` oder `QS_BASE_URL` fehlt | `config/end_to_end.env` prüfen und mit `set -a; source ...; set +a` laden; Wert nicht ausgeben | nein | vor Hardware beheben, normal neu starten |
| `No module named main/optimizer/...` | Python | falscher Startpfad oder `PYTHONPATH` fehlt | nach `3d-automation/` wechseln, venv aktivieren, `export PYTHONPATH="$PWD/src"` | ja, rein lokal | kein Hardwareversuch verbraucht |
| `No module named numpy/scipy/sklearn` | Optimierer | unvollständige Requirements installiert | `python -m pip install numpy scipy scikit-learn`, danach `pip check` | ja, vor Lauf | kein Hardwareversuch verbraucht |
| Slicer-Datei fehlt / Prozesscode ungleich 0 / leere Ausgabe | Slicer | falscher `PRUSASLICER_PATH`, Profil/STL ungültig, Slicerfehler | Pfade, Ausführungsrecht und manuellen `--version`-Aufruf prüfen; Slicer-Log lesen | ja; Stufe `slicing`, Attempt unverbraucht | Preflight wiederholen, dann derselbe Run |
| Drucker nicht erreichbar | PrusaLink | IP, Netz, API-Key oder PrusaLink falsch | Ping/Route und authentifiziertes `/api/printer` prüfen; Display kontrollieren | Preflight ja; später abhängig von Stufe | bei möglichem Druckstart erst manuell prüfen |
| Druckerstatus bleibt unerwartet / Statusfehlerlimit | Druckerüberwachung | Druck startete nicht, Netzunterbrechung, Firmwarezustand | `/api/v1/status` und Display vergleichen, Bett prüfen | Code: `waiting_for_print` retry-fähig | nach echter Statusklärung; automatische Einstufung ist ein Risiko |
| Drucktimeout | Druckprozess | Druck dauert > `PRINT_TIMEOUT_SECONDS`, Druck hängt | Display/Teil prüfen; Frist nicht blind erhöhen | Code: retry-fähig und Attempt verbraucht | laufenden Druck zuerst ausschließen |
| Spaghetti, Ablösung oder weggeflogenes Teil | Druck/Prozess | Haftung, Parameter, Geometrie | Sichtprüfung und Bild; Bett/Düse reinigen, Grenzen prüfen | nicht zuverlässig erkannt; möglicher späterer Retry | manueller Stopp empfohlen, Teil entfernen |
| Kamera-Health 503 | Kamera/Pi | `ffmpeg`/`v4l2-ctl` fehlt oder Gerätepfad nicht vorhanden | `/camera/health`, `which`, `ls -l`, V4L2-Formate prüfen | nein, Hardwareadapter klassifiziert Kamera terminal | Fehler beheben, manuell freigeben |
| Kamera-Capture 502 / leeres Bild | Kamera | unsupported Control/Format, Gerät belegt, ffmpeg-Fehler | API-Log, `v4l2-ctl -L`, Format und Auflösung prüfen | nein | vor Roboterhandling gestoppt; manuell prüfen/freigeben |
| Roboterverbindung fehlgeschlagen | Niryo | IP/Netz, Roboter aus, PyNiryo-Fehler | Preflight-`get_joints`, Netz und Roboteroberfläche prüfen | Preflight unverbraucht; im Zyklus terminal | Anlage prüfen, dann manueller Resume |
| Roboterkollision / Trackingfehler beim letzten Schub | QS-Roboter | Teil verklemmt oder Toleranz überschritten | Code führt feste 10-%-Recovery bis HOME aus; Vorrichtung/Teil danach prüfen | nein | trotz erfolgreicher Recovery terminal; manueller Resume |
| Roboterfehler an anderer Position | Roboter | Kollision, verlorenes Teil, falsche Lehre | sofort stoppen; aktuelle Pose und Mechanik sichern; kein generischer Rückzug implementiert | nein | vollständige Anlagenprüfung nötig |
| Teil verdreht oder verklemmt | QS-Mechanik | Ablage/Schub fehlgeschlagen | Sichtprüfung; Teil/Taster/Vorrichtung kontrollieren | nicht sensorisch erkannt | manuell stoppen und korrigieren |
| `/health` ok, Messung scheitert | SJ-220 | Health prüft nur Webdienst | direkte Messung nur mit Teil; Port, Kabel, Gerätestatus und Pi-Log prüfen | Messfehler im Orchestrator intern wiederholt | nach zwei Calls Framework-Retry/Penalty/Ignore |
| HTTP 409 `port_in_use` | SJ-220 | anderer Prozess hält Lock/Port oder ungültiger Gerätestatus | laufende API/CLI-Messung suchen; Lock nicht bei aktivem Prozess löschen | Orchestrator versucht zweiten POST | bei unklarem Detektorzustand stoppen |
| HTTP 503 `connection_error` | SJ-220 | `/dev/ttyUSB0`, Kabel, Rechte, Gerät aus | `ls -l /dev/ttyUSB0`, Gruppen, Kabel und Gerät prüfen | Orchestrator versucht zweiten POST | Ursache vor neuem Zyklus beseitigen |
| HTTP 504 `timeout` | SJ-220 | keine vollständige serielle Antwort/Messbewegung hängt | Detektorstatus, Kabel und Pi-Log prüfen | Orchestrator versucht zweiten POST | Detektorposition physisch prüfen |
| HTTP 422 `device_error` | SJ-220 | `NGnnn` vom Gerät | Code und Tabelle unten verwenden | nur `011/033` intern beim Lesen; sonst über Orchestrator | abhängig von Mechanik, meist Prüfung nötig |
| HTTP 502 `result_error`/`protocol_error` | SJ-220 | unvollständiges Ergebnis oder unerwartetes Protokoll | Raw-Log bei DEBUG ergänzen, Parameterkonfiguration am Gerät prüfen | Orchestrator zweiter POST | danach Framework-Policy |
| Ungültige Optimierer-JSON | Config | unbekanntes Feld, unvollständige Parameter, falsche Batches | `python -m optimizer.config ... --check-input-files`; Meldung exakt abarbeiten | ja, vor Hardware | kein neuer Store/Attempt starten |
| `output directory already exists` | Store | `--new` auf vorhandenem Ziel | für neues Experiment neuen Pfad; für bestehendes exakt `--resume` | nein | nichts löschen/überschreiben |
| `supplied configuration differs` | Store | JSON/Pfade seit Anlage geändert | ursprüngliche Konfiguration/Pfade wiederherstellen; Snapshot vergleichen | nein | Resume absichtlich verweigert |
| fehlender/beschädigter JSON-Zustand oder Checkpoint | Store | unvollständige Kopie, manueller Edit, Datenträgerfehler | komplettes Backup vergleichen; Dateien nicht improvisiert rekonstruieren | nein | technische Wiederherstellung/Entwicklerprüfung |
| Run bleibt `running` | Store/CLI | Prozessabbruch nach `mark_run_started` | reale Anlage prüfen und Zustand sichern | nein; keine CLI-Klassifikation vorhanden | offener Implementierungspunkt |
| fehlende/mismatched Preflight-Receipt | Hardware-CLI | anderer Run/Attempt oder Datei fehlt | denselben Run mit `--resume --from-run N --preflight-only` prüfen | ja, ohne Verbrauch | danach bestätigten Einzelrun |
| Sicherheitsstopp nach drei Fehlschlägen | Framework | drei endgültig fehlgeschlagene Parametersätze | gemeinsame Ursache beseitigen, dann `--acknowledge-failure-streak ... --preflight-only` | nein bis Quittierung | danach einzelnen Lauf bestätigen |

## SJ-220-Codes

Die Beschreibung stammt aus `src/qs/sj220_exceptions.py`.

| Codes | Bedeutung / erste Prüfung |
| --- | --- |
| `003`, `004`, `005`, `006` | End-/Ursprungsposition nicht erreicht oder Endschalter aktiv; Mechanik und Detektor prüfen |
| `007` | Detector over-range; Werkstückposition und Messbereich prüfen |
| `011`, `033` | Gerät beschäftigt/verarbeitet noch; nur idempotente Lesekommandos werden bis zu fünfmal intern wiederholt |
| `012`, `013` | Steuer-Timeout beziehungsweise Kommunikationspufferüberlauf |
| `014`–`017` | Flash-, Programm- oder Systemfehler am Gerät |
| `018`, `019`, `022` | ungültige Startposition/Einstellung oder Detektor getrennt |
| `030`, `031`, `032` | Befehl, Format oder Wert ungültig |
| `071` | SPC-Kommunikationsfehler |
| `101`–`103` | Ergebnis fehlt/außerhalb Bereich/Messung wegen Overrange abgebrochen |
| `110`–`130` | zu wenige Profilmerkmale/Daten oder Berechnungsfehler |
| `184` | „Printer access timeout“ laut hinterlegter Gerätetabelle |

Statuscodes `000` bis `005` bedeuten Idle, Messen, Rücklauf, Einziehen, eingezogen und Zwischenposition. `005` ist während/nach Bewegung ausdrücklich erlaubt.

## Tatsächlich implementierte Wiederholungslogik

Es gibt drei Ebenen, die nicht verwechselt werden dürfen:

### 1. Geräteebene SJ-220

Nur Lesekommandos mit `NG011` oder `NG033` werden bis zu fünfmal wiederholt. Bei `NG007` startet `measure()` intern eine zusätzliche Messung, verwirft deren Ergebnis und wirft danach den ursprünglichen Fehler weiter. Diese Sonderbehandlung ist mechanisch relevant.

### 2. Orchestrator

Jede Exception des ersten QS-HTTP-POST führt genau zu einem zweiten Client-POST. Scheitert auch dieser, setzt der Orchestrator `Ra=100` und `Rz=100`, merkt einen Fehlertext, führt aber die Post-Measurement-Roboterfolge weiter aus und zeichnet den Cycle als `completed` auf.

Damit können bei `007` durch die Kombination aus Geräte- und Orchestratorebene mehr als zwei physische Messbewegungen entstehen. Die ältere Client-Dokumentation „POST is deliberately not retried“ gilt nur für den Client selbst, nicht für seinen Aufrufer.

### 3. Optimierer-Framework

Der Hardwareadapter wandelt das obige CycleResult wegen seines Fehlertexts in einen retry-fähigen `measurement_penalty`-Fehler um. Mit automatischer Wiederholung kann anschließend ein kompletter zweiter Druck-/Messzyklus mit denselben Parametern folgen.

| Stufe | Frameworkklassifikation | Attempt verbraucht? | Folgeverhalten |
| --- | --- | --- | --- |
| `preflight`, `slicing` | retry-fähig, vor physischem Lauf | nein | nach Behebung gleicher Attempt |
| `waiting_for_print`, `measuring` | vergleichbar, retry-fähig | ja | höchstens ein automatischer zweiter Attempt |
| `measurement_penalty`, `result_validation` | retry-fähiges Ergebnisproblem | ja | höchstens ein automatischer zweiter Attempt |
| `uploading`, `starting_print`, `camera_capture`, `cooling`, `robot_handling`, `recording`, unbekannt | terminal / Zustand unsicher | ja | manueller Eingriff und Preflight |

Nach dem zweiten vergleichbaren Fehlschlag wird der Satz je nach unveränderlicher Experimententscheidung als Penalty 100 oder Ignore abgeschlossen.

## Gewünschtes Sicherheitsverhalten versus Code

| Situation | Aktueller Code | Empfohlene Verbesserung |
| --- | --- | --- |
| Netzfehler beim Warten auf Druck | retry-fähiger physischer Fehlschlag | Infrastrukturfehler von echtem Druckfehler unterscheiden; Druckerstatus zuerst reconciliieren |
| doppelt fehlgeschlagene Messung | Post-Handling wird mit temporärem 100/100 fortgesetzt | mechanische Position und Fehlerart explizit modellieren; sicheren Abbruchpfad definieren |
| SJ `007` | interne Zusatzmessung plus weitergereichter Fehler | genau eine verantwortliche Retry-Ebene festlegen |
| harter Abbruch bei `running` | automatisches Wiederholen blockiert, aber keine Klassifikations-CLI | Operator-Command für „physisch verbraucht/nicht verbraucht/terminal“ mit Audit-Log ergänzen |
| Spaghetti/verlorenes Teil | keine automatische Erkennung | Kameraauswertung oder Operator-Gate vor Robotergreifen |
| ignorierter Satz | nicht als Beobachtung und nicht in Duplikatmenge | separat als bereits physisch ausgeführt sperren |

Weiter: [10 – Tests und Entwicklung](10_tests_und_entwicklung.md)
