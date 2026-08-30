# Schritt 10: automatischer Wiederholungs- und Fehlerlauf

Diese Version setzt die gemeinsam festgelegte Regel für den Hardware-Dauerlauf um.

## Ablauf pro Parametersatz

1. Versuch 1 wird ausgeführt.
2. Bei einem sicher vergleichbaren Fehler wird derselbe Parametersatz automatisch als Versuch 2 ausgeführt.
3. Ist Versuch 2 erfolgreich, werden die echten Messwerte gespeichert.
4. Schlägt Versuch 2 ebenfalls fehl, wird der Parametersatz abgeschlossen. Die zu Beginn gewählte Fehlerbehandlung entscheidet, ob eine Penalty in den Optimierer eingeht.
5. Ein dritter Versuch desselben Parametersatzes ist nicht möglich.

Eine erfolgreiche Messung setzt den Zähler der aufeinanderfolgenden fehlerhaften Parametersätze auf null. Nach drei fehlerhaften Parametersätzen direkt hintereinander stoppt das Programm kontrolliert.

## Wahl zu Beginn des Experiments

Der Dauerlauf verlangt einmalig eine der beiden Optionen:

- `--failure-result penalty`: `objective_value = 100.0`, `is_penalty = true`; der Optimierer verwendet die Penalty.
- `--failure-result ignore`: `objective_value = null`, `is_ignored = true`; der Optimierer erhält keine Beobachtung für diesen Parametersatz.

Die Wahl wird in `run_state.json` unter `failure_observation_mode` gespeichert. Ein späterer Wechsel innerhalb desselben Experiments wird abgelehnt.

Unabhängig von der Wahl zählt ein nach zwei Versuchen fehlgeschlagener Parametersatz für `consecutive_failed_parameter_sets`.

## Sicherheitsgrenzen

Automatisch wiederholt werden nur Fehler, die das Framework als sicher vergleichbar klassifiziert. Ein Preflight-Fehler verbraucht keinen Versuch und stoppt den unbeaufsichtigten Lauf. Ein Roboterfehler, eine Kollision oder ein unklarer Anlagenzustand führt weiterhin sofort zu einem manuellen Stopp.

## Installation

Das ZIP-Archiv im Projektordner entpacken:

```bash
unzip -o ~/Downloads/optimizer-framework-schritt-10.zip \
  -d ~/Projects/bachelor-3d-loop/3d-automation
```

Danach die Offline-Tests ausführen:

```bash
PYTHONPATH=src python tests/test_experiment_store.py
PYTHONPATH=src python tests/test_framework_runner.py
PYTHONPATH=src python tests/test_hardware_executor.py
PYTHONPATH=src python tests/test_hardware_cli.py
PYTHONPATH=src python tests/test_orchestrator.py
PYTHONPATH=src python tests/test_orchestrator_camera.py
```

## Fortsetzung des vorhandenen Experiments ab Run 6

Wenn Penalties in die Optimierung eingehen sollen:

```bash
PYTHONPATH=src python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.new_model.json \
  --resume \
  --from-run 6 \
  --max-runs 7 \
  --automatic-retry \
  --failure-result penalty \
  --confirm-hardware
```

Wenn zweimal fehlgeschlagene Parametersätze nicht in die Optimierung eingehen sollen, wird lediglich `penalty` durch `ignore` ersetzt.

`--max-runs 7` bezeichnet die sieben Parametersätze Run 6 bis Run 12. Der automatische zweite Versuch zählt nicht als zusätzlicher Parametersatz.

Vor dem Hardwarestart müssen Druckbett, Roboterbereich, Zuführung und Messstation geprüft und frei sein.
