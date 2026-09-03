# 03 – Installation

## Unterstützte Umgebung

Der Produktionspfad ist Linux-orientiert: PrusaSlicer ist standardmäßig als AppImage eingetragen, die Kamera verwendet `/dev/video*`, das Messgerät `/dev/ttyUSB0` und die Prozesssperre `/tmp/sj220_service.lock`. `scripts/install_system.sh` richtet die aktuelle Software für den Hauptrechner, den Raspberry Pi oder beide Rollen ein. Das alte `scripts/setup.bat` legt dagegen nur zwei Verzeichnisse an und ist kein vollständiger Installer.

Eine Python-Version ist im Repository nicht formal festgelegt. Aus der Syntax folgt Python **3.10 oder neuer**; Analyse und Tests dieser Übergabe liefen mit Python **3.12.3**. Für reproduzierbaren Betrieb sollte das Projekt künftig eine Version in `pyproject.toml` oder einer vergleichbaren Datei festschreiben.

## 1. Repository beziehen

Die Remote-URL ist in der lokalen Git-Konfiguration als `origin` hinterlegt.

**Arbeitsverzeichnis: Elternverzeichnis des künftigen Projekts**

```bash
git clone https://github.com/ali2644/bachelor-3d-loop.git bachelor-3d-loop
cd bachelor-3d-loop
git switch feature/optimizer-framework-integration
```

Der bei der Dokumentation analysierte Stand war Commit `29f11b9`. Vor einer Übergabe ist zu prüfen, ob Branch und Commit im Remote vorhanden und weiterhin freigegeben sind; ein zukünftiger Checkout darf einen neueren, freigegebenen Stand verwenden.

## 2. Empfohlene Installation mit dem Skript

Das Installationsskript erkennt seinen Projektpfad selbst und kann deshalb aus jedem Arbeitsverzeichnis aufgerufen werden. Es unterstützt drei Rollen:

| Rolle | Installierter Softwareumfang |
| --- | --- |
| `main` | End-to-End-Anwendung, Hardwareclients, Optimierer, NumPy, SciPy und scikit-learn |
| `pi` | FastAPI, Uvicorn und PySerial für QS und Kamera; keine unnötige Roboter- oder Optimiererbibliothek |
| `all` | beide Umfänge auf demselben Linux-System |

### Hauptrechner

**Arbeitsverzeichnis: `bachelor-3d-loop/`**

```bash
chmod +x 3d-automation/scripts/install_system.sh
./3d-automation/scripts/install_system.sh \
  --role main \
  --install-system-packages
```

Der Schalter `--install-system-packages` nutzt `apt` und ist für Debian, Ubuntu und Raspberry Pi OS gedacht. Auf einem bereits vorbereiteten oder nicht apt-basierten System wird er weggelassen. Standardmäßig entsteht die virtuelle Umgebung als `.venv` im Repository-Root.

### Raspberry Pi

**Arbeitsverzeichnis: `bachelor-3d-loop/` auf dem Pi**

```bash
chmod +x 3d-automation/scripts/install_system.sh
./3d-automation/scripts/install_system.sh \
  --role pi \
  --install-system-packages
```

Für einen automatischen API-Start kann das Skript zusätzlich eine konkrete systemd-Unit erzeugen, installieren und starten:

```bash
./3d-automation/scripts/install_system.sh \
  --role pi \
  --install-system-packages \
  --install-service \
  --service-user pi
```

`--install-service` ist absichtlich explizit: Nur dieser Schalter startet einen Prozess. Der Dienst führt Uvicorn aus, löst beim Start aber keine Messung und keine Kameraaufnahme aus. Die Unit verwendet absolute Pfade, `config/qs_station.env`, `Restart=on-failure` und `NoNewPrivileges=true`. Der angegebene Dienstbenutzer muss die virtuelle Umgebung und den Quellcode lesen sowie `data/camera_images` beschreiben können; der Installer prüft das vor der Unit-Installation. Am einfachsten wird das Skript als genau dieser normale Benutzer ausgeführt und nur seine Systemschritte werden intern über `sudo` erhöht.

### Wichtige Eigenschaften und Optionen

- Vorhandene `config/end_to_end.env` und `config/qs_station.env` werden nie überschrieben.
- Lokale Env-Dateien werden mit Modus `0600` angelegt und von Git ignoriert.
- Die Installation führt keinen Druck, keine Roboterbewegung, keine Messung und keine Kameraaufnahme aus.
- Mit `--venv <Pfad>` und `--python <Interpreter>` lassen sich Umgebung und Python wählen.
- `--check-only` prüft eine bestehende Installation ohne Installationsänderung.
- `--prusa-slicer <Pfad>` prüft eine abweichende PrusaSlicer-Datei, lädt sie aber nicht herunter.
- `--help` zeigt alle Optionen und Beispiele.

Beispiel für eine reine Prüfung:

```bash
./3d-automation/scripts/install_system.sh --role main --check-only
./3d-automation/scripts/install_system.sh --role pi --check-only
```

Warnungen wegen nicht angeschlossener `/dev/video0`- oder `/dev/ttyUSB0`-Geräte sowie eines fehlenden PrusaSlicers beenden die Softwareprüfung nicht. Fehlende Python-Module oder inkonsistente Pakete führen dagegen zu einem Fehlercode.

## 3. Manuelle Alternative: Hauptrechner einrichten

### Virtuelle Umgebung und Python-Pakete

**Arbeitsverzeichnis: `bachelor-3d-loop/`**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r 3d-automation/requirements.txt
python -m pip install numpy scipy scikit-learn
```

`3d-automation/requirements.txt` enthält FastAPI, Uvicorn, PyNiryo, PySerial und Requests. Die vom Optimierer tatsächlich importierten Pakete NumPy, SciPy und scikit-learn fehlen dort; der zusätzliche Installationsbefehl ist deshalb derzeit erforderlich. Die Root-Datei `requirements.txt` ist eine ältere, für die aktuelle Anwendung unvollständige HTTP-Abhängigkeitsliste. `PrusaLinkPy` steht zwar dort, der aktuelle `PrusaLinkService` verwendet jedoch direkt `requests`.

### Python-Module erreichbar machen

**Arbeitsverzeichnis: `bachelor-3d-loop/3d-automation/`**

```bash
source ../.venv/bin/activate
export PYTHONPATH="$PWD/src"
python -m main --help
```

Das Projekt ist nicht als installierbares Python-Paket konfiguriert. `PYTHONPATH` muss daher in jeder neuen Shell gesetzt werden. Ein falsches Arbeitsverzeichnis führt typischerweise zu `No module named main` oder zu falsch aufgelösten relativen Kamera-Pfaden.

## 4. PrusaSlicer installieren

Der Code erwartet standardmäßig:

```text
~/apps/prusaslicer/PrusaSlicer-2.9.1-x86_64.AppImage
```

Eine andere ausführbare Datei wird über `PRUSASLICER_PATH` konfiguriert. Installation und Downloadquelle sind im Repository nicht automatisiert.

**Arbeitsverzeichnis: beliebig; Beispielpfad aus dem Code**

```bash
mkdir -p "$HOME/apps/prusaslicer"
chmod +x "$HOME/apps/prusaslicer/PrusaSlicer-2.9.1-x86_64.AppImage"
"$HOME/apps/prusaslicer/PrusaSlicer-2.9.1-x86_64.AppImage" --version
```

Der Download der Datei muss vorher aus einer vertrauenswürdigen, projektspezifisch freigegebenen Quelle erfolgen. Der Code dokumentiert keinen Download-Link und keine Prüfsumme.

Der spätere Slicer-Aufruf lautet sinngemäß:

```bash
"$PRUSASLICER_PATH" -g --load <PROFIL.ini> --center 90,45 <MODELL.stl> --output <AUSGABE.gcode>
```

## 5. Hauptrechner konfigurieren

**Arbeitsverzeichnis: `bachelor-3d-loop/3d-automation/`**

```bash
cp config/end_to_end.env.example config/end_to_end.env
chmod 600 config/end_to_end.env
```

Danach nur `config/end_to_end.env` lokal bearbeiten. Die Datei ist durch `.gitignore` ausgeschlossen und darf wegen des PrusaLink-Schlüssels nicht committet werden.

```bash
set -a
source config/end_to_end.env
set +a
```

Alle Felder erklärt [04 – Konfiguration](04_konfiguration.md).

## 6. Manuelle Alternative: Raspberry Pi 5 einrichten

Die folgende Paketinstallation ist eine Debian-/Raspberry-Pi-OS-Anleitung, abgeleitet aus den verwendeten Befehlen. Eine Distribution oder ein fertiges Deployment ist im Repository nicht festgeschrieben.

**Arbeitsverzeichnis: beliebig auf dem Raspberry Pi**

```bash
sudo apt update
sudo apt install python3-venv python3-pip ffmpeg v4l-utils
```

Den Projektstand auf den Pi übertragen oder dort klonen. Danach:

**Arbeitsverzeichnis: `bachelor-3d-loop/3d-automation/` auf dem Pi**

```bash
python3 -m venv .venv-pi
source .venv-pi/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
export PYTHONPATH="$PWD/src"
```

Für QS und Kamera sind aus der Datei mindestens `fastapi`, `uvicorn`, `pyserial` sowie `ffmpeg` und `v4l2-ctl` relevant. PyNiryo wird nur auf einem Rechner benötigt, der den Roboterclient ausführt.

### USB- und Kamera-Geräte prüfen

**Arbeitsverzeichnis: beliebig auf dem Pi**

```bash
ls -l /dev/ttyUSB0
ls -l /dev/video0
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
```

Wenn der Benutzer nicht auf die serielle Schnittstelle zugreifen darf, ist auf Debian-artigen Systemen häufig die Gruppe `dialout` relevant:

```bash
sudo usermod -aG dialout "$USER"
```

Danach ab- und wieder anmelden. Die tatsächlich benötigte Gruppe ist mit `ls -l /dev/ttyUSB0` zu prüfen; sie ist nicht im Repository festgelegt.

### API im Vordergrund starten

**Arbeitsverzeichnis: `bachelor-3d-loop/3d-automation/` auf dem Pi**

```bash
source .venv-pi/bin/activate
export PYTHONPATH="$PWD/src"
export CAMERA_DEVICE_PATH=/dev/video0
export CAMERA_OUTPUT_DIR="$PWD/data/camera_images"
export CAMERA_WIDTH=1920
export CAMERA_HEIGHT=1080
export CAMERA_PIXEL_FORMAT=mjpeg
python -m uvicorn qs.api:app --host 0.0.0.0 --port 8000
```

Alternativ zum Vordergrundstart erzeugt `scripts/install_system.sh --role pi --install-service --service-user <Benutzer>` eine installationsspezifische `/etc/systemd/system/qs-station.service`. Es liegt bewusst keine Unit mit fest codierten Projektpfaden im Repository; der Installer setzt die absoluten Pfade des jeweiligen Zielsystems ein.

## 7. Installation validieren

### Hauptrechner, ohne Hardwarebewegung

**Arbeitsverzeichnis: `bachelor-3d-loop/3d-automation/`**

```bash
source ../.venv/bin/activate
export PYTHONPATH="$PWD/src"
python -m compileall -q src tests
python -m pip check
python -m optimizer.config config/optimizer_config.example.json --check-input-files
python -m optimizer.warm_start config/optimizer_config.example.json
```

`compileall` bleibt ohne Ausgabe, wenn alle Dateien syntaktisch kompiliert wurden. `pip check` soll `No broken requirements found.` melden. Die Konfigurationsprüfung gibt eine normalisierte JSON-Struktur aus; der Warmstart zeigt die geplanten Punkte, ohne Zustand oder Hardware zu verändern.

### Netzwerk vom Hauptrechner

Ersetzen Sie nur den Pi-Platzhalter; der Drucker-Standard stammt aus `main.py`.

```bash
curl --fail --show-error http://<RASPBERRY-PI-IP>:8000/health
curl --fail --show-error http://<RASPBERRY-PI-IP>:8000/camera/health
curl --fail --show-error http://10.8.170.57/api/printer
```

Der letzte Aufruf kann abhängig von PrusaLink eine Authentifizierungsantwort liefern. Der echte Client sendet `X-Api-Key`; Schlüssel gehören nicht in Shell-Historie oder Dokumentation.

### Tests

```bash
python -m unittest discover -s tests -v
```

Der aktuelle bekannte Stand ist in [10 – Tests und Entwicklung](10_tests_und_entwicklung.md) dokumentiert. Dieser Befehl bewegt nach aktuellem Testaufbau keine Hardware; die Clients werden gemockt.

Weiter: [04 – Konfiguration](04_konfiguration.md)
