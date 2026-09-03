# 04 – Konfiguration

## Grundprinzip und Prioritäten

Es gibt keine globale Kaskade „CLI vor JSON vor Env“. Die Quellen sind komponentenspezifisch:

1. `main.py`: Dateipfade und sechs Einzelzyklusparameter kommen aus CLI-Argumenten. Nicht angegebene Parameter werden aus dem per CLI gewählten Basisprofil gelesen.
2. Hardwareadressen und Zeitwerte des Orchestrators kommen ausschließlich aus Umgebungsvariablen oder den in `main.py` codierten Defaults.
3. Das Optimierer-Framework liest Experiment, Grenzen, Strategie und Pfade ausschließlich aus einer JSON-Datei. Hardwarezugang und Orchestrator-Timeouts bleiben Env-Werte.
4. Die Hardware-CLI setzt während der Objekterzeugung gegebenenfalls den Kamera-Downloadpfad auf das Laufverzeichnis.

Relative Optimiererpfade werden relativ zum Verzeichnis der JSON-Datei aufgelöst. Relative Kamera-Ausgabepfade der Pi-API hängen dagegen vom Arbeitsverzeichnis des Uvicorn-Prozesses ab.

## Umgebungsvariablen auf dem Hauptrechner

Quelle: `src/main.py:build_orchestrator`.

| Name | Bedeutung | Typ | Einheit | Standard | Bereich/Format | Pflicht | Quelle | Beispiel |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `PRINTER_IP` | PrusaLink-Host | Text | – | `10.8.170.57` | Host/IP ohne Schema und Port | optional | `main.py:build_orchestrator` | `10.8.170.57` |
| `PRUSALINK_API_KEY` | PrusaLink-Zugang | geheimer Text | – | keiner | nicht leer | **ja** | `main.py:required_environment` | `REPLACE_WITH_NEW_API_KEY` |
| `ROBOT_IP` | Niryo-Adresse | Text | – | `10.8.170.41` | Host/IP | optional | `main.py:build_orchestrator` | `10.8.170.41` |
| `QS_BASE_URL` | QS-API | URL-Text | – | keiner | nicht leer, mit Schema/Port | **ja** | `main.py:required_environment` | `http://192.0.2.10:8000` |
| `CAMERA_BASE_URL` | separate Kamera-API | URL-Text | – | `QS_BASE_URL` | mit Schema/Port | optional | `main.py:build_orchestrator` | `http://192.0.2.10:8000` |
| `PRUSASLICER_PATH` | ausführbarer Slicer | Pfadtext | – | `~/apps/prusaslicer/PrusaSlicer-2.9.1-x86_64.AppImage` | vorhandene, ausführbare Datei | optional | `main.py:build_orchestrator` | `/opt/PrusaSlicer.AppImage` |
| `REMOTE_GCODE_PATH` | USB-Ziel im Drucker | Pfadtext | – | `FOLDER/demo.gcode` | relativer sicherer Pfad | optional | `main.py:build_orchestrator` | `FOLDER/demo.gcode` |
| `CAMERA_DOWNLOAD_DIR` | lokale JPEG-Kopien | Pfadtext | – | Projekt-`data/camera_images` | beschreibbares Verzeichnis | optional | `main.py:build_orchestrator` | `data/camera_images` |
| `PRINT_POLL_SECONDS` | Druckstatusintervall | float | s | `15` | >= 0 | optional | `main.py`, `PrintOrchestrator.__init__` | `15` |
| `PRINT_START_TIMEOUT_SECONDS` | Frist bis aktiv | float | s | `180` | > 0 | optional | `main.py`, `PrintOrchestrator.__init__` | `180` |
| `PRINT_TIMEOUT_SECONDS` | gesamte Überwachungsfrist | float | s | `28800` | > 0 | optional | `main.py`, `PrintOrchestrator.__init__` | `28800` |
| `MAX_STATUS_ERRORS` | aufeinanderfolgende Statusfehler | int | Anzahl | `5` | > 0 | optional | `main.py`, `PrintOrchestrator.__init__` | `5` |
| `PART_COOLING_SECONDS` | Wartezeit vor Robotik | float | s | `60` | >= 0 | optional | `main.py`, `PrintOrchestrator.__init__` | `60` |

Sichere Muster stehen in `config/end_to_end.env.example` für den Hauptrechner und `config/qs_station.env.example` für den Raspberry Pi. Sie enthalten nur Platzhalter beziehungsweise dokumentierte Defaults.

### Feste, derzeit nicht extern konfigurierbare Zeitwerte

| Komponente | Wert | Quelle |
| --- | --- | --- |
| PrusaLink normaler Request | 10 s | `PrusaLinkService.__init__` |
| PrusaLink Upload | 300 s Read-Timeout | `PrusaLinkService.__init__` |
| PrusaLink Verbindungswait | 20 Versuche, 10 s Abstand | `PrusaLinkService.wait_until_connected` |
| PrusaSlicer | 600 s | `SlicerService.__init__` |
| QS-Client Health / Messung | 5 s / 90 s | `QualityStationClient.__init__` |
| Kamera-Client Health / Capture / Download | 5 s / 30 s / 30 s | `CameraClient.__init__` |
| Orchestrator QS-Health-Wait | 300 s, 10 s Abstand | `PrintOrchestrator._wait_for_quality_station_health` |

Diese Werte können nur durch Konstruktorübergabe oder Codeänderung angepasst werden; `main.build_orchestrator()` bietet dafür keine Env-Variablen.

## Umgebungsvariablen auf dem Raspberry Pi

Quelle: `src/qs/api.py`.

| Name | Bedeutung | Typ | Einheit | Standard | Bereich/Format | Pflicht | Quelle | Beispiel |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `CAMERA_DEVICE_PATH` | V4L2-Kamera | Pfadtext | – | `/dev/video0` | existierendes Gerät | optional | `qs/api.py:_camera_device_path` | `/dev/video0` |
| `CAMERA_OUTPUT_DIR` | JPEG-Speicher auf Pi | Pfadtext | – | `data/camera_images` | beschreibbar; relativ zum Server-Arbeitsverzeichnis | optional | `qs/api.py:_camera_output_directory` | `/srv/qs/images` |
| `CAMERA_WIDTH` | Aufnahmebreite | int | Pixel | `1920` | Code prüft nicht; muss Kamera/ffmpeg unterstützen | optional | `qs/api.py:_camera_width` | `1920` |
| `CAMERA_HEIGHT` | Aufnahmehöhe | int | Pixel | `1080` | Code prüft nicht; muss Kamera/ffmpeg unterstützen | optional | `qs/api.py:_camera_height` | `1080` |
| `CAMERA_PIXEL_FORMAT` | Eingabeformat | Text | – | `mjpeg` | Code prüft nicht; V4L2-/ffmpeg-Format | optional | `qs/api.py:_camera_pixel_format` | `mjpeg` |

Serieller Gerätepfad und Baudrate sind in `src/qs/api.py:create_measurement` fest auf `/dev/ttyUSB0` und `38400` gesetzt und derzeit nicht über Env konfigurierbar.

## CLI von `main`

Quelle: `src/main.py:parse_arguments`. Pfade sind relativ zum aktuellen Arbeitsverzeichnis interpretierbar; die Defaults sind absolute Pfade unter `3d-automation/`.

| Argument | Typ / Default | Wirkung |
| --- | --- | --- |
| `--mode` | Enum; `preflight` | `preflight`, `robot-qs`, `full` oder `experiment` |
| `--stl` | Pfad; `data/models/15x15_V2_rounded.stl` | Eingabemodell |
| `--profile` | Pfad; `config/slicer_profile.ini` | vollständiges Basisprofil |
| `--generated-profiles-dir` | Pfad; `data/generated_profiles` | erzeugte INI-Dateien |
| `--gcode` | Pfad; `data/gcode/output.gcode` | Einzeldatei; im Experiment bestimmt nur das Elternverzeichnis |
| `--results-csv` | Pfad; `data/results/parameter_optimization_cycles.csv` | append-only Zyklusergebnisse |
| `--experiment-plan` | Pfad; `config/experiment_plans/experiment_plan_100.csv` | exakt 100 Planzeilen |
| `--experiment-cycles` | int 1…100; `2` | **letzte** auszuführende Plannummer, nicht Anzahl |
| `--experiment-start-cycle` | int 1…100; `1` | erste auszuführende Plannummer |
| `--reuse-experiment-plan` | Flag; aus | bestehenden Plan zwingend unverändert wiederverwenden |
| `--experiment-plan-seed` | int; keiner | Reproduzierbarkeit bei Neugenerierung; unvereinbar mit Reuse |
| `--top-solid-layers` | int; Profilwert | obere Vollschichten |
| `--print-speed` | float, mm/s; Profilwert | Geschwindigkeit oberer Vollfüllung |
| `--extrusion-width` | float, mm; Profilwert | Extrusionsbreite der oberen Füllung |
| `--extrusion-multiplier` | float; Profilwert | globaler Extrusionsfaktor |
| `--temperature` | int, °C; Profilwert | Düsentemperatur nach erster Schicht |
| `--fan-speed` | int, %; `max_fan_speed` aus Profil | min./max./Brückenlüfter im erzeugten Profil |

Die Hilfe nennt historische Experimentgrenzen und bezeichnet `top_solid_layers` als fest. Die eigentliche Klasse `PrintParameters` erlaubt jedoch: `top_solid_layers >= 0`, `print_speed > 0`, `extrusion_width > 0`, `extrusion_multiplier > 0`, `temperature >= 0`, `fan_speed` von 0 bis 100. Diese intrinsischen Prüfungen sind keine Aussage über sichere Material- oder Maschinengrenzen. Für reale Versuche müssen enger validierte Grenzen verwendet werden.

Im Modus `experiment` sind die sechs Parameterargumente verboten; die Werte kommen vollständig aus der CSV.

## Optimierer-CLI-Argumente

| Einstieg | Argument | Regel / Bedeutung |
| --- | --- | --- |
| alle Optimierer-CLIs | `config` | Pfad zur JSON, positionsabhängig |
| `optimizer.config` | `--check-input-files` | zusätzlich STL, Profil und History-Pfade prüfen |
| `framework_runner` | genau eines `--new`, `--resume` | Store anlegen oder öffnen |
| `framework_runner` | `--simulate` | zwingende Bestätigung, dass der Simulator verwendet wird |
| `framework_runner` | `--from-run N` | erwartete nächste Nummer beim Resume |
| `framework_runner` | `--max-runs N` | maximal in diesem Prozess abgeschlossene Sätze; ohne Angabe bis Ende/Stopp |
| `framework_runner` | `--retry-failed` | gespeicherten retry-fähigen Satz identisch vorbereiten |
| `hardware_cli` | genau eines `--new`, `--resume` | Anlegen oder Öffnen des Stores |
| `hardware_cli` | `--from-run N` | Resume-Konsistenz; bei manueller Freigabe Pflicht |
| `hardware_cli` | `--max-runs N` | Default 1 abgeschlossener Satz; automatischer Retry kann Extra-Zyklus erzeugen |
| `hardware_cli` | `--retry-failed` | einen gespeicherten retry-fähigen Run vorbereiten |
| `hardware_cli` | `--automatic-retry` | ersten vergleichbaren Fehlschlag einmal automatisch wiederholen; nur Resume |
| `hardware_cli` | `--failure-result penalty\|ignore` | experimentweite, danach unveränderliche Fehlerbeobachtung |
| `hardware_cli` | `--resume-after-manual-intervention` | terminalen Run nach Anlagenprüfung freigeben; nur mit Resume, `--from-run`, Preflight |
| `hardware_cli` | `--acknowledge-failure-streak` | Pause nach drei Fehlsätzen quittieren; Alias `--acknowledge-penalty-streak` |
| `hardware_cli` | `--preflight-only` | Vorschlag speichern/Dienste prüfen, keine physische Ausführung |
| `hardware_cli` | `--confirm-hardware` | Pflicht für physischen Lauf; bei Preflight verboten |

`optimizer.warm_start` besitzt außer dem Config-Pfad keine Option. Ein neuer Hardwarestore darf nur mit `--new --preflight-only` angelegt werden.

## Optimierer-JSON

Quelle: `src/optimizer/config.py`, Schema `1`. Unbekannte Felder werden abgelehnt.

| Feld | Bedeutung | Typ / Einheit | Default | Bereich/Format | Pflicht | Beispiel |
| --- | --- | --- | --- | --- | --- | --- |
| `schema_version` | Konfigurationsschema | int / – | keiner | genau `1` | ja | `1` |
| `experiment_name` | Bezeichner im Snapshot | Text / – | keiner | nicht leer | ja | `surface_roughness_bo_example` |
| `total_runs` | endgültige Parametersätze | int / Anzahl | keiner | >= 1 und Batchregeln | ja | `100` |
| `seed` | deterministische Zufallsquelle | int / – | keiner | >= 0 | ja | `42` |
| `objective` | zu minimierende Größe | Text / µm | keiner | genau `Ra_um` | ja | `Ra_um` |
| `warm_start.method` | Initialdesign | Enum / – | keiner | `lhs`, `random`, `sobol` | ja | `lhs` |
| `warm_start.sample_count` | Initialpunkte/Batchgröße | int / Anzahl | keiner | >= 1; BO/PSO >= 2, DE >= 4 | ja | `10` |
| `strategy.name` | Hauptstrategie | Enum / – | keiner | dokumentierte Namen/Aliase | ja | `bayesian` |
| `strategy.options` | Strategieparameter | Objekt / – | `{}` | nur erlaubte Schlüssel | nein | `{"acquisition":"ei"}` |
| `parameters` | variable Parameter | Liste / je Parameter | keiner | nicht leer; je `name`, `lower`, `upper` | ja | `[ {"name":"print_speed",...} ]` |
| `fixed_parameters` | feste Parameter | Objekt / je Parameter | keiner | zusammen mit `parameters` genau alle sechs | ja | `{"top_solid_layers":5}` |
| `paths.stl` | STL-Eingabe | Pfadtext / – | keiner | relativ zur JSON oder absolut | ja | `../data/models/15x15_V2_rounded.stl` |
| `paths.base_profile` | Slicer-Basisprofil | Pfadtext / – | keiner | relativ zur JSON oder absolut | ja | `slicer_profile.ini` |
| `paths.output_directory` | Laufverzeichnis | Pfadtext / – | keiner | bei `--new` noch nicht vorhanden | ja | `../data/optimization_runs/run_001` |
| `paths.history_csvs` | Altbeobachtungen | Liste / – | `[]` | eindeutige Pfade; aktuelle Runner verlangen leer | nein | `[]` |

Quelle für alle JSON-Felder ist `src/optimizer/config.py`; die Beispielwerte stammen aus `config/optimizer_config.example.json`.

Jeder der sechs unterstützten Parameter muss **genau einmal** entweder variabel oder fest vorkommen. Variable Untergrenze muss kleiner als Obergrenze sein. Für batchbasierte Strategien muss `total_runs - sample_count` durch `sample_count` teilbar sein; Bayesian Optimization erzeugt dagegen Einzelvorschläge.

### Parameterdomänen und Rundung

| Parameter | Einheit | Typ/Rundung | intrinsische Code-Domäne | Beispielgrenze |
| --- | --- | --- | --- | --- |
| `top_solid_layers` | Schichten | int | >= 0 | im Beispiel fest `5` |
| `print_speed` | mm/s | 1 Dezimalstelle | > 0 | 50…90 |
| `extrusion_width` | mm | 3 Dezimalstellen | > 0 | 0,38…0,50 |
| `extrusion_multiplier` | Faktor | 3 Dezimalstellen | > 0 | 1,05…1,20 |
| `temperature` | °C | int | >= 0 | 215…235 |
| `fan_speed` | % | int | 0…100 | 30…80 |

Die Beispielgrenzen stammen aus `config/optimizer_config.example.json`, nicht aus einer allgemeinen Maschinensicherheitsfreigabe. Die JSON darf andere Werte innerhalb der breiten intrinsischen Domäne angeben. Der Betreiber trägt die Verantwortung für material- und hardwaregerechte Grenzen.

### Strategieoptionen

| Strategie | Option | Default | gültig |
| --- | --- | --- | --- |
| Bayesian | `acquisition` | `ei` | `ei` oder `thompson` |
| Bayesian | `candidate_count` | `4096` | int >= 64 |
| Bayesian | `n_restarts_optimizer` | `5` | int >= 0 |
| PSO | `inertia` | `0.7` | 0…1 |
| PSO | `cognitive_weight` | `1.5` | >= 0 |
| PSO | `social_weight` | `1.5` | >= 0 |
| PSO | `max_velocity` | `0.2` | > 0 und <= 1 |
| Differential Evolution | `differential_weight` | `0.8` | > 0 und <= 2 |
| Differential Evolution | `crossover_probability` | `0.9` | 0…1 |
| Random/Sobol | keine | – | unbekannte Optionen werden abgelehnt |

Penalty ist kein JSON-Feld: `--failure-result penalty` oder `ignore` speichert die Experimententscheidung; vor `--automatic-retry` ist eine solche persistierte Wahl Pflicht. Ohne gespeicherte Wahl verwendet ein nicht automatischer Hardwareaufruf intern Penalty als Default. Der numerische Wert ist im aktuellen `FailurePolicy` fest `100.0`. Logging hat ebenfalls kein Konfigurationsfeld: alle CLIs nutzen `INFO`, die Hardware-CLI schreibt zusätzlich `optimizer_hardware.log`.

| Feste Fehleroption | Wert | Konfigurierbar? | Quelle |
| --- | --- | --- | --- |
| vergleichbare Attempts pro Optimierer-Run | 2 | nicht per CLI/JSON | `FailurePolicy.maximum_attempts_per_run` |
| Penalty-Zielfunktionswert | 100,0 | nicht per CLI/JSON | `FailurePolicy.penalty_value` |
| Sicherheitsstopp nach Fehlsätzen | 3 nacheinander | nicht per CLI/JSON | `FailurePolicy.maximum_consecutive_failed_parameter_sets` |
| zusätzlicher QS-Aufruf im Orchestrator | 1 nach erstem Fehler | nein | `PrintOrchestrator._run_cycle` |
| SJ-Leseretrys bei `011`/`033` | insgesamt 5 Versuche | nur Konstruktor | `SJ220Service.__init__` |

## Slicer-Profil und Abbildung

`SlicerProfileGenerator` bewahrt alle nicht betroffenen Zeilen des Basisprofils und ersetzt:

| Logischer Parameter | Slicer-Schlüssel |
| --- | --- |
| `top_solid_layers` | `top_solid_layers` |
| `print_speed` | `top_solid_infill_speed` |
| `extrusion_width` | `top_infill_extrusion_width` |
| `extrusion_multiplier` | `extrusion_multiplier` |
| `temperature` | `temperature` |
| `fan_speed` | `min_fan_speed`, `max_fan_speed`, `bridge_fan_speed` |

Zusätzlich werden konstante Versuchsbedingungen erzwungen: `skirts=0`, `brim_width=0`, `top_solid_min_thickness=0`, `slowdown_below_layer_time=0`, `enable_dynamic_fan_speeds=0`. Fehlt ein benötigter Schlüssel im Basisprofil, bricht die Generierung ab.

Das aktuelle `config/slicer_profile.ini` enthält unter anderem Schichthöhe `0.2`, Fülldichte `0%`, Bett `60 °C`, erste Schicht `230 °C` bei Geschwindigkeit `15`, danach `220 °C`, fünf obere Vollschichten, Geschwindigkeit `80 mm/s`, Breite `0.42 mm`, Extrusionsfaktor `1.05` und Lüfter `80 %`. `slicer_profile_flat.ini` ist leer und nicht verwendbar; `slicer_profile_meins.ini` ist ein abweichender Altstand.

## Sichere Konfigurationsverwaltung

- Keine API-Schlüssel, Passwörter oder Tokens in Markdown, JSON, Git oder Screenshots aufnehmen.
- Vor `--new` einen neuen `paths.output_directory` wählen; ein bestehendes Verzeichnis wird absichtlich nicht überschrieben.
- Für `--resume` dieselbe JSON am selben Ort und dasselbe Zielverzeichnis verwenden. Der gespeicherte Hash enthält aufgelöste absolute Pfade; selbst ein Verschieben kann daher als Konfigurationsänderung gelten.
- Nach Start eines Optimierungslaufs Grenzen und Strategie nicht nachträglich ändern. Der Konfigurationssnapshot ist Teil der Reproduzierbarkeit.

Weiter: [05 – Hardware-Setup](05_hardware_setup.md)
