# 12 – Übergabe und offene Punkte

## Referenzstand

Diese Dokumentation wurde aus Branch `feature/optimizer-framework-integration`, Commit `29f11b9`, den vorhandenen Tests und Konfigurationen erstellt. Projektpitch und Aufgabenstellung wurden als Kontext gelesen; bei Widersprüchen war der aktuelle Code verbindlich.

Die Dokumentationsarbeit hat keinen funktionalen Produktionscode verändert. Hardware wurde nicht angesteuert.

## Reifegrad

| Bereich | Einstufung | Begründung |
| --- | --- | --- |
| Profilgenerierung | implementiert und unit-getestet | sechs Parameter und feste Versuchsbedingungen werden gezielt ersetzt |
| Sliceradapter | implementiert und gemockt getestet | Prozess, Timeout und nicht leere Ausgabe geprüft; kein echter Slicerlauf dieser Übergabe |
| PrusaLink | implementiert und gemockt getestet | Health, Status, Upload und Auto-Start vorhanden |
| Kamera-API/-Client | implementiert und getestet | Health, Capture, Download und Validierung; echte Kamera nicht getestet |
| SJ-220-Service/-API | implementiert | serielles Protokoll und Fehlerabbildung; reale Referenzmessung nicht durchgeführt |
| Roboterablauf | implementiert | feste Positionen, Geschwindigkeiten und partielle Recovery; reale Mechanik nicht geprüft |
| statischer 100er-Plan | implementiert und getestet | Generierung, Archivierung, Auswahl und manueller Resume |
| persistenter Optimierer | implementiert und weitgehend getestet | Warmstart, fünf Strategien, Checkpoints, Penalty/Ignore und Resume |
| Hardwareadapter | integriert und mit Fakes getestet | Preflight-Receipt und Bestätigungs-Gate; echter Gesamtlauf nicht ausgeführt |
| Deployment | unvollständig | kein Paket-Metadatum, keine CI, kein Docker, keine systemd-Unit |
| Teststatus | nicht vollständig grün | 129 erfolgreich, ein veraltetes Testmodul mit fehlendem Import |

Vorhandene, nicht versionierte Laufartefakte deuten auf frühere Hardwareausführungen hin, gelten aber nicht als reproduzierbarer Abnahmetest dieses Codezustands.

## Gefundene Widersprüche

| Thema | Ältere/oberflächliche Aussage | Aktueller Code |
| --- | --- | --- |
| obere Schichten | CLI-Hilfe: fest 5 | `PrintParameters` und Optimierer erlauben `top_solid_layers` variabel |
| Parametergrenzen | CLI-Hilfe: enge alte Bereiche | Einzelzyklus prüft nur intrinsische Domänen; Optimierergrenzen kommen aus JSON |
| Mess-Retry | Client-Kommentar: POST nicht automatisch wiederholen | Orchestrator ruft den Client nach jeder Exception ein zweites Mal auf |
| Messfehler und Roboter | ältere Doku: nach Fehler nicht weiterbewegen | aktueller Orchestrator setzt 100/100 und führt Post-Measurement-Handling aus |
| Kamera-Reihenfolge | fachliche Kurzbeschreibung teilweise nach Messung | Code: direkt nach Druckende, vor Abkühlung und Robotik |
| Robotpositionen | ältere Markdown-/Generatorsequenzen | tatsächliche Reihenfolge nur in `robot_service.py` aktuell |
| systemd | ältere Hinweise implizieren Service | keine Unit im Repository |
| Requirements | zwei Requirements-Dateien suggerieren Vollständigkeit | NumPy, SciPy und scikit-learn fehlen in der App-Datei |
| History-Import | JSON-Schema akzeptiert `history_csvs` | beide Runner verweigern nicht leere Listen |

## Priorisierte technische Schulden

### Priorität 0 – vor unbeaufsichtigten Hardwareläufen

1. **Retry-Verantwortung vereinheitlichen.** Den SJ-220-Sonderfall `007`, den Orchestrator-Doppel-POST und den Framework-Zyklusretry auf eine sicher begrenzte, physisch nachvollziehbare Policy reduzieren.
2. **Druckstatus reconciliieren.** Netzwerkfehler in `waiting_for_print` nicht automatisch wie einen vergleichbaren Prozessfehler behandeln. Vor Retry feststellen, ob der Druck lief, fertig ist oder noch läuft.
3. **Crash-Recovery für `running`.** Auditierbaren CLI-Befehl implementieren, der nach Operatorprüfung zwischen unverbraucht, verbraucht/retry-fähig und terminal entscheidet.
4. **Roboterablauf vor Ort requalifizieren.** Alle Positionen und Recovery-Bahnen nach aktuellem mechanischem Stand einzeln freigeben.
5. **Messfehler-Posthandling entscheiden.** Fachlich klären, ob bei ungültiger Messung die QS wirklich weiterbewegt werden darf.

### Priorität 1 – Reproduzierbarkeit und Betrieb

1. Eine einzige vollständige Dependency-/Packaging-Datei mit Python-Version und gelockten Versionen erstellen.
2. Veralteten `test_bayesian_optimizer.py` auf `BayesianStrategy`/`ExperimentStore` migrieren; Testlauf grün machen.
3. systemd-Unit für Pi-API samt Arbeitsverzeichnis, Env-Datei, Restart-Policy und eingeschränktem Benutzer versionieren.
4. API auf vertrauenswürdiges Netz begrenzen und Authentifizierung/TLS oder einen abgesicherten Reverse Proxy festlegen.
5. Firmware-, Slicer-, Kamera-, Werkstoff-, Düse- und Anlagenstände pro Experiment erfassen.
6. `CAMERA_OUTPUT_DIR` absolut konfigurieren und seriellen Port/Baud aus sicherer Konfiguration statt Hardcode lesen.

### Priorität 2 – wissenschaftliche und funktionale Erweiterung

1. Historienimport mit explizitem Schema und Provenienz implementieren.
2. Ignorierte Parametersätze separat von Optimiererbeobachtungen als „bereits versucht“ führen.
3. Bildauswertung beziehungsweise Operator-Freigabe vor dem Greifen zur Erkennung verlorener/fehlerhafter Teile ergänzen.
4. QBC oder Modellvergleiche nur mit klarem wissenschaftlichem Versuchsdesign implementieren; sie sind heute nicht „vorbereitet fertig“.
5. Mehrziel- oder Nebenbedingungslogik für `Rz` und Prozessqualität evaluieren.
6. CI mit Unit-Tests, Link-/Dokumentationsprüfung und statischer Analyse einrichten.

## Noch zu klären

| Information | Warum nötig | Betroffene Stelle / Klärung |
| --- | --- | --- |
| langfristig freigegebener Zielbranch/Release | reproduzierbares Klonen über das vorhandene GitHub-`origin` | Projektverantwortlicher; derzeit dokumentiert ist der analysierte Feature-Branch |
| freigegebene OS- und Python-Version | reproduzierbarer Support | Packaging/CI definieren |
| tatsächliches Druckermodell MINI oder MINI+ und Firmware | Profil-/API-Kompatibilität | Gerät inventarisieren |
| PrusaSlicer-Bezugsquelle und Prüfsumme | sichere Installation | Release/IT-Freigabe dokumentieren |
| sichere Parametergrenzen pro Material/Düse | Schutz und wissenschaftliche Gültigkeit | Prozessverantwortlicher; JSON-Review |
| aktuelle Gelenkpositionen nach realem Aufbau | Kollisionsschutz | Lehrfahrt/Abnahme am Standort |
| gewünschtes Verhalten nach Messfehler | Roboter- und Datenpolicy | fachliche Entscheidung plus Tests |
| erwartete Ra/Rz-Bereiche eines Referenznormals | Messkettenvalidierung | QS-Verantwortlicher |
| Backup-, Aufbewahrungs- und Datenschutzregeln für Bilder | verlässlicher Betrieb | Betreiber/Projektleitung |
| Endpunktabsicherung im Produktionsnetz | Zugriffsschutz | IT-/Security-Konzept |

## Wichtige Änderungsstellen

| Änderung | Primäre Dateien |
| --- | --- |
| Prozessreihenfolge/Fehlerstufen | `src/orchestrator.py` |
| Hardwarekonstruktion und Env | `src/main.py` |
| Roboterpfad | `src/robot/robot_service.py`, `src/robot/robot_positions.py` |
| SJ-Protokoll/Retry | `src/qs/sj220_service.py`, `src/qs/api.py` |
| Kamera | `src/camera/camera_ctrl.py`, `src/camera/camera_client.py` |
| Druck/Slicer | `src/printer/*.py` |
| statischer Plan/CSV | `src/experiments/*.py`, `src/results/csv_cycle_recorder.py` |
| Optimiererschema/Strategien | `src/optimizer/config.py`, `src/optimizer/strategies.py` |
| Persistenz/Resume | `src/optimizer/experiment_store.py`, `framework_runner.py`, `hardware_cli.py` |

## Übergabecheckliste

- [ ] README und Kapitel 01–12 gemeinsam lesen.
- [ ] Zielbranch/Release und Python-Version offiziell freigeben.
- [ ] Virtuelle Umgebung aus einer bereinigten Dependency-Datei neu bauen.
- [ ] Alle Tests grün machen; aktuellen Testbericht versioniert ablegen.
- [ ] Eigenes Simulationsexperiment neu + Resume erfolgreich ausführen.
- [ ] Lokale Env-Datei anlegen; keine Schlüssel committen.
- [ ] Netzwerk-, Drucker-, Kamera- und Pi-Health prüfen.
- [ ] SJ-220 mit Referenznormal validieren.
- [ ] Roboterpositionen und Recovery mit Sicherheitsfreigabe prüfen.
- [ ] Fehlerpolicy `penalty` oder `ignore` wissenschaftlich festlegen.
- [ ] Neuen Hardwarelauf zuerst `--new --preflight-only`, danach einen bestätigten Run starten.
- [ ] Laufverzeichnis komplett sichern und Ergebnis mit physischem Teil korrelieren.
- [ ] P0-Punkte erledigen, bevor ein längerer oder unbeaufsichtigter Lauf erwogen wird.

## Empfohlener nächster Schritt

Zuerst die Retry- und Crash-Recovery-Logik als kleine, getestete Zustandsmaschine konsolidieren. Danach Dependencies und Deployment reproduzierbar machen und einen dokumentierten Hardware-Abnahmelauf mit Referenzteil durchführen. Erst auf dieser stabilen Basis sollte die wissenschaftliche Optimiererbewertung erweitert werden.

Zurück zum [Projekt-README](../../README.md).
