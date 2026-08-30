# Aktuelle Fehler- und Wiederanlaufregel

Diese Datei beschreibt die verbindliche Regel ab Framework-Schritt 10.

## Vergleichbare Fehler

Ein Parametersatz erhält höchstens zwei physische Versuche:

1. Versuch 1 erfolgreich: echte Messwerte speichern und fortfahren.
2. Versuch 1 fehlerhaft: Fehlversuch archivieren und dieselben Parameter automatisch erneut ausführen.
3. Versuch 2 erfolgreich: echte Messwerte speichern und fortfahren.
4. Versuch 2 fehlerhaft: Parametersatz ohne dritten Versuch abschließen und fortfahren.

Für Punkt 4 wird zu Beginn des Experiments genau ein Modus gewählt:

- `penalty`: künstlichen Zielfunktionswert `100.0` für den Optimierer speichern;
- `ignore`: keinen Zielfunktionswert speichern und den Satz aus Optimiererbeobachtungen ausschließen.

`Ra_um` und `Rz_um` bleiben in beiden Fehlerfällen leer. Dadurch wird die Penalty nie als echte Messung ausgegeben.

## Abbruchgrenze

Nach drei direkt aufeinanderfolgenden Parametersätzen, die jeweils zweimal fehlschlagen, stoppt der Dauerlauf vor dem nächsten Parametersatz. Dabei spielt es keine Rolle, ob für die Optimierung `penalty` oder `ignore` gewählt wurde.

Eine erfolgreiche Messung setzt `consecutive_failed_parameter_sets` wieder auf null.

## Sicherheitsausnahmen

- Preflight- und vorbereitende Fehler verbrauchen keinen physischen Versuch und stoppen den unbeaufsichtigten Lauf.
- Roboterkollisionen, fehlgeschlagene Handhabung und unklare Hardwarezustände werden nicht automatisch wiederholt. Sie erzeugen einen manuellen Stopp ohne Optimiererbeobachtung.
- Ein dritter physischer Versuch desselben Parametersatzes ist nicht erlaubt.

## Gespeicherte Nachweise

- `runs/run_XXXX.json`: aktueller verbindlicher Runzustand;
- `attempt_history/`: archivierte Fehlversuche;
- `run_state.json`: Fehlerbehandlungsmodus, Fehlerfolge und Wiederanlaufpunkt;
- `results.csv`: unterscheidet `measured`, `penalty` und `ignored_failure`;
- `logs/preflight_run_XXXX_attempt_YY.json`: Preflight-Nachweis je Versuch.

Die konkreten Installations-, Test- und Startbefehle stehen in `docs/OPTIMIZER_FRAMEWORK_STEP_10.md`.
