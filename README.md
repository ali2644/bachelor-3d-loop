# Automated R.E.P.P.R.I.N.T. - 3D-Druck-Qualitätsregelkreis

Dieses Repository automatisiert einen geschlossenen Versuchs- und Optimierungskreislauf für den FFF-3D-Druck. Ein Python-Orchestrator erzeugt aus Prozessparametern ein PrusaSlicer-Profil, überträgt den G-Code per PrusaLink, überwacht den Druck, lässt einen Niryo Ned2 das Bauteil in eine Qualitätsstation einlegen, liest `Ra` und `Rz` eines Mitutoyo SJ-220 aus und speichert Messwerte sowie Kamerabild. Ein separates Optimierer-Framework kann daraus den nächsten Parametersatz bestimmen.

> **Sicherheit:** Die Modi `robot-qs`, `full`, `experiment` und der bestätigte Optimierer-Hardwarelauf bewegen reale Hardware. Vor dem Start Arbeitsräume räumen, Not-Aus erreichbar halten und die mechanische Anordnung prüfen. Roboterbewegungen niemals blind wiederholen.

## Aktueller Stand

Der Stand dieses Übergabepakets basiert auf Branch `feature/optimizer-framework-integration`, Commit `29f11b9`.

| Bereich | Stand |
| --- | --- |
| Slicer, PrusaLink, Robotik, QS und Kamera | Im End-to-End-Orchestrator verbunden; reale Hardware hier nicht erneut getestet |
| Statischer Versuchsplan | Bis 100 Planzeilen, manueller Start-/Endbereich und Plan-Wiederverwendung |
| Optimierer | LHS/Random/Sobol-Warmstart sowie Bayesian, PSO, Differential Evolution, Random und Sobol; Hardwareadapter und persistenter Zustand vorhanden |
| Resume | Für vorgeschlagene, retry-fähige und terminal klassifizierte Läufe vorhanden; ein nach Prozessabbruch als `running` verbliebener Lauf besitzt noch keinen unterstützten CLI-Freigabepfad |
| Installation | Linux-orientiert; Dependency-Dateien sind derzeit unvollständig und werden in der Installationsanleitung erläutert |
| Tests | 129 Tests erfolgreich; ein veralteter Test importiert das nicht mehr vorhandene Modul `optimizer.bayesian_optimizer` |

## System in einem Satz

```text
Parameter -> Profil -> G-Code -> Druck -> Kamera -> Roboter -> Rauheitsmessung -> Speicherung -> nächster Parameter
```

Die Steueranwendung läuft auf dem Hauptrechner. Die FastAPI für SJ-220 und Kamera läuft auf dem Raspberry Pi. Drucker und Roboter werden über das lokale Netz angesprochen; das Messgerät hängt seriell, die Kamera per V4L2 am Raspberry Pi.

## Voraussetzungen in Kürze

- Linux auf Hauptrechner und Raspberry Pi; Python 3.10 oder neuer, mit 3.12.3 verifiziert.
- PrusaSlicer als ausführbare Datei auf dem Hauptrechner.
- Für Hardwarebetrieb: erreichbarer Prusa-Drucker mit PrusaLink, Niryo Ned2, Raspberry Pi 5, Mitutoyo SJ-220 und V4L2-Kamera.
- Auf dem Pi zusätzlich `ffmpeg` und `v4l2-ctl`.

## Schnellstart ohne Hardware

Alle folgenden Befehle werden im Repository-Root ausgeführt, sofern nicht anders angegeben.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r 3d-automation/requirements.txt
python -m pip install numpy scipy scikit-learn
cd 3d-automation
export PYTHONPATH="$PWD/src"
python -m main --help
python -m optimizer.config config/optimizer_config.example.json --check-input-files
python -m optimizer.warm_start config/optimizer_config.example.json
```

Warum zusätzliche Pakete installiert werden müssen und welche Python-Version tatsächlich ableitbar ist, steht in [Installation](3d-automation/docs/03_installation.md).

Eine neue Simulation benötigt ein neues, noch nicht vorhandenes `paths.output_directory` in der Optimierer-JSON:

```bash
python -m optimizer.framework_runner \
  config/optimizer_config.simulation.json \
  --simulate \
  --new \
  --max-runs 6
```

Existiert das konfigurierte Ausgabeverzeichnis bereits, ist statt `--new` ein passender `--resume`-Aufruf erforderlich. Details: [Bedienung](3d-automation/docs/06_bedienung.md).

## Start mit Hardware - Kurzfassung

1. Auf dem Raspberry Pi die QS-/Kamera-API starten und `/health` sowie `/camera/health` prüfen.
2. Auf dem Hauptrechner `config/end_to_end.env.example` nach `config/end_to_end.env` kopieren, Zugangsdaten eintragen und die Datei in die Shell laden.
3. Zuerst `python -m main --mode preflight` ausführen.
4. Mechanik getrennt mit einem vorhandenen Bauteil prüfen.
5. Erst danach einen Einzelzyklus oder den bewachten Optimierer-Hardwarelauf starten.

```bash
cd 3d-automation
set -a
source config/end_to_end.env
set +a
export PYTHONPATH="$PWD/src"
python -m main --mode preflight
```

Der Optimierer besitzt zusätzliche Sicherheitsgates. Ein neues Experiment wird zunächst nur angelegt und geprüft:

```bash
cp config/optimizer_config.example.json \
  config/optimizer_config.hardware.local.json
# Danach Experimentname, sichere Grenzen und einen neuen Ausgabepfad eintragen.
python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.local.json \
  --new \
  --preflight-only \
  --failure-result penalty
```

Die vorhandene `optimizer_config.example.json` ist ein Strukturbeispiel und keine automatische Freigabe für reale Hardware. Vor dem Aufruf muss die lokale Kopie kontrolliert editiert werden.

## Dokumentation

| Kapitel | Inhalt |
| --- | --- |
| [01 Systemüberblick](3d-automation/docs/01_systemueberblick.md) | Ziel, Geräteverteilung, Daten- und Kontrollfluss |
| [02 Repository und Architektur](3d-automation/docs/02_repository_und_architektur.md) | Verzeichnisse, Module, Klassen, Zustände und Schnittstellen |
| [03 Installation](3d-automation/docs/03_installation.md) | Einrichtung von Hauptrechner und Raspberry Pi |
| [04 Konfiguration](3d-automation/docs/04_konfiguration.md) | Umgebungsvariablen, CLI, JSON und Slicer-Profil |
| [05 Hardware-Setup](3d-automation/docs/05_hardware_setup.md) | Drucker, Roboter, SJ-220, Raspberry Pi, Kamera und QS |
| [06 Bedienung](3d-automation/docs/06_bedienung.md) | Befehle und vollständige Betriebschecklisten |
| [07 Versuche und Daten](3d-automation/docs/07_versuche_und_daten.md) | Pläne, IDs, CSV/JSON, Bilder, Logs und Resume |
| [08 Optimierer](3d-automation/docs/08_optimierer.md) | Warmstart, Strategien, Bayesian Optimization und Zustände |
| [09 Fehlerbehandlung](3d-automation/docs/09_fehlerbehandlung.md) | Diagnose, Retry, Penalty und manuelle Stopps |
| [10 Tests und Entwicklung](3d-automation/docs/10_tests_und_entwicklung.md) | Tests, Simulation, Erweiterung und Debugging |
| [11 API-Referenz](3d-automation/docs/11_api_referenz.md) | QS-/Kamera-Routen und Clientverhalten |
| [12 Übergabe und offene Punkte](3d-automation/docs/12_uebergabe_und_offene_punkte.md) | Reifegrad, Risiken, Schulden und nächste Schritte |

## Verbindliche Quellen

Bei Widersprüchen gilt in dieser Reihenfolge:

1. aktueller Produktionscode und zugehörige Tests,
2. aktuelle Konfigurationsdateien,
3. diese Übergabedokumentation,
4. ältere Meilenstein-Dokumente wie `OPTIMIZER_FRAMEWORK_STEP_*.md`.

Die älteren Schrittdateien bleiben als Entwicklungshistorie erhalten. Mehrere Aussagen darin sind inzwischen überholt; sie sind nicht die aktuelle Bedienungsanleitung.
