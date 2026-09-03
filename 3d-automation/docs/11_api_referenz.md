# 11 – API-Referenz

## Server und Basis-URL

Die FastAPI-Anwendung steht in `src/qs/api.py` und kombiniert QS und Kamera. Start auf dem Raspberry Pi aus `bachelor-3d-loop/3d-automation/`:

```bash
source .venv-pi/bin/activate
export PYTHONPATH="$PWD/src"
python -m uvicorn qs.api:app --host 0.0.0.0 --port 8000
```

Die Basis-URL ist aus Sicht des Hauptrechners der Wert von `QS_BASE_URL`, zum Beispiel `http://192.0.2.10:8000`. Standardmäßig verwendet der Kamera-Client dieselbe URL; `CAMERA_BASE_URL` kann sie überschreiben.

Im Projekt sind weder API-Authentifizierung noch TLS implementiert. Die API darf nur in einem kontrollierten Netz erreichbar sein. CORS-Konfiguration ist ebenfalls nicht vorhanden.

FastAPI stellt zusätzlich die generierten Oberflächen `/docs`, `/redoc` und das Schema `/openapi.json` bereit.

## Routenübersicht

| Methode | Route | Request | Erfolg | Wichtige Fehler |
| --- | --- | --- | --- | --- |
| `GET` | `/health` | – | 200 JSON | keine Geräteprüfung |
| `GET` | `/camera/health` | – | 200 JSON | 503 Abhängigkeit/Gerät fehlt |
| `POST` | `/camera/captures/{cycle_id}` | Path-Parameter | 200 JSON | 422 ID, 502 Aufnahme |
| `GET` | `/camera/captures/{cycle_id}` | Path-Parameter | 200 `image/jpeg` | 404 fehlt, 422 ID |
| `POST` | `/measurements` | kein Body | 200 JSON | 409, 422, 500, 502, 503, 504 |

`cycle_id` muss genau 32 Zeichen lang sein und dem regulären Ausdruck `^[0-9a-f]{32}$` entsprechen. Erwartet ist `uuid.uuid4().hex`, also Kleinbuchstaben und Ziffern ohne Bindestriche.

## `GET /health`

Prüft nur, ob der Webprozess antwortet. Serielle Schnittstelle, SJ-220 und Kamera werden nicht geprüft.

```bash
curl --fail --show-error "$QS_BASE_URL/health"
```

Antwort:

```json
{
  "status": "ok",
  "service": "qs-station"
}
```

Der `QualityStationClient.health()` hat 5 Sekunden Timeout, fordert erfolgreichen HTTP-Status und exakt `status: "ok"`.

## `GET /camera/health`

Prüft, ob `ffmpeg` und `v4l2-ctl` über `PATH` auffindbar sind und ob `CAMERA_DEVICE_PATH` existiert.

```bash
curl --fail --show-error "$QS_BASE_URL/camera/health"
```

Erfolg:

```json
{
  "status": "ok",
  "service": "camera",
  "device_path": "/dev/video0"
}
```

Fehler 503, Beispiel:

```json
{
  "detail": {
    "type": "missing_dependency",
    "message": "Missing camera command(s): ffmpeg"
  }
}
```

Alternativ ist `type` gleich `camera_unavailable`. Der Endpoint öffnet die Kamera nicht und testet keine Auflösung oder Controls. Der Kamera-Client verwendet 5 Sekunden Timeout.

## `POST /camera/captures/{cycle_id}`

Startet synchron genau eine Aufnahme. Request-Body und Query-Parameter gibt es nicht. Die API setzt die in [04 – Konfiguration](04_konfiguration.md) beschriebenen Controls, ruft `ffmpeg` auf und erwartet danach eine nicht leere JPEG-Datei.

```bash
CAMERA_CYCLE_ID="$(python -c 'import uuid; print(uuid.uuid4().hex)')"
curl --fail --show-error \
  -X POST \
  "$QS_BASE_URL/camera/captures/$CAMERA_CYCLE_ID"
```

Erfolg:

```json
{
  "status": "completed",
  "cycle_id": "0123456789abcdef0123456789abcdef",
  "filename": "0123456789abcdef0123456789abcdef.jpg"
}
```

| Status | `detail.type` | Bedeutung |
| --- | --- | --- |
| 422 | `invalid_cycle_id` | ID hat falsches Format |
| 502 | `camera_capture_error` | V4L2-/ffmpeg-/Dateifehler oder leere Ausgabe |

Der `CameraClient` verwendet 30 Sekunden Timeout, validiert Status, identische Cycle-ID und exakt den Dateinamen `<cycle_id>.jpg`. Anschließend lädt er die Datei automatisch herunter.

## `GET /camera/captures/{cycle_id}`

Liefert ein vorhandenes Bild als `image/jpeg` mit Dateinamen im `Content-Disposition`-Header.

```bash
curl --fail --show-error \
  "$QS_BASE_URL/camera/captures/$CAMERA_CYCLE_ID" \
  --output "$CAMERA_CYCLE_ID.jpg"
```

| Status | `detail.type` | Bedeutung |
| --- | --- | --- |
| 404 | `camera_capture_not_found` | keine nicht leere Datei für die ID |
| 422 | `invalid_cycle_id` | ID hat falsches Format |

Der Client-Download hat 30 Sekunden Timeout und schreibt zunächst `<name>.part`, dann wird atomar auf den endgültigen Dateinamen umbenannt. Eine leere HTTP-Nutzlast wird abgelehnt.

## `POST /measurements`

> **Physische Bewegung:** Dieser Aufruf öffnet `/dev/ttyUSB0` und startet eine SJ-220-Messung. Nur mit korrekt positioniertem Werkstück ausführen.

Es gibt keinen Request-Body. Die API fordert `Ra` und `Rz` an.

```bash
curl --fail --show-error \
  -X POST \
  "$QS_BASE_URL/measurements"
```

Erfolg, Zahlen nur Beispiel:

```json
{
  "status": "completed",
  "results": {
    "Ra": 4.152,
    "Rz": 22.5
  },
  "unit": "um",
  "duration_seconds": 12.34
}
```

`unit` ist die gemeinsame Einheit aller Results oder `null`, falls die Geräteantwort gemischte Einheiten enthält. Der HTTP-Client verwendet 90 Sekunden Timeout, akzeptiert nur `status: "completed"` und endliche numerische Werte für beide Felder. Er gibt intern `{"Ra": ..., "Rz": ...}` zurück.

### Fehlerantworten

FastAPI verpackt Details wie folgt:

```json
{
  "detail": {
    "type": "device_error",
    "code": "007",
    "message": "SJ-220 error 007: ..."
  }
}
```

| HTTP | `detail.type` | Exception im Server |
| --- | --- | --- |
| 409 | `port_in_use` | `SJ220PortInUseError` |
| 409 | `invalid_state` | `SJ220StateError` |
| 422 | `device_error` | `SJ220DeviceError`, zusätzlich `code` |
| 500 | `sj220_error` | sonstiger bekannter `SJ220Error` |
| 502 | `result_error` | `SJ220ResultError` |
| 502 | `protocol_error` | `SJ220ProtocolError` |
| 503 | `connection_error` | `SJ220ConnectionError` |
| 504 | `timeout` | `SJ220TimeoutError` |

Der Client selbst sendet einen Mess-POST nur einmal. `PrintOrchestrator` fängt jedoch jede Exception ab und ruft `measure()` ein zweites Mal auf. Das ist die aktuell wirksame Systemlogik; Details und Risiken stehen in [09 – Fehlerbehandlung](09_fehlerbehandlung.md).

## Zusammenspiel im Orchestrator

1. Im Preflight ruft der Orchestrator `/camera/health`, `/api/printer`, `/health` und den Roboter-Verbindungscheck auf.
2. Nach Druckstatus `FINISHED` sendet er `POST /camera/captures/{cycle_id}`.
3. `CameraClient` lädt sofort `GET /camera/captures/{cycle_id}` in das lokale Ergebnisverzeichnis.
4. Nach Abkühlung und Roboterpositionierung folgt `POST /measurements`.
5. Die Antwort wird als `Ra`/`Rz` in CycleResult und Persistenz überführt.

Die API kennt weder Experiment-ID, Run-Nummer noch Optimiereriteration. Die Korrelation geschieht ausschließlich über Cycle-ID und Dateien auf dem Hauptrechner.

## Nebenläufigkeit und Betrieb

FastAPI kann parallele Requests annehmen. Das SJ-220 schützt sich zusätzlich mit Thread-Lock und Prozess-Lockdatei; ein zweiter Prozess erhält einen Port-in-use-Fehler. Für Kameraaufnahmen existiert keine vergleichbare explizite Locklogik. Der Orchestrator arbeitet seriell und erzeugt normalerweise keine Parallelaufrufe.

Offene Betriebsaufgaben sind Authentifizierung/TLS, eine versionierte systemd-Unit, strukturierte Request-Logs, konfigurierbarer serieller Port und ein Health-Check, der optional den echten Gerätezustand prüft.

Weiter: [12 – Übergabe und offene Punkte](12_uebergabe_und_offene_punkte.md)
