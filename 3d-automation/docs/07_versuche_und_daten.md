# 07 – Versuche und Daten

## Zwei Datenmodelle

Das Projekt besitzt zwei Ausführungs- und Speicherwege:

| Weg | Start | Primärer Zustand | Wiederaufnahme |
| --- | --- | --- | --- |
| statischer Plan / Einzelzyklus | `python -m main` | append-only `parameter_optimization_cycles.csv` | manuell über Planbereich |
| Optimierer | `optimizer.framework_runner` oder `optimizer.hardware_cli` | `ExperimentStore` mit JSON, Checkpoints und neu gebauter `results.csv` | zustandsbasiert über `--resume` |

Diese Formate sind nicht austauschbar. Besonders enthält die statische CSV weder Optimiereriteration noch Attempt-Nummer.

## Statischer Versuchsplan

Die CSV-Kopfzeile muss exakt lauten:

```csv
cycle_number,top_solid_layers,print_speed,extrusion_width,extrusion_multiplier,temperature,fan_speed
```

Beispiel einer syntaktisch gültigen Zeile:

```csv
1,5,80,0.42,1.05,220,80
```

| Spalte | Einheit | Bedeutung |
| --- | --- | --- |
| `cycle_number` | – | fortlaufend ab 1, lückenlos |
| `top_solid_layers` | Schichten | Zahl oberer Vollschichten |
| `print_speed` | mm/s | Geschwindigkeit oberer Vollfüllung |
| `extrusion_width` | mm | Breite der oberen Füllung |
| `extrusion_multiplier` | Faktor | Extrusionsmengenfaktor |
| `temperature` | °C | Düsentemperatur nach der ersten Schicht |
| `fan_speed` | % | fester Lüfterwert im erzeugten Profil |

`load_experiment_plan()` prüft Header, Zahlen, fortlaufende Cycle-Nummern, erwartete Zeilenzahl und eindeutige Parametersätze. `main --mode experiment` setzt die erwartete Zahl fest auf 100.

### Automatische Plangenerierung

`generate_experiment_plan()` verwendet einen Latin Hypercube aus der Python-Standardbibliothek `random`. Jede Dimension erhält einen zufälligen Punkt je gleich großem Intervall und wird unabhängig gemischt. Die festen Grenzen sind:

| Parameter | Bereich |
| --- | --- |
| `top_solid_layers` | fest 5 |
| `print_speed` | 50…90 mm/s |
| `extrusion_width` | 0,38…0,50 mm |
| `extrusion_multiplier` | 1,05…1,20 |
| `temperature` | 215…235 °C |
| `fan_speed` | 30…80 % |

Ohne Seed wird ein zufälliger 63-Bit-Seed erzeugt und im Log genannt. Der Plan wird zunächst in `config/experiment_plans/archive/` geschrieben und dann atomar aktiviert. Eine vorhandene aktive CSV wird zusätzlich als `..._replaced_...csv` archiviert.

## Profil- und G-Code-Erzeugung

Für jeden Zyklus erzeugt `SlicerProfileGenerator` ein vollständiges, vom Basisprofil abgeleitetes INI. Einzelzyklen landen standardmäßig in `data/generated_profiles/`; statische Planläufe verwenden zyklusbezogene Dateinamen. Im Optimierer heißen sie beispielsweise:

```text
generated_profiles/run_0007_attempt_02_profile.ini
gcode/run_0007_attempt_02.gcode
```

Der Generator ersetzt die sechs Parameter sowie fünf feste Versuchsbedingungen. Das erzeugte Profil wird über SHA-256 im statischen Ergebnis erfasst. `SlicerService` löscht eine schon vorhandene G-Code-Zieldatei vor dem Aufruf und wartet höchstens 600 Sekunden. Dadurch ist die Zieldatei kein Archiv: Eindeutige Run-/Attempt-Namen sind wichtig.

## Ergebnis eines Einzel- oder Planzyklus

Standardpfad: `data/results/parameter_optimization_cycles.csv`. Das Schema ist stabil und wird vor jedem Append mit der vorhandenen Kopfzeile verglichen.

| Feld | Inhalt |
| --- | --- |
| `cycle_id` | UUID-Text des physischen Zyklus |
| `mode` | `full` oder `robot-qs` |
| `status` | `completed` oder Fehlerstatus des `CycleResult` |
| `failed_stage` | bei Erfolg leer, sonst letzte Stufe |
| `error` | Fehlermeldung oder leer |
| `started_at`, `finished_at` | ISO-8601-Zeitpunkte |
| `duration_seconds` | Laufzeit, auf 3 Stellen gerundet |
| `stl_path`, `profile_path`, `gcode_path` | verwendete lokale Pfade |
| `profile_sha256` | Hash des erzeugten Profils |
| `camera_image_path` | lokale JPEG-Kopie oder leer |
| `Ra_um`, `Rz_um` | Rauheitswerte in µm |
| `printer_states` | beobachtete Zustände, mit ` -> ` verbunden |
| `parameter_*` | sechs tatsächlich verwendete Parameter |

Die Datei wird nach jeder Zeile geflusht und per `fsync` synchronisiert. Sie enthält aber keine globale Transaktion zusammen mit G-Code oder Bild. Ein harter Abbruch zwischen Teilschritten kann deshalb unvollständige Artefakte hinterlassen.

## Optimierer-Laufverzeichnis

Ein neu angelegter `ExperimentStore` erzeugt:

```text
<output_directory>/
├── config_snapshot.json
├── run_state.json
├── results.csv                    # nach Ergebnissen erzeugt
├── runs/run_0001.json
├── attempt_history/
├── optimizer_state/
├── generated_profiles/
├── gcode/
├── logs/
├── hardware_cycles.csv            # nur Hardware-CLI
└── images/                         # nur Hardware-CLI
```

### `config_snapshot.json`

Enthält die normalisierte Konfiguration mit absoluten Pfaden. `source_path` wird gespeichert; der Konfigurationshash wird allerdings ohne `source_path`, aber mit den übrigen aufgelösten Pfaden berechnet. Deshalb kann ein Umzug von Daten, Profil oder Zielverzeichnis einen Resume verhindern.

### `run_state.json`

| Feldgruppe | Beispiele / Bedeutung |
| --- | --- |
| Identität | `experiment_id`, `experiment_name`, `config_sha256` |
| Fortschritt | `status`, `total_runs`, `completed_runs`, `current_run_number` |
| Fehlerserie | `consecutive_penalty_runs`, `consecutive_ignored_runs`, `consecutive_failed_parameter_sets` |
| Policy | `failure_observation_mode` = `penalty`, `ignore` oder `null` |
| Pause | `last_error`, `pause_reason`, `resume_run_number` |
| Audit | `created_at`, `updated_at` |

Der Store gleicht beim Öffnen den zusammengefassten Zustand mit den einzelnen Run-Dateien ab. Hash-, Schema- oder Sequenzwidersprüche führen zum Abbruch statt zu stiller Korrektur.

### `runs/run_NNNN.json`

Jeder Run enthält:

- `run_number`, `attempt_number`, `status`;
- Strategie und `optimizer_iteration` (`null` im Warmstart);
- alle sechs Parameter;
- `cycle_id`, `objective_value`, `Ra_um`, `Rz_um`;
- `is_penalty`, `is_ignored`, `soft_failure_count`;
- `failed_stage`, `error` und Zeitpunkte.

Der aktuelle Datensatz ist die autoritative Sicht auf einen Parametersatz. Frühere Zustände werden vor relevanten Übergängen in `attempt_history/run_NNNN_attempt_NN*.json` archiviert.

### `optimizer_state/`

Dateien wie `bayesian_iteration_0000.json` enthalten einen Checkpoint samt bereits festgelegtem Vorschlagsbatch. Der Checkpoint wird vor dem ersten physischen Lauf des Batches gespeichert. Nach Resume wird deshalb derselbe Vorschlag verwendet und kein neuer Zufallspunkt erzeugt.

## `results.csv` des Optimierers

Die Datei wird atomar aus allen abgeschlossenen Run-JSONs neu aufgebaut.

| Feld | Bedeutung |
| --- | --- |
| `run_number`, `attempt_number` | Parametersatz und letzter physischer/manueller Versuch |
| `strategy`, `optimizer_iteration` | Erzeuger und Iteration; Warmstartiteration leer |
| sechs Parameterfelder | tatsächlich vorgeschlagener, quantisierter Satz |
| `objective_value` | für Optimierung verwendeter Wert; `Ra_um` oder Penalty 100 |
| `Ra_um`, `Rz_um` | echte Messung; bei Penalty/Ignore leer |
| `observation_kind` | `measured`, `penalty` oder `ignored_failure` |
| `is_penalty`, `is_ignored` | boolesche Kennzeichen |
| `soft_failure_count` | Zahl vergleichbarer Fehlschläge |
| `failed_stage`, `error`, `cycle_id` | Diagnose und physische Zuordnung |

Beispielschema, Werte nur illustrativ:

```csv
run_number,attempt_number,strategy,optimizer_iteration,top_solid_layers,print_speed,extrusion_width,extrusion_multiplier,temperature,fan_speed,objective_value,Ra_um,Rz_um,observation_kind,is_penalty,is_ignored,soft_failure_count,failed_stage,error,cycle_id
1,1,bayesian,,5,72.0,0.421,1.08,222,55,4.2,4.2,24.8,measured,False,False,0,,,0123456789abcdef0123456789abcdef
```

## Bilder und Logs

Die Pi-API speichert `<cycle_id>.jpg` in `CAMERA_OUTPUT_DIR`. Der Hauptrechner lädt dasselbe Bild nach `CAMERA_DOWNLOAD_DIR`; die Hardware-CLI setzt dieses Verzeichnis auf `<output_directory>/images`. `hardware_cycles.csv` referenziert die lokale Datei.

`optimizer_hardware.log` enthält INFO-Logs der Hardware-CLI und der aufgerufenen Module. Einzel-/Planläufe loggen standardmäßig nur auf die Konsole. Die Logkonfiguration ist aktuell nicht über Datei oder CLI einstellbar.

## Retry, Penalty und Ignore in den Daten

- Ein Fehler vor physischem Verbrauch (`preflight`, `slicing`) behält den Attempt für eine Korrektur frei.
- Ein vergleichbarer Fehler verbraucht einen Attempt. `prepare_retry()` behält dieselben Parameter und erhöht `attempt_number`.
- Nach zwei vergleichbaren Fehlschlägen wird der Run abgeschlossen: bei `penalty` mit `objective_value=100`, bei `ignore` ohne Zielfunktionswert.
- Ein terminaler Fehler bleibt `terminal_failed`, bis der Operator ihn nach Anlagenprüfung freigibt; manuelle Freigaben können Attempt-Nummern über 2 erzeugen.
- Drei aufeinanderfolgende endgültig fehlgeschlagene Parametersätze setzen `pause_reason` und `resume_run_number`.

## Überschreiben und doppelte Ergebnisse vermeiden

1. Für jeden neuen Optimiererlauf ein noch nicht vorhandenes Zielverzeichnis wählen; `ExperimentStore.create()` verweigert Überschreiben.
2. Nie Run-JSON, Checkpoint oder `run_state.json` von Hand ändern.
3. Für Resume unveränderte Konfiguration und Pfade verwenden.
4. Statische Pläne nur mit `--reuse-experiment-plan` fortsetzen und Startnummer gegen CSV und physische Teile prüfen.
5. Vor Backup den Prozess sauber beenden; immer das komplette Laufverzeichnis gemeinsam kopieren.
6. `results.csv` als Lesesicht behandeln, Run-JSONs als Quelle des Optimiererzustands.

Weiter: [08 – Optimierer](08_optimierer.md)
