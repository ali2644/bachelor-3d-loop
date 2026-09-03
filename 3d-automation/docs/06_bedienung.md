# 06 – Bedienung

## Gemeinsame Shell-Vorbereitung

Wenn nicht anders angegeben, werden alle Befehle aus `bachelor-3d-loop/3d-automation/` ausgeführt.

```bash
source ../.venv/bin/activate
export PYTHONPATH="$PWD/src"
```

Für Hardware zusätzlich:

```bash
set -a
source config/end_to_end.env
set +a
```

> **Hardwarewarnung:** `robot-qs`, `full`, `experiment`, `qs.run_sj220`, `robot.robot_service` und ein bestätigter `optimizer.hardware_cli`-Lauf können reale Geräte bewegen. Die Befehle sind aus dem Code verifiziert, wurden bei dieser Dokumentation aber nicht an der Anlage ausgeführt.

## Hilfe und sichere Diagnose

```bash
python -m main --help
python -m optimizer.config --help
python -m optimizer.warm_start --help
python -m optimizer.framework_runner --help
python -m optimizer.hardware_cli --help
```

Alle Befehle sollen Usage-Text liefern und ohne Hardwarezugriff enden.

### Optimiererkonfiguration prüfen

```bash
python -m optimizer.config \
  config/optimizer_config.example.json \
  --check-input-files
```

Erwartet wird die normalisierte Konfiguration als JSON. Fehlercode 1 und eine Meldung entstehen bei ungültigem Schema oder fehlenden Eingabedateien.

### Warmstart anzeigen

```bash
python -m optimizer.warm_start config/optimizer_config.example.json
```

Dies gibt die deterministische Punktfolge aus, legt aber weder ein Experimentverzeichnis an noch kontaktiert es Hardware.

## Betriebsmodi von `main`

### Preflight

Zweck: lokale Pfade, Slicer, Kamera, Drucker, QS-API und Roboterverbindung prüfen, ohne Roboterbewegung oder Druckstart.

```bash
python -m main --mode preflight
```

Vor der Prüfung erzeugt `main` aus dem Basisprofil ein zyklusspezifisches Profil in `data/generated_profiles/`. Die QS-Healthprüfung wartet höchstens 300 Sekunden und fragt alle 10 Sekunden erneut an. Erfolg endet mit `Preflight passed. No robot movement was performed.` und Exitcode 0. Ein Drucker muss `IDLE` oder `FINISHED` melden.

Es existiert kein eigener `--dry-run`-Schalter. Für Anlagenchecks dient `preflight`; für Optimiererlogik dient `--simulate`.

### Robot-QS-Ablauf

Zweck: ein bereits vorhandenes, korrekt bereitgestelltes Bauteil greifen, zur QS bringen, messen und ausschieben. Slicing, Druck, Kamera und Abkühlzeit werden übersprungen.

```bash
python -m main --mode robot-qs
```

Erfolg: JSON mit `status: "completed"`, `stage: "completed"`, Cycle-ID sowie `measurements` mit `Ra` und `Rz`; zusätzlich eine Zeile in `data/results/parameter_optimization_cycles.csv`. Bei einem Fehler endet der Prozess mit Exitcode 1. Beenden mit `Ctrl+C` ist kein geregelter Recovery-Vorgang; danach die Anlage physisch prüfen.

### Vollständiger Einzelversuch

```bash
python -m main \
  --mode full \
  --top-solid-layers 5 \
  --print-speed 80 \
  --extrusion-width 0.42 \
  --extrusion-multiplier 1.05 \
  --temperature 220 \
  --fan-speed 80
```

Ohne Parameterargumente werden die sechs Werte aus `config/slicer_profile.ini` übernommen. Der Lauf erzeugt Profil und G-Code, lädt den G-Code mit automatischem Druckstart hoch, überwacht den Status, nimmt ein Bild auf, wartet die Abkühlzeit, bewegt den Roboter, misst und schreibt CSV. Erfolg ist das abschließende CycleResult-JSON plus `status=completed` in der CSV.

### Statische Versuchsreihe neu starten

```bash
python -m main \
  --mode experiment \
  --experiment-plan config/experiment_plans/experiment_plan_100.csv \
  --experiment-start-cycle 1 \
  --experiment-cycles 2 \
  --experiment-plan-seed 42
```

Dies erzeugt **vor** der Hardwareausführung einen neuen 100-Zeilen-Plan. Eine vorhandene Plandatei wird archiviert. `--experiment-cycles 2` bedeutet „bis einschließlich Zeile 2“, also zwei Zyklen nur bei Start 1. Pro Planzeile entstehen `cycle_NNN`-Profil/G-Code und eine CSV-Zeile. Der Runner bricht beim ersten geworfenen Zyklusfehler ab; eine Mess-Penalty des Orchestrators gilt dagegen als abgeschlossen.

Die Datei `experiment_plan_20.csv` kann von `main` nicht direkt verwendet werden, weil der Loader dort weiterhin exakt 100 Zeilen erwartet.

### Statische Versuchsreihe fortsetzen

Nach Sichtprüfung der Ergebnis-CSV und der Anlage die erste **nicht erfolgreich ausgeführte** Plannummer bestimmen, im Beispiel 42:

```bash
python -m main \
  --mode experiment \
  --experiment-plan config/experiment_plans/experiment_plan_100.csv \
  --experiment-start-cycle 42 \
  --experiment-cycles 100 \
  --reuse-experiment-plan
```

`--reuse-experiment-plan` ist zwingend, sonst wird der Plan ersetzt. Die Software leitet Start 42 nicht automatisch aus der Ergebnisdatei ab und verhindert keine manuell erzeugten Duplikate. `--experiment-plan-seed` darf beim Reuse nicht gesetzt werden.

## Einzelne QS-Komponenten

### QS-/Kamera-API starten

Auf dem Raspberry Pi, Arbeitsverzeichnis `bachelor-3d-loop/3d-automation/`:

```bash
source .venv-pi/bin/activate
export PYTHONPATH="$PWD/src"
python -m uvicorn qs.api:app --host 0.0.0.0 --port 8000
```

Beenden mit `Ctrl+C`, aber nicht während einer Messbewegung.

### Einzelne Messung

Auf dem Pi, nur mit korrekt positioniertem Teil:

```bash
python -m qs.run_sj220
```

Alternativ über die laufende API vom Hauptrechner:

```bash
curl --fail --show-error \
  -X POST "$QS_BASE_URL/measurements"
```

### Kamerabild aufnehmen

Vom Hauptrechner; erzeugt eine eindeutige 32-stellige Cycle-ID:

```bash
CAMERA_CYCLE_ID="$(python -c 'import uuid; print(uuid.uuid4().hex)')"
curl --fail --show-error \
  -X POST "$CAMERA_BASE_URL/camera/captures/$CAMERA_CYCLE_ID"
curl --fail --show-error \
  "$CAMERA_BASE_URL/camera/captures/$CAMERA_CYCLE_ID" \
  --output "$CAMERA_CYCLE_ID.jpg"
```

Wenn `CAMERA_BASE_URL` nicht separat gesetzt ist, im Befehl `$QS_BASE_URL` verwenden. Erfolg sind Status `completed` und ein nicht leeres JPEG.

## Hardwarefreie Optimierersimulation

Vor dem ersten Lauf muss das in der JSON konfigurierte `paths.output_directory` noch nicht existieren. Falls der mitgelieferte Simulationspfad schon vorhanden ist, kopieren Sie die JSON und wählen darin einen neuen Zielnamen.

```bash
cp config/optimizer_config.simulation.json \
  config/optimizer_config.simulation.local.json
```

In `simulation.local.json` anschließend `paths.output_directory` ändern, zum Beispiel auf `../data/optimization_runs/framework_simulation_local`. Dann:

```bash
python -m optimizer.framework_runner \
  config/optimizer_config.simulation.local.json \
  --simulate \
  --new \
  --max-runs 6
```

Erfolg: JSON-Zusammenfassung; `results.csv`, `run_state.json` und `runs/*.json` im Zielverzeichnis. `--max-runs` zählt in diesem Prozess abgeschlossene Parametersätze.

Fortsetzung ab dem vom Store erwarteten Lauf, beispielsweise 7:

```bash
python -m optimizer.framework_runner \
  config/optimizer_config.simulation.local.json \
  --simulate \
  --resume \
  --from-run 7 \
  --max-runs 6
```

`--from-run` ist eine Konsistenzprüfung, kein Sprung über offene Läufe. Bei einem gespeicherten retry-fähigen Simulationsfehler kommt `--retry-failed` hinzu.

## Optimierer mit Hardware

### Lokale Konfiguration vorbereiten

```bash
cp config/optimizer_config.example.json \
  config/optimizer_config.hardware.local.json
```

In der Kopie mindestens `experiment_name`, sichere Parametergrenzen und ein **neues** `paths.output_directory` eintragen. Das Basisprofil und STL vor Ort prüfen. Die Datei enthält keine Zugangsdaten; diese bleiben in `end_to_end.env`.

### Neues Experiment anlegen und preflighten

```bash
python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.local.json \
  --new \
  --preflight-only \
  --failure-result penalty
```

Alternativ kann die einmalige, danach unveränderliche Fehlerentscheidung `ignore` lauten. Der Befehl persistiert Run 1 als Vorschlag, erzeugt das Profil und reserviert den G-Code-Pfad, prüft Dienste und schreibt eine Receipt-Datei. Er führt noch keinen Slicer-Lauf aus. `hardware_started` ist `false`; es wird nicht gedruckt und der Roboter nicht bewegt.

### Ersten physischen Lauf starten

```bash
python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.local.json \
  --resume \
  --from-run 1 \
  --max-runs 1 \
  --confirm-hardware
```

Die gespeicherte Preflight-Receipt muss zu Experiment, Run, Attempt und Parametern passen. Erfolg: `completed_in_this_call: 1`, aktualisierte JSON/CSV, G-Code, Bild und Log. Ohne `--confirm-hardware` startet kein physischer Lauf.

### Bewachte Folgeausführung mit automatischem Retry

```bash
python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.local.json \
  --resume \
  --max-runs 4 \
  --automatic-retry \
  --confirm-hardware
```

Vor jedem neuen Attempt wird eine vorhandene passende Preflight-Receipt geprüft oder ein Preflight ausgeführt. Ein sicher klassifizierter physischer Fehler kann denselben Satz einmal zusätzlich ausführen; deshalb können bei `--max-runs 4` mehr als vier physische Zyklen entstehen.

### Gespeicherten retry-fähigen Fehler wiederholen

Zuerst Preflight für denselben Satz, beispielhaft Run 7:

```bash
python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.local.json \
  --resume \
  --from-run 7 \
  --retry-failed \
  --preflight-only
```

Danach:

```bash
python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.local.json \
  --resume \
  --from-run 7 \
  --retry-failed \
  --max-runs 1 \
  --confirm-hardware
```

### Nach manuellem Eingriff fortsetzen

Nur für einen terminal gestoppten Run und nach physischer Fehlerbehebung:

```bash
python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.local.json \
  --resume \
  --from-run 7 \
  --resume-after-manual-intervention \
  --preflight-only
```

Danach den bestätigten Resume-Befehl ohne `--resume-after-manual-intervention`, aber mit `--from-run 7 --confirm-hardware` ausführen. Eine manuelle Freigabe erhöht die Attempt-Nummer; dafür gibt es derzeit keine Zwei-Attempt-Grenze.

Nach drei endgültig fehlgeschlagenen Parametersätzen wird ein Sicherheitsstopp quittiert:

```bash
python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.local.json \
  --resume \
  --from-run 7 \
  --acknowledge-failure-streak \
  --preflight-only
```

Ein nach hartem Prozessabbruch dauerhaft als `running` gespeicherter Run hat aktuell keinen unterstützten CLI-Recovery-Pfad. Nicht per Hand JSON editieren; Zustand sichern und die Implementierung ergänzen beziehungsweise projektverantwortlich entscheiden.

## Checklisten

### 1. Erster Start ohne Hardware

- [ ] Virtuelle Umgebung aktiv, `PYTHONPATH` gesetzt.
- [ ] `compileall` und `pip check` erfolgreich.
- [ ] Beispiel-JSON mit `optimizer.config` gültig.
- [ ] Warmstart-Preview plausibel und reproduzierbar.
- [ ] Neues Simulation-Ziel gewählt; kurzen `--new`- und `--resume`-Lauf ausführen.

### 2. Erster Preflight mit Hardware

- [ ] Geräte eingeschaltet, Netz/USB geprüft, Arbeitsräume frei.
- [ ] Pi-API gestartet; `/health` und `/camera/health` erfolgreich.
- [ ] Lokale Env-Datei geladen; Schlüssel nicht im Terminal ausgegeben.
- [ ] PrusaLink-Status, Roboterverbindung und Dateien erreichbar.
- [ ] `python -m main --mode preflight` erfolgreich.

### 3. Vollständiger Einzelversuch

- [ ] Parameter und Slicer-Vorschau fachlich freigegeben.
- [ ] Leeres/sauberes Bett und freie Roboterbahn bestätigt.
- [ ] Preflight unmittelbar vorher erfolgreich.
- [ ] `main --mode full` unter Aufsicht starten.
- [ ] Druck, Bild, mechanischen Transfer, Messung und CSV kontrollieren.

### 4. Vollständige statische Versuchsreihe

- [ ] Seed und 100-Zeilen-Plan archiviert beziehungsweise bewusst neu erzeugt.
- [ ] Erst zwei Zyklen (`1…2`) als Grenztest ausführen.
- [ ] Ergebnis-CSV und Bauteile nach jedem Block prüfen.
- [ ] Bei Unterbrechung erfolgreichen letzten Lauf feststellen.
- [ ] Ausschließlich mit `--reuse-experiment-plan` und korrektem Start fortsetzen.

### 5. Optimierungslauf

- [ ] Experiment-JSON validiert; Zielpfad neu; Grenzen sicher.
- [ ] Penalty oder Ignore wissenschaftlich entschieden.
- [ ] `--new --preflight-only` erfolgreich.
- [ ] Ersten Run einzeln mit Bestätigung ausführen.
- [ ] Erst danach kleine, beaufsichtigte Batches verwenden.
- [ ] `results.csv`, Runs, Bilder und Log regelmäßig sichern.

### 6. Fortsetzung nach Abbruch

- [ ] Keine Hardware bewegt sich; Drucker/Roboter/SJ physisch prüfen.
- [ ] Zielverzeichnis unverändert sichern; Run-JSON lesen, nicht editieren.
- [ ] Status (`retryable_failed`, `terminal_failed`, Pause oder `running`) feststellen.
- [ ] Passenden dokumentierten Resume-Pfad wählen.
- [ ] Preflight-Receipt neu erzeugen beziehungsweise prüfen.
- [ ] Einen einzelnen bestätigten Run ausführen und Ergebnis kontrollieren.

Weiter: [07 – Versuche und Daten](07_versuche_und_daten.md)
