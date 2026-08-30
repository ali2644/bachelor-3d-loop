# Optimierer-Framework – Schritt 11

Dieser Schritt entfernt die früher im Programm fest codierten Versuchsgrenzen.
Die Grenzen werden nun ausschließlich in der jeweiligen Optimierer-JSON festgelegt.

## Ergebnis

- Alle sechs Prozessparameter können variabel oder fest konfiguriert werden.
- `top_solid_layers` kann als ganzzahliger Optimierungsparameter verwendet werden.
- `top_solid_layers = 5` als fester Wert bleibt vollständig kompatibel.
- Der Profilgenerator überschreibt `top_solid_layers` nicht mehr mit dem Wert 5.
- LHS, Bayesian Optimization und die übrigen Framework-Strategien verwenden die
  in der JSON angegebenen Bereiche.

## Installation erst nach Ende des laufenden Hardwareversuchs

Während ein Hardwareprozess läuft, dürfen keine Python- oder Konfigurationsdateien
ausgetauscht werden. Nach dem Ende des laufenden Experiments kann das Paket im
Projektverzeichnis entpackt werden:

```bash
unzip -o ~/Downloads/optimizer-framework-schritt-11.zip \
  -d ~/Projects/bachelor-3d-loop/3d-automation
```

Danach werden zunächst nur Offline-Tests ausgeführt:

```bash
PYTHONPATH=src python tests/test_optimizer_config.py
PYTHONPATH=src python tests/test_print_parameters.py
PYTHONPATH=src python tests/test_warm_start.py
PYTHONPATH=src python tests/test_framework_runner.py
```

## Bestehendes Experiment

Die aktuell verwendete Konfiguration mit folgendem Eintrag bleibt gültig:

```json
"fixed_parameters": {
  "top_solid_layers": 5
}
```

Die Konfiguration eines bereits gestarteten Experiments darf nicht nachträglich
verändert werden. Für andere Grenzen oder variable Top-Layer muss ein neues
Experiment mit einem neuen `experiment_name` und einem neuen `output_directory`
angelegt werden.

## Vollständig variables Beispiel

Die Datei `config/optimizer_config.flexible.example.json` enthält alle sechs
Parameter als Variablen. Sie dient nur als Strukturbeispiel. Die dort gewählten
Grenzen sind nicht automatisch für einen Hardwareversuch freigegeben.

Weitere Einzelheiten stehen in `docs/OPTIMIZER_FLEXIBLE_BOUNDS.md`.
