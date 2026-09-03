# 10 – Tests und Entwicklung

## Testwerkzeug und Aufbau

Die Tests verwenden Python `unittest`, `unittest.mock`, temporäre Verzeichnisse und kleine Fake-Hardwareadapter. Es gibt keine `pytest`-, Coverage-, Lint-, Formatter- oder CI-Konfiguration im Repository.

| Bereich | Testdateien | Abdeckung |
| --- | --- | --- |
| Orchestrator | `test_orchestrator.py`, `test_orchestrator_camera.py` | Reihenfolge, Status, Mess-Retry/Penalty, Kamera und Robot-Recovery |
| Druck | `test_print_parameters.py`, `test_slicer_service.py`, `test_prusalink_service.py` | Profilmapping, Domänen, Prozessaufruf und HTTP |
| QS/Kamera | `test_qs_api_client.py`, `test_camera_api.py`, `test_camera_client.py` | Payloads, Statuscodes, Download und Validierung |
| statischer Versuch | `test_experiment_plan.py`, `test_experiment_runner.py`, `test_csv_cycle_recorder.py`, `test_main.py` | Plan, Auswahl/Resume, Speicherung und CLI |
| Optimierer | `test_optimizer_config.py`, `test_warm_start.py`, `test_strategies.py`, `test_experiment_store.py`, `test_framework_runner.py` | Schema, Reproduzierbarkeit, alle Strategien, Persistenz, Retry/Pause |
| Hardwareadapter | `test_hardware_executor.py`, `test_hardware_cli.py` | Stufenklassifikation, Sicherheitsflags, Preflight-Receipt und Resume |
| veraltet | `test_bayesian_optimizer.py` | erwartet entferntes Legacy-Modul und läuft aktuell nicht |

Die Tests sind Unit- und dateibasierte Integrationstests. Sie ersetzen HTTP, Subprozesse und Roboter durch Mocks/Fakes. Es gibt keine automatisierten End-to-End-Tests gegen echte Geräte.

## Vollständiger Testlauf

**Arbeitsverzeichnis: `bachelor-3d-loop/3d-automation/`**

```bash
source ../.venv/bin/activate
export PYTHONPATH="$PWD/src"
python -m unittest discover -s tests -v
```

Für die Tests werden keine Hardware-Env-Werte benötigt. Der bei der Übergabe ausgeführte Lauf fand 130 Tests: 129 liefen erfolgreich, ein Testmodul scheiterte beim Import:

```text
ModuleNotFoundError: No module named 'optimizer.bayesian_optimizer'
```

Ursache ist `tests/test_bayesian_optimizer.py`, das die entfernte Legacy-API `BayesianOptimizer` und `read_optimization_history` importiert. Die aktuelle Implementierung liegt in `optimizer.strategies.BayesianStrategy` und verwendet `ExperimentStore`; die aktuellen Strategie-/Frameworktests decken diesen Weg ab. Der Test sollte migriert oder nach nachvollziehbarer Entscheidung entfernt werden.

## Sichere Zusatzprüfungen

```bash
python -m compileall -q src tests
python -m pip check
python -m optimizer.config config/optimizer_config.example.json --check-input-files
python -m optimizer.warm_start config/optimizer_config.example.json
```

Bei dieser Übergabe waren Kompilierung und `pip check` erfolgreich; Config und Warmstart liefen erfolgreich.

## Simulation als Integrationstest

Eine Simulation prüft Store, Vorschlagslogik, Checkpoints, CSV-Export und Resume gemeinsam. Sie kontaktiert keine Geräte.

1. `config/optimizer_config.simulation.json` kopieren.
2. In der Kopie einen noch nicht vorhandenen `paths.output_directory` setzen.
3. Einen begrenzten Erstlauf und Resume ausführen:

```bash
python -m optimizer.framework_runner \
  config/optimizer_config.simulation.local.json \
  --simulate --new --max-runs 2

python -m optimizer.framework_runner \
  config/optimizer_config.simulation.local.json \
  --simulate --resume --from-run 3 --max-runs 2
```

Der im Rahmen dieser Dokumentation ausgeführte frische Smoke-Test schloss Runs 1–2 und nach Resume 3–4 erfolgreich ab.

## Einzelne Tests ausführen

Beispiele, jeweils aus `3d-automation/`:

```bash
python -m unittest -v tests/test_orchestrator.py
python -m unittest -v tests/test_hardware_cli.py
python -m unittest -v tests/test_strategies.py
```

Ein erfolgreicher Lauf endet mit `OK`. `FAILED (failures=N)` bedeutet eine nicht erfüllte Assertion; `FAILED (errors=N)` meist eine Exception in Setup oder Testcode. Der aktuelle Legacy-Import ist ein `error`, kein nachgewiesener Fehler der neuen Strategie.

## Mocking-Strategie

`PrintOrchestrator` erwartet protokollartige Abhängigkeiten für Slicer, Drucker, Roboterfactory, QS, Recorder und Kamera. Tests implementieren nur die tatsächlich aufgerufenen Methoden und protokollieren Reihenfolge/Argumente. HTTP-Clients mocken `requests.Session`; Slicer-Tests mocken `subprocess.run`. `HardwareExecutorTest` stellt einen Fake-Orchestrator bereit, `HardwareCliTest` einen Builder, der nie echte Hardware konstruiert.

Neue Tests dürfen keine Standard-IP kontaktieren. Fakes sollten einen Fehler gezielt mit derselben `CycleStage` auslösen, die der Produktionsadapter verwendet.

## Hardwaretests

Es gibt keine automatisierte Hardware-Test-Suite. Vor Ort sollte eine versionierte Abnahmematrix geführt werden:

1. Slicer mit Referenz-STL und Profil.
2. PrusaLink Health, Upload ohne unbeabsichtigten Druck und anschließend kontrollierter Druck.
3. Roboter-`get_joints` ohne Bewegung.
4. Jede gelehrte Teilsequenz bei reduzierter Geschwindigkeit und leerer Vorrichtung.
5. Kamera-Health, Aufnahme und Download.
6. SJ-220 mit Referenznormal und erwarteten Ra/Rz-Bereichen.
7. Einzelzyklus, zwei statische Zyklen und ein Optimierer-Einzellauf.
8. Geplante Fehlerfälle: Netzunterbrechung, Kameraausfall und kontrollierter manueller Stopp.

Ergebnisse, Anlagenkonfiguration, Firmwareversionen und Freigabegrenzen sind im Repository derzeit nicht strukturiert erfasst.

## Neue Hardwarekomponente hinzufügen

1. Kleine Schnittstelle/Protocol mit zeitlich begrenzten Methoden definieren.
2. Adapter in einem eigenen Modul implementieren; Verbindung, Close und Timeout explizit behandeln.
3. Im `main.build_orchestrator()` verdrahten, ohne globale Initialisierung beim Import.
4. Neue `CycleStage` beziehungsweise Fehlerklassifikation bewusst festlegen: vorphysisch, vergleichbar oder terminal.
5. Orchestrator-Reihenfolge mit Fake testen.
6. Client-/Protokolltests für Fehlerantworten, Timeouts und ungültige Payloads ergänzen.
7. Env-Beispiel und Kapitel 04/05/09/11 aktualisieren.

## Neuen Druckparameter hinzufügen

1. `PrintParameters` und Validierung in `printer/print_parameters.py` erweitern.
2. Logischen Wert eindeutig auf einen Slicer-Schlüssel abbilden; Profil-Read/Write testen.
3. `PARAMETER_DEFINITIONS` und Vollständigkeitsprüfung in `optimizer/config.py` anpassen.
4. `_numeric_parameters`, `_parameter_key` und Hardware-Konvertierung aktualisieren.
5. Plan-CSV, `CsvCycleRecorder` und Optimierer-CSV-Schema migrieren.
6. Beispielkonfigurationen und Parameter-/Bounds-Tests ändern.
7. Wissenschaftliche Einheit, Quantisierung und sichere Maschinenlimits dokumentieren.

Eine Schemaänderung darf vorhandene Laufverzeichnisse nicht stillschweigend umdeuten; gegebenenfalls Schema-Version erhöhen und Migration implementieren.

## Neue Optimierungsstrategie hinzufügen

1. Alias und erlaubte Optionen in `optimizer/config.py` ergänzen.
2. `StrategyAdapter.propose()` implementieren und über `build_strategy()` registrieren.
3. Nur normierte Werte über `ParameterSpace` verarbeiten.
4. Deterministische Seeds und vollständigen JSON-serialisierbaren Zustand speichern.
5. Batchgröße und vollständige Vorresultate validieren.
6. Duplikate nach Quantisierung verhindern.
7. Factory-, Reproduzierbarkeits-, Resume-, Grenz- und unvollständige-Batch-Tests ergänzen.

## Logging und Debugging

Alle Haupt-CLIs konfigurieren `INFO` mit Zeit, Level, Loggername und Meldung. Hardwareläufe schreiben zusätzlich `<output_directory>/logs/optimizer_hardware.log`. Für tiefere SJ-Protokolldiagnose existieren DEBUG-Meldungen für TX/RX in ASCII und Hex, aber kein CLI-Schalter. Für eine lokale Diagnose kann der Log-Level im kontrollierten Entwicklungszweig angehoben werden; keine seriellen Logs veröffentlichen, ohne sie auf sensible Betriebsdaten zu prüfen.

Wichtige Diagnoseartefakte:

- `run_state.json` für Gesamtstatus;
- `runs/run_NNNN.json` und `attempt_history/` für Übergänge;
- Preflight-Receipts in `logs/`;
- `optimizer_state/` für Vorschlagsreproduzierbarkeit;
- `hardware_cycles.csv` und Bilder für den physischen Ablauf.

## Erkennbare Codekonventionen

Der aktuelle Kern verwendet Typannotationen, `dataclass(frozen=True)`, kleine Adapterklassen, `pathlib.Path`, spezifische Exceptions und `unittest`. Atomare JSON-Schreibvorgänge verwenden temporäre Dateien, Flush, `fsync` und `os.replace`. Es gibt jedoch keine formal konfigurierte Style-/Lint-Regel. Bei Änderungen sollten bestehende Typen und 79–88-Zeichen-Zeilenstil beibehalten und alle betroffenen Tests ergänzt werden.

Weiter: [11 – API-Referenz](11_api_referenz.md)
