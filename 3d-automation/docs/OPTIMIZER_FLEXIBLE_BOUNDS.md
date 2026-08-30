# Frei konfigurierbare Parametergrenzen

Ab diesem Stand werden die Versuchsgrenzen ausschließlich in der jeweiligen Optimierer-JSON festgelegt. Die früher fest eingebauten Forschungsbereiche sind entfernt.

Alle sechs Prozessparameter können entweder variabel oder fest sein:

- `top_solid_layers` (ganzzahlig)
- `print_speed`
- `extrusion_width`
- `extrusion_multiplier`
- `temperature` (ganzzahlig)
- `fan_speed` (ganzzahlig)

## Top-Layer fest auf 5

Für Alis aktuelle Versuche bleibt die bisherige Form gültig:

```json
"parameters": [
  {"name": "print_speed", "lower": 50, "upper": 90},
  {"name": "extrusion_width", "lower": 0.38, "upper": 0.50},
  {"name": "extrusion_multiplier", "lower": 1.05, "upper": 1.20},
  {"name": "temperature", "lower": 215, "upper": 235},
  {"name": "fan_speed", "lower": 30, "upper": 80}
],
"fixed_parameters": {
  "top_solid_layers": 5
}
```

## Top-Layer optimieren

Für einen späteren Versuch des Betreuers wird `top_solid_layers` aus `fixed_parameters` entfernt und in `parameters` aufgenommen:

```json
"parameters": [
  {"name": "top_solid_layers", "lower": 3, "upper": 7},
  {"name": "print_speed", "lower": 40, "upper": 150}
],
"fixed_parameters": {
  "extrusion_width": 0.42,
  "extrusion_multiplier": 1.1,
  "temperature": 220,
  "fan_speed": 50
}
```

Jeder unterstützte Parameter muss genau einmal vorkommen: entweder in `parameters` oder in `fixed_parameters`.

## Verbleibende intrinsische Regeln

Die künstlichen bisherigen Forschungsgrenzen sind entfernt. Es bleiben nur Regeln, die aus Datentyp und Bedeutung folgen:

- `top_solid_layers`: ganze Zahl ab 0;
- `print_speed`, `extrusion_width`, `extrusion_multiplier`: größer als 0;
- `temperature`: ganze Zahl ab 0;
- `fan_speed`: ganze Prozentzahl von 0 bis 100;
- bei variablen Parametern muss `lower < upper` gelten.

Die frei gewählten Grenzen sind experimentelle Verantwortung. Vor einem Hardwarelauf müssen sie fachlich geprüft werden. Ein extremes, aber formal gültiges Intervall kann zu Fehldrucken, Gerätestopps oder unbrauchbaren Messungen führen.

## Wichtige Änderung im Slicerprofil

`top_solid_layers` wird nicht mehr nachträglich auf 5 überschrieben. Der im Parametersatz gespeicherte Wert wird direkt in das erzeugte Profil geschrieben.

Die Datei `config/optimizer_config.flexible.example.json` zeigt eine vollständige Konfiguration mit sechs variablen Parametern. Sie ist nur ein Strukturbeispiel und nicht automatisch für einen realen Hardwarelauf freigegeben.
