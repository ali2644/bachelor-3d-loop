#!/usr/bin/env bash

# Installiert die Softwarebasis fuer Automated R.E.P.P.R.I.N.T.
# Das Skript fuehrt keine Druck-, Roboter-, Kamera- oder Messaktion aus.

set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
APP_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
REPOSITORY_DIR="$(cd -- "$APP_DIR/.." && pwd -P)"

ROLE=""
PYTHON_BIN="python3"
VENV_DIR="$REPOSITORY_DIR/.venv"
INSTALL_SYSTEM_PACKAGES=false
INSTALL_SERVICE=false
CHECK_ONLY=false
SERVICE_USER=""
PRUSASLICER_PATH_OPTION=""

info() {
    printf '[INFO] %s\n' "$*"
}

warn() {
    printf '[WARNUNG] %s\n' "$*" >&2
}

die() {
    printf '[FEHLER] %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Verwendung:
  install_system.sh --role main|pi|all [Optionen]

Rollen:
  main  Hauptrechner: Anwendung, Hardwareclients und Optimierer
  pi    Raspberry Pi: QS-/Kamera-API
  all   Beide Rollen auf demselben Rechner

Optionen:
  --python PFAD                  Python-Interpreter (Standard: python3)
  --venv PFAD                    Virtuelle Umgebung (Standard: <Repo>/.venv)
  --install-system-packages      Debian-/Ubuntu-/Raspberry-Pi-OS-Pakete
                                 mit apt installieren
  --install-service              Auf dem Pi qs-station.service erzeugen,
                                 aktivieren und starten (benoetigt pi/all)
  --service-user BENUTZER        Benutzer fuer den systemd-Dienst
  --prusa-slicer PFAD            PrusaSlicer-Datei fuer die Pruefung
  --check-only                   Bestehende Installation nur pruefen;
                                 keine Dateien oder Pakete veraendern
  -h, --help                     Diese Hilfe anzeigen

Beispiele:
  ./scripts/install_system.sh --role main --install-system-packages
  ./scripts/install_system.sh --role pi --install-system-packages \
      --install-service --service-user pi
  ./scripts/install_system.sh --role main --check-only

Sicherheit:
  Das Skript bewegt keine Hardware und startet keinen Druck oder Messvorgang.
  Nur --install-service startet die QS-/Kamera-API als Hintergrunddienst.
EOF
}

while (($# > 0)); do
    case "$1" in
        --role)
            (($# >= 2)) || die "--role benoetigt einen Wert."
            ROLE="$2"
            shift 2
            ;;
        --python)
            (($# >= 2)) || die "--python benoetigt einen Pfad."
            PYTHON_BIN="$2"
            shift 2
            ;;
        --venv)
            (($# >= 2)) || die "--venv benoetigt einen Pfad."
            VENV_DIR="$2"
            shift 2
            ;;
        --install-system-packages)
            INSTALL_SYSTEM_PACKAGES=true
            shift
            ;;
        --install-service)
            INSTALL_SERVICE=true
            shift
            ;;
        --service-user)
            (($# >= 2)) || die "--service-user benoetigt einen Namen."
            SERVICE_USER="$2"
            shift 2
            ;;
        --prusa-slicer)
            (($# >= 2)) || die "--prusa-slicer benoetigt einen Pfad."
            PRUSASLICER_PATH_OPTION="$2"
            shift 2
            ;;
        --check-only)
            CHECK_ONLY=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unbekannte Option: $1 (Hilfe: --help)"
            ;;
    esac
done

case "$ROLE" in
    main|pi|all) ;;
    "") die "Eine Rolle ist erforderlich: --role main|pi|all" ;;
    *) die "Ungueltige Rolle '$ROLE'; erlaubt sind main, pi und all." ;;
esac

if $CHECK_ONLY && { $INSTALL_SYSTEM_PACKAGES || $INSTALL_SERVICE; }; then
    die "--check-only kann nicht mit Installationsoptionen kombiniert werden."
fi

if $INSTALL_SERVICE && [[ "$ROLE" == "main" ]]; then
    die "--install-service erfordert --role pi oder --role all."
fi

if [[ -n "$SERVICE_USER" ]] && ! $INSTALL_SERVICE; then
    die "--service-user ist nur zusammen mit --install-service sinnvoll."
fi

if [[ "$VENV_DIR" != /* ]]; then
    VENV_DIR="$(pwd -P)/$VENV_DIR"
fi

run_as_root() {
    if ((EUID == 0)); then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo -- "$@"
    else
        die "Dieser Schritt benoetigt root-Rechte oder sudo: $*"
    fi
}

install_os_packages() {
    command -v apt-get >/dev/null 2>&1 || die \
        "--install-system-packages wird nur auf apt-basierten Systemen unterstuetzt."

    local packages=(git python3 python3-pip python3-venv curl)
    if [[ "$ROLE" == "pi" || "$ROLE" == "all" ]]; then
        packages+=(ffmpeg v4l-utils)
    fi

    info "Aktualisiere apt-Paketlisten."
    run_as_root apt-get update
    info "Installiere Betriebssystempakete fuer Rolle '$ROLE'."
    run_as_root apt-get install -y --no-install-recommends "${packages[@]}"
}

validate_python() {
    command -v "$PYTHON_BIN" >/dev/null 2>&1 || die \
        "Python-Interpreter nicht gefunden: $PYTHON_BIN"
    "$PYTHON_BIN" -c \
        'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
        || die "Python 3.10 oder neuer ist erforderlich."
}

create_virtual_environment() {
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then
        info "Erzeuge virtuelle Umgebung: $VENV_DIR"
        "$PYTHON_BIN" -m venv "$VENV_DIR"
    else
        info "Verwende vorhandene virtuelle Umgebung: $VENV_DIR"
    fi

    local venv_python="$VENV_DIR/bin/python"
    "$venv_python" -m pip install --upgrade pip
    if [[ "$ROLE" == "pi" ]]; then
        "$venv_python" -m pip install \
            'fastapi>=0.115,<1' \
            'pyserial>=3.5,<4' \
            'uvicorn>=0.34,<1'
    else
        "$venv_python" -m pip install -r "$APP_DIR/requirements.txt"
        "$venv_python" -m pip install numpy scipy scikit-learn
    fi
}

install_local_configuration() {
    local target

    if [[ "$ROLE" == "main" || "$ROLE" == "all" ]]; then
        target="$APP_DIR/config/end_to_end.env"
        if [[ -e "$target" ]]; then
            info "Lokale Hauptrechner-Konfiguration bleibt unveraendert: $target"
        else
            install -m 600 "$APP_DIR/config/end_to_end.env.example" "$target"
            info "Konfigurationsvorlage angelegt: $target"
        fi
        mkdir -p \
            "$APP_DIR/data/results" \
            "$APP_DIR/data/generated_profiles" \
            "$APP_DIR/data/gcode" \
            "$APP_DIR/data/optimization_runs"
    fi

    if [[ "$ROLE" == "pi" || "$ROLE" == "all" ]]; then
        target="$APP_DIR/config/qs_station.env"
        if [[ -e "$target" ]]; then
            info "Lokale Pi-Konfiguration bleibt unveraendert: $target"
        else
            install -m 600 "$APP_DIR/config/qs_station.env.example" "$target"
            info "Konfigurationsvorlage angelegt: $target"
        fi
        mkdir -p "$APP_DIR/data/camera_images"
    fi
}

check_executable() {
    local command_name="$1"
    local package_hint="$2"
    if command -v "$command_name" >/dev/null 2>&1; then
        info "Gefunden: $command_name"
    else
        warn "$command_name fehlt (Paket: $package_hint)."
    fi
}

check_device() {
    local path="$1"
    if [[ -e "$path" ]]; then
        info "Geraet vorhanden: $path"
    else
        warn "Geraet derzeit nicht vorhanden: $path"
    fi
}

check_prusa_slicer() {
    local slicer_path="$PRUSASLICER_PATH_OPTION"
    if [[ -z "$slicer_path" ]]; then
        slicer_path="${PRUSASLICER_PATH:-${HOME:-}/apps/prusaslicer/PrusaSlicer-2.9.1-x86_64.AppImage}"
    fi
    if [[ -x "$slicer_path" ]]; then
        info "PrusaSlicer ist ausfuehrbar: $slicer_path"
    else
        warn "PrusaSlicer fehlt oder ist nicht ausfuehrbar: $slicer_path"
        warn "Downloadquelle und Pruefsumme muessen projektspezifisch freigegeben werden."
    fi
}

validate_installation() {
    local venv_python="$VENV_DIR/bin/python"
    [[ -x "$venv_python" ]] || die \
        "Virtuelle Umgebung fehlt oder ist unvollstaendig: $VENV_DIR"
    "$venv_python" -c \
        'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
        || die "Die virtuelle Umgebung benoetigt Python 3.10 oder neuer."

    info "Pruefe Python-Paketkonsistenz."
    "$venv_python" -m pip check

    if [[ "$ROLE" == "main" || "$ROLE" == "all" ]]; then
        info "Pruefe Hauptanwendung und Optimierer ohne Hardwarezugriff."
        (
            cd "$APP_DIR"
            PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$APP_DIR/src" "$venv_python" -c \
                'import main, numpy, scipy, sklearn; import optimizer.config, optimizer.warm_start'
            PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$APP_DIR/src" \
                "$venv_python" -m main --help >/dev/null
            PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$APP_DIR/src" \
                "$venv_python" -m optimizer.config \
                config/optimizer_config.example.json --check-input-files >/dev/null
            PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$APP_DIR/src" \
                "$venv_python" -m optimizer.warm_start \
                config/optimizer_config.example.json >/dev/null
        )
        check_prusa_slicer
    fi

    if [[ "$ROLE" == "pi" || "$ROLE" == "all" ]]; then
        info "Pruefe QS-/Kamera-API ohne Messung oder Aufnahme."
        (
            cd "$APP_DIR"
            PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$APP_DIR/src" \
                "$venv_python" -c \
                'import fastapi, serial, uvicorn; from qs.api import app; assert app is not None'
        )
        check_executable ffmpeg ffmpeg
        check_executable v4l2-ctl v4l-utils
        check_device /dev/video0
        check_device /dev/ttyUSB0
    fi
}

install_qs_service() {
    [[ "$APP_DIR" != *[[:space:]]* ]] || die \
        "Der Projektpfad darf fuer die systemd-Installation keine Leerzeichen enthalten."
    command -v systemctl >/dev/null 2>&1 || die \
        "systemctl wurde nicht gefunden; der Dienst kann nicht installiert werden."

    local service_user="$SERVICE_USER"
    if [[ -z "$service_user" ]]; then
        service_user="${SUDO_USER:-$(id -un)}"
    fi
    if [[ "$service_user" == "root" && -z "$SERVICE_USER" ]]; then
        die "Bei direktem root-Aufruf muss --service-user explizit gesetzt werden."
    fi
    id "$service_user" >/dev/null 2>&1 || die \
        "Der Dienstbenutzer existiert nicht: $service_user"

    if [[ "$service_user" == "$(id -un)" ]]; then
        [[ -x "$VENV_DIR/bin/python" && -r "$APP_DIR/src/qs/api.py" ]] || die \
            "Der Dienstbenutzer kann Python oder die API-Quelle nicht lesen."
        [[ -w "$APP_DIR/data/camera_images" ]] || die \
            "Der Dienstbenutzer kann data/camera_images nicht beschreiben."
    elif ((EUID == 0)); then
        command -v runuser >/dev/null 2>&1 || die \
            "runuser fehlt; Zugriffsrechte des Dienstbenutzers sind nicht pruefbar."
        runuser -u "$service_user" -- test -x "$VENV_DIR/bin/python" || die \
            "Der Dienstbenutzer kann die virtuelle Umgebung nicht ausfuehren."
        runuser -u "$service_user" -- test -r "$APP_DIR/src/qs/api.py" || die \
            "Der Dienstbenutzer kann die API-Quelle nicht lesen."
        runuser -u "$service_user" -- test -w "$APP_DIR/data/camera_images" || die \
            "Der Dienstbenutzer kann data/camera_images nicht beschreiben."
    else
        command -v sudo >/dev/null 2>&1 || die \
            "sudo fehlt; Zugriffsrechte des Dienstbenutzers sind nicht pruefbar."
        sudo --user="$service_user" -- test -x "$VENV_DIR/bin/python" || die \
            "Der Dienstbenutzer kann die virtuelle Umgebung nicht ausfuehren."
        sudo --user="$service_user" -- test -r "$APP_DIR/src/qs/api.py" || die \
            "Der Dienstbenutzer kann die API-Quelle nicht lesen."
        sudo --user="$service_user" -- test -w "$APP_DIR/data/camera_images" || die \
            "Der Dienstbenutzer kann data/camera_images nicht beschreiben."
    fi

    local service_file
    service_file="$(mktemp)"
    trap "rm -f -- '$service_file'" EXIT

    cat >"$service_file" <<EOF
[Unit]
Description=Automated R.E.P.P.R.I.N.T. QS Station API
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$service_user
WorkingDirectory=$APP_DIR
Environment=PYTHONPATH=$APP_DIR/src
EnvironmentFile=-$APP_DIR/config/qs_station.env
ExecStart=$VENV_DIR/bin/python -m uvicorn qs.api:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

    info "Installiere und starte qs-station.service."
    run_as_root install -m 644 "$service_file" /etc/systemd/system/qs-station.service
    run_as_root systemctl daemon-reload
    run_as_root systemctl enable --now qs-station.service
    run_as_root systemctl --no-pager --full status qs-station.service || {
        warn "Der Dienst ist nicht fehlerfrei gestartet. Diagnose:"
        warn "  sudo journalctl -u qs-station.service -n 100 --no-pager"
        return 1
    }
    rm -f -- "$service_file"
    trap - EXIT
}

info "Projekt: $REPOSITORY_DIR"
info "Rolle: $ROLE"
info "Virtuelle Umgebung: $VENV_DIR"

if $CHECK_ONLY; then
    validate_installation
    info "Pruefung abgeschlossen. Es wurden keine Installationsaenderungen vorgenommen."
    exit 0
fi

if $INSTALL_SYSTEM_PACKAGES; then
    install_os_packages
fi

validate_python
create_virtual_environment
install_local_configuration
validate_installation

if $INSTALL_SERVICE; then
    install_qs_service
fi

info "Installation fuer Rolle '$ROLE' abgeschlossen."
if [[ "$ROLE" == "main" || "$ROLE" == "all" ]]; then
    info "Naechster Schritt: config/end_to_end.env bearbeiten und danach den Preflight ausfuehren."
fi
if [[ "$ROLE" == "pi" || "$ROLE" == "all" ]]; then
    info "Naechster Schritt: config/qs_station.env und die Geraeterechte pruefen."
fi
