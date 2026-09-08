# 06 – Bedienung

Diese Anleitung beschreibt die Bedienung des Systems aus Sicht der Person, die
Versuche plant, startet, überwacht, fortsetzt und die Ergebnisse weitergibt.
Für die Bedienung ist kein Verständnis jeder Python-Klasse erforderlich.

## 1. Die zwei Programmeinstiege

Es gibt zwei getrennte Bedienwege:

| Einstieg | Zweck | Ergebnisverwaltung |
|---|---|---|
| `python -m main` | Preflight, Roboter-QS-Test, einzelner Druck oder vorgegebener CSV-Versuchsplan | ausdrücklich angegebene `--results-csv` |
| `python -m optimizer.hardware_cli` | Optimierer mit Warmstart, BO, PSO, DE, Random oder Sobol | eigener Experimentordner aus der Optimierer-JSON |

`main` und das Optimierer-Framework sollen nicht gleichzeitig auf die Anlage
zugreifen.

## 2. Sicherheits- und Datenregeln

1. Vor Hardwarebefehlen Druckbett, Roboterbereich, Zuführung und Messstation
   prüfen.
2. Es darf immer nur ein steuernder Prozess laufen.
3. Ein neuer Versuch erhält einen neuen Ergebnisnamen beziehungsweise einen
   neuen `output_directory`.
4. Eine begonnene Optimierer-Konfiguration wird nicht verändert. Änderungen an
   STL, Profil, Grenzen, Zielfunktion oder Strategie erfordern ein neues
   Experiment.
5. `--new` bedeutet wirklich neues Experiment. `--resume` öffnet ein
   vorhandenes Experiment.
6. Einen physischen Optimiererlauf niemals ohne vorherigen erfolgreichen
   Preflight starten.
7. Bei einem unklaren Roboter- oder Anlagenzustand zuerst die Anlage prüfen und
   erst danach einen Wiederanlauf bestätigen.

## 3. Einrichtung auf einem neuen Benutzerkonto

### 3.1 Projektstand laden

Im bereits geklonten Repository:

```bash
git fetch origin
git switch feature/optimizer-framework-integration
git pull --ff-only
git status -sb
```

Erwartet wird ein sauberer Arbeitsbaum. Falls der Branch lokal noch nicht
existiert:

```bash
git switch --track origin/feature/optimizer-framework-integration
```

### 3.2 Python-Umgebung

Vom Repository-Ordner `bachelor-3d-loop` aus:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r 3d-automation/requirements.txt
cd 3d-automation
```

Vor jedem neuen Terminal:

```bash
cd ~/Projects/bachelor-3d-loop
source .venv/bin/activate
cd 3d-automation
export PYTHONPATH="$PWD/src"
```

Der Hardwarebetrieb ist für den Linux-Laborrechner vorgesehen. Auf einem
Windows-Laptop können Konfiguration, Simulation und viele Tests betrachtet
werden; Robotik, serielle QS-Anbindung und Laborpfade sind dort nicht
betriebsbereit.

### 3.3 Lokale Umgebungsdatei

Einmalig:

```bash
cp config/end_to_end.env.example config/end_to_end.env
chmod 600 config/end_to_end.env
nano config/end_to_end.env
```

Mindestens zu prüfen:

| Variable | Bedeutung |
|---|---|
| `PRINTER_IP` | IP-Adresse des PrusaLink-Druckers |
| `PRUSALINK_API_KEY` | persönlicher beziehungsweise freigegebener API-Key |
| `ROBOT_IP` | IP-Adresse des Niryo-Roboters |
| `QS_BASE_URL` | Basis-URL der QS-API auf dem Raspberry Pi |
| `CAMERA_BASE_URL` | Kamera-API; normalerweise gleich `QS_BASE_URL` |
| `PRUSASLICER_PATH` | lokaler Pfad zur PrusaSlicer-AppImage |
| `REMOTE_GCODE_PATH` | Zielpfad auf dem Drucker |
| `PRINT_POLL_SECONDS` | Abstand zwischen Druckerstatusabfragen |
| `PRINT_START_TIMEOUT_SECONDS` | maximale Zeit bis der neue Druck aktiv ist |
| `PRINT_TIMEOUT_SECONDS` | maximale Druckdauer |
| `MAX_STATUS_ERRORS` | erlaubte aufeinanderfolgende Statusfehler |
| `PART_COOLING_SECONDS` | Abkühlzeit vor der Roboterbewegung |

Die Datei in die aktuelle Shell laden:

```bash
set -a
source config/end_to_end.env
set +a
```

`config/end_to_end.env` enthält Zugangsdaten und wird nicht committed.

### 3.4 Offline-Abnahme

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Alle Tests müssen mit `OK` enden. Die Tests verwenden simulierte Dienste und
starten weder Drucker noch Roboter.

## 4. Eingabedateien auswählen

Vor einem Versuch müssen vier Arten von Eingaben bewusst gewählt werden:

| Eingabe | Beispiel | Regel |
|---|---|---|
| STL-Modell | `data/models/15x15_V2_rounded.stl` | vor jedem neuen Experiment prüfen |
| Slicer-Basisprofil | `config/slicer_profile.ini` | muss ein vollständiges, funktionierendes Profil sein |
| Ergebnisziel für `main` | `data/results/validation_2026-09-08.csv` | neuer Dateiname für neue Reihe |
| Optimierer-Konfiguration | `config/optimizer_config.hardware.json` | enthält zusätzlich Strategie und Experimentordner |

Absolute und relative Pfade in einer Optimierer-JSON sind erlaubt. Relative
Pfade werden relativ zum Ordner der JSON-Datei aufgelöst.

## 5. Bedienung von `main`

### 5.1 Warum `--results-csv` immer angegeben wird

`--results-csv` ist jetzt ein Pflichtargument. Dadurch kann nicht mehr
unbemerkt eine alte Standard-CSV mit einem anderen Spaltenschema verwendet
werden. Eine vorhandene Datei wird beim Programmstart geprüft, also vor Druck
und Roboterbewegung.

Regel:

- neue Versuchsreihe: neuer CSV-Dateiname;
- Fortsetzung derselben Reihe: dieselbe kompatible CSV;
- alte oder anders aufgebaute CSV: nicht überschreiben, sondern neuen Namen
  wählen oder die alte Datei separat archivieren.

Nur das unmittelbar vorherige Programmschema ohne die neue Spalte
`print_time_seconds` wird verlustfrei ergänzt. Andere Fremd- oder Altschemata
werden weiterhin abgelehnt.

### 5.2 Preflight

```bash
PYTHONPATH=src python -m main \
  --mode preflight \
  --stl data/models/15x15_V2_rounded.stl \
  --profile config/slicer_profile.ini \
  --results-csv data/results/preflight_check.csv
```

Der Preflight prüft Dateien und erreichbare Dienste. Er startet keinen Druck
und bewegt den Roboter nicht. Die angegebene Ergebnisdatei wird durch einen
erfolgreichen Preflight nicht beschrieben; sie ist trotzdem ausdrücklich
angegeben, damit jeder `main`-Aufruf dieselbe eindeutige Form hat.

### 5.3 Nur Roboter und QS mit vorhandenem Bauteil

```bash
PYTHONPATH=src python -m main \
  --mode robot-qs \
  --stl data/models/15x15_V2_rounded.stl \
  --profile config/slicer_profile.ini \
  --results-csv data/results/robot_qs_2026-09-08.csv
```

Das Bauteil muss vorher an der eingelernten Position liegen. Es wird nicht
gesliced oder gedruckt. Robotertransport, QS-Messung und Ergebnisaufzeichnung
werden ausgeführt.

### 5.4 Ein vollständiger Zyklus mit Profilwerten

```bash
PYTHONPATH=src python -m main \
  --mode full \
  --stl data/models/15x15_V2_rounded.stl \
  --profile config/slicer_profile.ini \
  --generated-profiles-dir data/generated_profiles \
  --gcode data/gcode/single_cycle.gcode \
  --results-csv data/results/single_cycle_2026-09-08.csv
```

Ohne Parameterargumente werden die sechs Werte aus dem Basisprofil gelesen.

### 5.5 Ein vollständiger Zyklus mit allen Parameterargumenten

```bash
PYTHONPATH=src python -m main \
  --mode full \
  --stl data/models/15x15_V2_rounded.stl \
  --profile config/slicer_profile.ini \
  --generated-profiles-dir data/generated_profiles \
  --gcode data/gcode/single_cycle_all_arguments.gcode \
  --results-csv data/results/single_cycle_all_arguments.csv \
  --top-solid-layers 5 \
  --print-speed 70.0 \
  --extrusion-width 0.42 \
  --extrusion-multiplier 1.10 \
  --temperature 225 \
  --fan-speed 60
```

Diese Parameter gelten nur für einen einzelnen `full`- oder `robot-qs`-Aufruf.
Im Modus `experiment` kommen die Parameter aus dem CSV-Plan; dort werden
Parameterargumente abgelehnt.

### 5.6 Neuen CSV-Versuchsplan erzeugen und ausführen

Das folgende Beispiel erzeugt reproduzierbar einen 100-Zeilen-Plan und führt
die Einträge 1 bis einschließlich 20 aus:

```bash
mkdir -p data/results

RESULTS_CSV="data/results/experiment_$(date +%Y%m%d_%H%M%S).csv"

printf '%s\n' "$RESULTS_CSV" \
  > data/results/active_experiment_results.txt

PYTHONPATH=src python -m main \
  --mode experiment \
  --stl data/models/15x15_V2_rounded.stl \
  --profile config/slicer_profile.ini \
  --generated-profiles-dir data/generated_profiles \
  --gcode data/gcode/experiment.gcode \
  --results-csv "$RESULTS_CSV" \
  --experiment-plan config/experiment_plans/experiment_plan_100.csv \
  --experiment-start-cycle 1 \
  --experiment-cycles 100 \
  --experiment-plan-seed 42
```

`--experiment-cycles` ist die Nummer des letzten Eintrags, nicht die Anzahl ab
dem Start. Beispiel: Start 49 und Ende 100 führen 52 Zyklen aus.

Ohne `--reuse-experiment-plan` wird ein neuer Plan erzeugt. Der vorherige Plan
wird im Archivordner gesichert.

### 5.7 Unterbrochenen CSV-Versuchsplan fortsetzen

```bash
RESULTS_CSV="$(cat data/results/active_experiment_results.txt)"

PYTHONPATH=src python -m main \
  --mode experiment \
  --stl data/models/15x15_V2_rounded.stl \
  --profile config/slicer_profile.ini \
  --generated-profiles-dir data/generated_profiles \
  --gcode data/gcode/experiment.gcode \
  --results-csv "$RESULTS_CSV" \
  --experiment-plan config/experiment_plans/experiment_plan_100.csv \
  --experiment-start-cycle 38 \
  --experiment-cycles 100 \
  --reuse-experiment-plan
```

Beim Fortsetzen darf `--experiment-plan-seed` nicht zusätzlich angegeben
werden. Sonst wäre unklar, ob der bestehende oder ein neuer Plan gemeint ist.

## 5.8 Ergebnisse einer `main`-Versuchsreihe gemeinsam speichern

Für jede neue Versuchsreihe wird ein eigener Ordner angelegt. Darin werden folgende Dateien gespeichert:

- verwendetes STL-Modell,
- verwendetes Slicer-Basisprofil,
- Parameterplan,
- generierte Slicer-Profile,
- erzeugte G-Code-Dateien,
- Kamerabilder,
- Ergebnis-CSV,
- vollständige Terminalausgabe als Logdatei.

### 5.8.1 Neue Versuchsreihe starten

> Dieser Block darf nur für eine neue Versuchsreihe verwendet werden.  
> Für die Fortsetzung einer unterbrochenen Reihe muss der Befehl aus dem nächsten Abschnitt verwendet werden.

Den folgenden Block vollständig kopieren und im Projektordner ausführen:

```bash
set -o pipefail

mkdir -p data/experiments

RUN_DIR="data/experiments/main_$(date +%Y%m%d_%H%M%S_%N)"

mkdir -p "$RUN_DIR"/{input,generated_profiles,gcode,images,logs}

cp data/models/15x15_V2_rounded.stl \
  "$RUN_DIR/input/model.stl"

cp config/slicer_profile.ini \
  "$RUN_DIR/input/base_profile.ini"

printf '%s\n' "$RUN_DIR" \
  > data/experiments/active_main_experiment.txt

CAMERA_DOWNLOAD_DIR="$RUN_DIR/images" \
PYTHONPATH=src python -m main \
  --mode experiment \
  --stl "$RUN_DIR/input/model.stl" \
  --profile "$RUN_DIR/input/base_profile.ini" \
  --generated-profiles-dir "$RUN_DIR/generated_profiles" \
  --gcode "$RUN_DIR/gcode/output.gcode" \
  --results-csv "$RUN_DIR/results.csv" \
  --experiment-plan "$RUN_DIR/experiment_plan_100.csv" \
  --experiment-start-cycle 1 \
  --experiment-cycles 100 \
  --experiment-plan-seed 42 \
  2>&1 | tee "$RUN_DIR/logs/main.log"
```

Der Zeitstempel sorgt dafür, dass jede Versuchsreihe einen neuen eindeutigen Ordner erhält, zum Beispiel:

```text
data/experiments/main_20260907_143215_382019475/
```

Die Datei

```text
data/experiments/active_main_experiment.txt
```

enthält den Pfad der aktuell laufenden Versuchsreihe. Dadurch muss sich der Bediener den erzeugten Zeitstempel nicht merken.

Die Ergebnisse werden folgendermaßen abgelegt:

```text
data/experiments/main_20260907_143215_382019475/
├── input/
│   ├── model.stl
│   └── base_profile.ini
├── experiment_plan_100.csv
├── generated_profiles/
│   ├── cycle_001_profile.ini
│   ├── cycle_002_profile.ini
│   └── ...
├── gcode/
│   ├── cycle_001.gcode
│   ├── cycle_002.gcode
│   └── ...
├── images/
│   ├── <cycle-id>.jpg
│   └── ...
├── logs/
│   └── main.log
└── results.csv
```

Bedeutung der wichtigsten Dateien:

| Datei oder Ordner | Inhalt |
|---|---|
| `input/model.stl` | Kopie des verwendeten Druckmodells |
| `input/base_profile.ini` | Kopie des verwendeten Slicer-Basisprofils |
| `experiment_plan_100.csv` | Parameter aller 100 geplanten Zyklen |
| `generated_profiles/` | Für jeden Zyklus erzeugtes Slicer-Profil |
| `gcode/` | Für jeden Zyklus erzeugter G-Code |
| `images/` | Von der Kamera aufgenommene Bauteilbilder |
| `results.csv` | Ergebnisse und Zustände der ausgeführten Zyklen |
| `logs/main.log` | Vollständige Terminalausgabe der Versuchsreihe |

### 5.8.2 Unterbrochene Versuchsreihe fortsetzen

Beim Fortsetzen darf kein neuer Versuchsordner und kein neuer Parameterplan erzeugt werden.

Zuerst muss bestimmt werden, welcher Zyklus als Nächstes ausgeführt werden soll.

Beispiel:

- Zyklus 37 wurde erfolgreich abgeschlossen.
- Die Fortsetzung beginnt deshalb bei Zyklus 38.
- `--experiment-cycles 100` bedeutet, dass bis einschließlich Zyklus 100 ausgeführt wird.

Den folgenden Block vollständig kopieren und ausführen:

```bash
set -o pipefail

RUN_DIR="$(cat data/experiments/active_main_experiment.txt)"

CAMERA_DOWNLOAD_DIR="$RUN_DIR/images" \
PYTHONPATH=src python -m main \
  --mode experiment \
  --stl "$RUN_DIR/input/model.stl" \
  --profile "$RUN_DIR/input/base_profile.ini" \
  --generated-profiles-dir "$RUN_DIR/generated_profiles" \
  --gcode "$RUN_DIR/gcode/output.gcode" \
  --results-csv "$RUN_DIR/results.csv" \
  --experiment-plan "$RUN_DIR/experiment_plan_100.csv" \
  --experiment-start-cycle 38 \
  --experiment-cycles 100 \
  --reuse-experiment-plan \
  2>&1 | tee -a "$RUN_DIR/logs/main.log"
```

Die Zahl hinter `--experiment-start-cycle` muss durch die Nummer des nächsten auszuführenden Zyklus ersetzt werden.

Beispiele:

| Letzter vollständig abgeschlossener Zyklus | Nächster Startwert |
|---:|---:|
| 10 | `--experiment-start-cycle 11` |
| 37 | `--experiment-start-cycle 38` |
| 60 | `--experiment-start-cycle 61` |
| 99 | `--experiment-start-cycle 100` |

Beim Fortsetzen bewirkt `--reuse-experiment-plan`, dass der vorhandene Parameterplan unverändert geladen wird.

Außerdem werden weiterhin dieselben Ablagen verwendet:

- dieselbe `results.csv`,
- derselbe Bilderordner,
- derselbe G-Code-Ordner,
- derselbe Profilordner,
- dieselbe Logdatei.

`tee -a` hängt die neue Terminalausgabe an die vorhandene Logdatei an. Die vorherige Ausgabe wird dadurch nicht überschrieben.

### 5.8.3 Wichtige Regeln beim Fortsetzen

Beim Fortsetzen dürfen folgende Bestandteile nicht verwendet werden:

```text
$(date ...)
--experiment-plan-seed
```

Ein neuer Zeitstempel würde einen neuen Ordner erzeugen. Ein neuer Seed würde einen neuen Parameterplan erzeugen.

Zum Fortsetzen werden stattdessen immer verwendet:

```text
data/experiments/active_main_experiment.txt
--reuse-experiment-plan
```

### 5.8.4 Aktuellen Versuchsordner anzeigen

```bash
cat data/experiments/active_main_experiment.txt
```

### 5.8.5 Gespeicherte Dateien anzeigen

```bash
RUN_DIR="$(cat data/experiments/active_main_experiment.txt)"

find "$RUN_DIR" -maxdepth 2 -type f | sort
```

### 5.8.6 Hinweis zur Ordneraufteilung

Dieser Ablauf erstellt einen gemeinsamen Ordner für eine vollständige Versuchsreihe.

Die einzelnen Zyklen erhalten darin jeweils:

- ein eigenes generiertes Slicer-Profil,
- eine eigene G-Code-Datei,
- ein eigenes Kamerabild,
- eine eigene Zeile in `results.csv`.

Es wird nicht für jeden einzelnen Zyklus ein separater Hauptordner erstellt.

### 5.9 Alle `main`-Argumente

| Argument | Wirkung |
|---|---|
| `--mode` | `preflight`, `robot-qs`, `full` oder `experiment` |
| `--stl` | verwendetes Modell |
| `--profile` | unverändertes Basisprofil |
| `--generated-profiles-dir` | Ablage der erzeugten Profile |
| `--gcode` | G-Code-Ziel; bei Experimenten wird dessen Ordner verwendet |
| `--results-csv` | Pflichtziel für Zyklusergebnisse |
| `--experiment-plan` | CSV-Datei mit 100 Parametersätzen |
| `--experiment-start-cycle` | erster Planindex, inklusive |
| `--experiment-cycles` | letzter Planindex, inklusive |
| `--reuse-experiment-plan` | vorhandenen Plan beibehalten |
| `--experiment-plan-seed` | Seed für einen reproduzierbaren neuen Plan |
| sechs Parameterargumente | Einzelzykluswerte; im Experimentmodus verboten |

## 6. Optimierer-Konfiguration

### 6.1 Grundstruktur

```json
{
  "schema_version": 1,
  "experiment_name": "surface_roughness_example_001",
  "total_runs": 100,
  "seed": 42,
  "objective": "Ra_um + 0.1 * print_time_minutes",
  "warm_start": {
    "method": "lhs",
    "sample_count": 10
  },
  "strategy": {
    "name": "bayesian",
    "options": {
      "acquisition": "ei",
      "candidate_count": 4096,
      "n_restarts_optimizer": 5
    }
  },
  "parameters": [
    {"name": "print_speed", "lower": 50, "upper": 90},
    {"name": "extrusion_width", "lower": 0.38, "upper": 0.50},
    {"name": "extrusion_multiplier", "lower": 1.05, "upper": 1.20},
    {"name": "temperature", "lower": 215, "upper": 235},
    {"name": "fan_speed", "lower": 30, "upper": 80}
  ],
  "fixed_parameters": {
    "top_solid_layers": 5
  },
  "paths": {
    "stl": "../data/models/15x15_V2_rounded.stl",
    "base_profile": "slicer_profile.ini",
    "output_directory": "../data/optimization_runs/example_001",
    "history_csvs": []
  }
}
```

### 6.2 Felder

| Feld | Bedeutung |
|---|---|
| `schema_version` | Formatversion; aktuell `1` |
| `experiment_name` | eindeutiger lesbarer Name |
| `total_runs` | Zahl abgeschlossener Parametersätze, nicht physischer Versuche |
| `seed` | reproduzierbare Zufallsfolge |
| `objective` | zu minimierende Messgröße oder Rechenformel |
| `warm_start.method` | `lhs`, `random` oder `sobol` |
| `warm_start.sample_count` | Zahl der Startpunkte; bei Batchstrategien zugleich Batchgröße |
| `strategy.name` | `bayesian`, `pso`, `differential_evolution`, `random` oder `sobol` |
| `strategy.options` | Optionen der gewählten Strategie |
| `parameters` | variable Parameter und frei gewählte Grenzen |
| `fixed_parameters` | nicht optimierte Parameter |
| `paths.output_directory` | ausschließlich für dieses Experiment |
| `paths.history_csvs` | reserviert; aktuell immer `[]`, Import noch nicht implementiert |

Jeder der sechs Prozessparameter muss genau einmal vorkommen: entweder variabel
in `parameters` oder fest in `fixed_parameters`.

### 6.3 Frei wählbare Grenzen und Top-Layer

`top_solid_layers` bleibt für den aktuellen Versuch fest auf 5:

```json
"fixed_parameters": {"top_solid_layers": 5}
```

Für einen späteren Versuch kann es stattdessen optimiert werden:

```json
"parameters": [
  {"name": "top_solid_layers", "lower": 3, "upper": 7}
],
"fixed_parameters": {
  "print_speed": 70,
  "extrusion_width": 0.42,
  "extrusion_multiplier": 1.10,
  "temperature": 225,
  "fan_speed": 60
}
```

Formale Mindestregeln: Geschwindigkeiten, Breiten und Multiplikator sind größer
als null; Temperatur und Top-Layer sind nichtnegative ganze Zahlen; Lüfter ist
eine ganze Zahl von 0 bis 100; bei Variablen gilt `lower < upper`. Formal
gültige extreme Grenzen sind nicht automatisch physikalisch sicher.

### 6.4 Zielfunktion

`objective` ist eine sichere arithmetische Formel. Verfügbare Größen:

| Name | Einheit | Bedeutung |
|---|---:|---|
| `Ra_um` | µm | gemessener Ra-Wert |
| `Rz_um` | µm | gemessener Rz-Wert |
| `print_time` | s | beobachtete Druckzeit |
| `print_time_seconds` | s | eindeutiger Alias für `print_time` |
| `print_time_minutes` | min | Druckzeit geteilt durch 60 |

Erlaubt sind Zahlen, Klammern und `+`, `-`, `*`, `/`, `**`. Nicht erlaubt
sind Funktionsaufrufe, Vergleiche, Imports oder beliebige Python-Ausdrücke.

Beispiele:

```json
"objective": "Ra_um"
```

```json
"objective": "Ra_um + 0.1 * print_time_minutes"
```

```json
"objective": "5 + print_time_minutes * Ra_um + Rz_um"
```

Die Gewichte bestimmen die fachliche Bedeutung. Sekundenwerte sind numerisch
viel größer als Rauheitswerte; deshalb ist meist `print_time_minutes` oder ein
kleiner Faktor sinnvoll.

`print_time` wird ab dem Warten auf den nach dem Upload gestarteten Druck bis
zum beobachteten Zustand `FINISHED` gemessen. Slicing, Kamera, Abkühlen,
Roboterbewegung und QS-Messung gehören nicht dazu. `duration_seconds` in
`hardware_cycles.csv` ist dagegen die Gesamtdauer des gesamten Zyklus.

Bei einem Parametersatz, der zweimal fehlschlägt, wird die Formel nicht mit
erfundenen Ra-, Rz- oder Zeitwerten ausgewertet. Im Modus `penalty` wird direkt
`objective_value = 100.0` gespeichert. Deshalb muss 100 auf der Skala der
gewählten Formel tatsächlich ein schlechter Wert sein. Andernfalls ist für
dieses Experiment `ignore` die fachlich sichere Wahl.

### 6.5 Strategiebedingungen

- Bayesian: nach dem Warmstart jeweils ein neuer Vorschlag.
- PSO, DE, Random und Sobol: Vorschläge in vollständigen Batches der Größe
  `warm_start.sample_count`.
- Bei den Batchstrategien muss `total_runs - sample_count` ohne Rest durch
  `sample_count` teilbar sein.
- PSO benötigt mindestens 2 Startpunkte, DE mindestens 4.

## 7. Optimierer offline prüfen

### 7.1 JSON und Eingabedateien prüfen

```bash
PYTHONPATH=src python -m optimizer.config \
  config/optimizer_config.hardware.json \
  --check-input-files
```

Ohne `--check-input-files` wird nur Struktur und Inhalt der JSON geprüft.

### 7.2 Warmstartpunkte anzeigen

```bash
PYTHONPATH=src python -m optimizer.warm_start \
  config/optimizer_config.hardware.json
```

Das erzeugt keine Hardwarebewegung und legt noch kein Experiment an.

### 7.3 Neue Simulation

Vorher in der Simulations-JSON einen noch nicht vorhandenen
`output_directory` wählen:

```bash
PYTHONPATH=src python -m optimizer.framework_runner \
  config/optimizer_config.simulation.json \
  --new \
  --simulate \
  --max-runs 3
```

### 7.4 Simulation fortsetzen

```bash
PYTHONPATH=src python -m optimizer.framework_runner \
  config/optimizer_config.simulation.json \
  --resume \
  --simulate \
  --from-run 4 \
  --max-runs 2
```

`--retry-failed` wird nur verwendet, wenn der gespeicherte nächste Run den
Status `retryable_failed` besitzt:

```bash
PYTHONPATH=src python -m optimizer.framework_runner \
  config/optimizer_config.simulation.json \
  --resume \
  --simulate \
  --from-run 4 \
  --retry-failed \
  --max-runs 1
```

## 8. Neues Optimierer-Hardwareexperiment

### 8.1 Konfiguration kopieren

```bash
cp config/optimizer_config.example.json \
  config/optimizer_config.hardware.json
nano config/optimizer_config.hardware.json
```

Prüfen:

- neuer `experiment_name`;
- neuer, noch nicht vorhandener `output_directory`;
- richtige STL;
- richtiges Basisprofil;
- gewünschte Grenzen und feste Parameter;
- gewünschte Zielfunktion;
- Strategie, Warmstart und Gesamtzahl;
- `history_csvs` ist `[]`.

### 8.2 Fehlerergebnis einmalig wählen und Preflight ausführen

Penalty soll in den Optimierer eingehen:

```bash
PYTHONPATH=src python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.json \
  --new \
  --failure-result penalty \
  --preflight-only
```

Fehlerhafter Parametersatz soll nicht als Optimiererbeobachtung eingehen:

```bash
PYTHONPATH=src python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.json \
  --new \
  --failure-result ignore \
  --preflight-only
```

Die Wahl wird in `run_state.json` gespeichert und darf innerhalb des
Experiments nicht gewechselt werden.

### 8.3 Genau einen Parametersatz ausführen

```bash
PYTHONPATH=src python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.json \
  --resume \
  --from-run 1 \
  --max-runs 1 \
  --confirm-hardware
```

Ohne `--max-runs` ist 1 der Standard. Ohne `--confirm-hardware` wird kein
physischer Optimiererzyklus gestartet.

### 8.4 Mehrere Parametersätze automatisch ausführen

Beispiel für 12 abgeschlossene Parametersätze:

```bash
PYTHONPATH=src python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.json \
  --resume \
  --from-run 1 \
  --max-runs 12 \
  --automatic-retry \
  --confirm-hardware
```

`--max-runs 12` zählt Parametersätze, nicht physische Drucke. Ein automatisch
wiederholter Fehlversuch kann also zusätzliche physische Zyklen verursachen.
Vor jedem Versuch wird ein Preflight-Nachweis erzeugt oder geprüft.

## 9. Fehler- und Wiederanlaufregeln

### 9.1 Normaler vergleichbarer Fehler

Bei einem vergleichbaren Druck-/Status- oder Messfehler:

1. Versuch 1 wird mit Fehler archiviert.
2. Mit `--automatic-retry` werden dieselben Parameter genau einmal wiederholt.
3. Bei Erfolg werden echte Werte gespeichert.
4. Bei erneutem Fehler wird der Parametersatz als `penalty` oder
   `ignored_failure` abgeschlossen.
5. Ein dritter automatischer Versuch ist nicht erlaubt.

Ohne automatischen Modus wird der erste Fehler bewusst sichtbar. Danach:

```bash
PYTHONPATH=src python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.json \
  --resume \
  --from-run X \
  --retry-failed \
  --preflight-only
```

Nach erfolgreichem Preflight:

```bash
PYTHONPATH=src python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.json \
  --resume \
  --from-run X \
  --max-runs 1 \
  --confirm-hardware
```

### 9.2 Preflight-Fehler

Ein Preflight-Fehler verbraucht keinen physischen Versuch. Ursache beheben und
denselben Run erneut preflighten:

```bash
PYTHONPATH=src python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.json \
  --resume \
  --from-run X \
  --retry-failed \
  --preflight-only
```

### 9.3 Roboterfehler oder unklarer Anlagenzustand

Diese Fälle stoppen ohne Optimiererbeobachtung. Erst Anlage und Teil prüfen,
dann denselben Run vorbereiten:

```bash
PYTHONPATH=src python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.json \
  --resume \
  --from-run X \
  --resume-after-manual-intervention \
  --preflight-only
```

Nach dem Preflight normal mit `--confirm-hardware` starten.

### 9.4 Programmabsturz mit Runstatus `running`

Zuerst sicherstellen, dass kein alter Python-Prozess, Druckauftrag oder
Roboterbefehl mehr aktiv ist. Anlage manuell prüfen. Erst dann:

```bash
PYTHONPATH=src python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.json \
  --resume \
  --from-run X \
  --resume-interrupted-run \
  --preflight-only
```

Der unterbrochene Zustand wird archiviert und derselbe Parametersatz als neuer
manuell bestätigter Versuch vorbereitet.

### 9.5 Drei fehlerhafte Parametersätze hintereinander

Nach drei Parametersätzen, die jeweils nach zwei vergleichbaren Versuchen ohne
Messung abgeschlossen wurden, stoppt der Dauerlauf. Nach Ursachenprüfung wird
der gespeicherte nächste Run bestätigt:

```bash
PYTHONPATH=src python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.json \
  --resume \
  --from-run X \
  --acknowledge-failure-streak \
  --preflight-only
```

`--acknowledge-penalty-streak` ist ein kompatibler alter Name für dasselbe
Argument. Die Grenze zählt auch im Modus `ignore`.

### 9.6 Typische Fehlermeldungen

| Meldung | Bedeutung | Reaktion |
|---|---|---|
| output directory already exists | `--new` auf vorhandenen Ordner | `--resume` verwenden oder neuen Ordner konfigurieren |
| supplied configuration differs | JSON nach Start verändert | ursprüngliche JSON verwenden oder neues Experiment starten |
| safe resume point is run X | falsches `--from-run` | genau X verwenden |
| preflight receipt is missing | Versuch nicht freigeprüft | `--preflight-only` ausführen |
| existing cycle CSV has a different schema | `main`-CSV stammt aus anderer Version | neue Ergebnisdatei wählen |
| status `running` | Prozess wurde möglicherweise unterbrochen | Anlage prüfen, dann `--resume-interrupted-run` |
| requires manual intervention | unsicherer Hardwarezustand | manuell prüfen, dann manueller Resume |

## 10. Was gespeichert wird

Ein Optimiererexperiment besitzt diese Struktur:

```text
output_directory/
├── config_snapshot.json
├── run_state.json
├── results.csv
├── hardware_cycles.csv
├── runs/
├── attempt_history/
├── optimizer_state/
├── generated_profiles/
├── gcode/
├── images/
└── logs/
```

| Ort | Inhalt |
|---|---|
| `config_snapshot.json` | unveränderter Konfigurationsnachweis mit aufgelösten Pfaden |
| `run_state.json` | Gesamtfortschritt, sicherer nächster Run, Fehlerfolge und Fehlerergebnismodus |
| `runs/run_XXXX.json` | verbindlicher aktueller Zustand eines Parametersatzes |
| `attempt_history/` | frühere Fehl- oder Wiederanlaufversuche unverändert archiviert |
| `results.csv` | eine lesbare Zeile je abgeschlossenem Parametersatz |
| `hardware_cycles.csv` | jeder tatsächlich vom Orchestrator aufgezeichnete Hardwarezyklus |
| `optimizer_state/` | Strategie-Checkpoint und kompletter vorgeschlagener Batch |
| `generated_profiles/` | Profil je Run und Versuch |
| `gcode/` | G-Code je Run und Versuch |
| `images/` | Kamerabild je Hardwarezyklus |
| `logs/optimizer_hardware.log` | Ablauf- und Fehlermeldungen |
| `logs/preflight_*.json` | Preflight-Nachweis je Run und Versuch |

`results.csv` enthält unter anderem `objective_value`, echte `Ra_um` und
`Rz_um`, `print_time_seconds`, `observation_kind`, Penalty-/Ignore-Kennzeichen,
Parameter, Fehler und `cycle_id`.

Die Abschlussausgabe des Hardware-CLI zeigt unter `last_completed_result`
zusätzlich das letzte Zielergebnis, Ra, Rz und `print_time_seconds`. Bei einem
Batch stehen alle Ergebnisse weiterhin vollständig in `results.csv`.

Nicht gespeichert werden API-Keys aus der Umgebung. Der reale mechanische
Zustand der Anlage kann nicht vollständig aus Dateien rekonstruiert werden und
muss nach einem Abbruch immer vor Ort geprüft werden.

## 11. PSO- und DE-Zustand

Ja, beide Zustände werden gespeichert. Vor der ersten physischen Ausführung
eines neuen Batches entsteht ein unveränderlicher JSON-Checkpoint unter:

```text
output_directory/optimizer_state/
```

PSO speichert insbesondere:

- Partikel-IDs, Positionen und Geschwindigkeiten;
- persönliche Bestpositionen und Fitnesswerte;
- globale Bestposition und globalen Bestwert;
- Zufallszustand;
- alle Vorschläge des aktuellen Batches.

Differential Evolution speichert insbesondere:

- Individuen/Population und Fitnesswerte;
- Trial-Population;
- Zufallszustand;
- alle Vorschläge des aktuellen Batches.

Wenn der Prozess beim X-ten Kandidaten eines Batches stoppt, werden bereits
abgeschlossene Kandidaten nicht erneut gedruckt. Der gespeicherte Batch wird
geladen und beim noch offenen X-ten Run fortgesetzt.

Kontrolle:

```bash
ls -lt data/optimization_runs/EXPERIMENT/optimizer_state
python -m json.tool \
  data/optimization_runs/EXPERIMENT/optimizer_state/DATEINAME.json
```

## 12. Zustand und Ergebnisse kontrollieren

Gesamtzustand:

```bash
python -m json.tool \
  data/optimization_runs/EXPERIMENT/run_state.json
```

Einzelner Parametersatz:

```bash
python -m json.tool \
  data/optimization_runs/EXPERIMENT/runs/run_0001.json
```

Letzte Ergebnisse:

```bash
tail -n 5 data/optimization_runs/EXPERIMENT/results.csv
tail -n 5 data/optimization_runs/EXPERIMENT/hardware_cycles.csv
```

Letzte Logmeldungen:

```bash
tail -n 100 \
  data/optimization_runs/EXPERIMENT/logs/optimizer_hardware.log
```

## 13. Daten an einen anderen Rechner übergeben

Der vollständige Experimentordner ist die Übergabeeinheit:

```bash
cd data/optimization_runs
zip -r EXPERIMENT.zip EXPERIMENT
```

Die ZIP-Datei kann per freigegebenem Netzlaufwerk, `scp` oder USB-Datenträger
übergeben werden. Für eine reine Auswertung reichen oft `results.csv`,
`hardware_cycles.csv` und `images/`; für eine vollständige Reproduzierbarkeit
sollte immer der ganze Experimentordner übertragen werden.

## 14. Argument- und Fallabdeckung

Die automatisierten Tests decken alle Bedienargumente und Zustandsübergänge
ohne echte Hardware ab. Zusätzlich müssen Hardwarefälle kontrolliert vor Ort
abgenommen werden.

| Fall | Offline-Test | Reale Abnahme |
|---|---|---|
| alle `main`-Pfade und Einzelparameter | `tests/test_main.py` | Preflight, robot-qs, full |
| neue/fortgesetzte CSV-Reihe | `tests/test_main.py` | je ein kontrollierter Lauf |
| LHS, Random, Sobol | `tests/test_warm_start.py` | Warmstartausgabe prüfen |
| BO, PSO, DE, Random, Sobol | `tests/test_framework_runner.py` | mindestens gewählte Produktivstrategie |
| `--new`, `--resume`, `--from-run`, `--max-runs` | Framework-/Hardware-CLI-Tests | Start und Fortsetzung |
| automatischer Retry, Penalty und Ignore | Hardware-CLI- und Runner-Tests | provozierbarer Messfehler nur unter Aufsicht |
| Preflight-Fehler | `tests/test_hardware_cli.py` | Verbindung vor Druck trennen, falls freigegeben |
| manueller Stopp | `tests/test_hardware_cli.py` | nur bei echtem Fehler anwenden |
| unterbrochener Prozess | `tests/test_hardware_cli.py` | nicht absichtlich bei Bewegung provozieren |
| drei Fehlerparameter hintereinander | `tests/test_framework_runner.py` | Simulation genügt; nicht absichtlich Hardware belasten |
| Formel und Druckzeit | `tests/test_objective.py`, Runner-/Recorder-Tests | einen erfolgreichen Druckwert prüfen |
| inkompatible Ergebnis-CSV | `tests/test_csv_cycle_recorder.py` | keine physische Provokation nötig |

Vollständige Offline-Abnahme:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Weiter: [07 – Versuche und Daten](07_versuche_und_daten.md)
