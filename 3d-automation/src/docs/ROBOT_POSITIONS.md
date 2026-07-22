# Dokumentation der Roboterpositionen

Diese Datei wird aus `robot_positions.py` erzeugt. Positionswerte und Beschreibungen sollen daher nur dort geändert werden.

## Allgemeine Hinweise

- Alle Werte sind Gelenkwinkel des Niryo Ned2 in Radiant.
- Der Aufbau aus Drucker, Roboter und Qualitätsstation ist mechanisch fixiert.
- Die Positionen dürfen nur nach einem erneuten sicheren Einlernvorgang geändert werden.
- Schiebebewegungen werden mit reduzierter Armgeschwindigkeit ausgeführt.
- Vor automatischen Gesamttests neue oder geänderte Positionen einzeln testen.

## Ablaufübersicht

```text
HOME
→ PRINTER_SAFE
→ PRINTER_APPROACH
→ PRINTER_PICK
→ PRINTER_BREAK_OFF
→ PRINTER_RETREAT
→ PRINTER_SAFE
→ TRANSFER_CLEARANCE
→ QS_SAFE
→ QS_PART_RELEASE
→ QS_RETRACT
→ QS_SAFE
→ QS_ALIGNMENT_ORIENTATION
→ QS_ALIGNMENT_CONTACT
→ QS_ALIGNMENT_END
→ QS_SAFE
→ QS_FINAL_PUSH_CONTACT
→ QS_FINAL_PUSH_INTERMEDIATE
→ QS_FINAL_PUSH_END
→ QS_FINAL_PUSH
→ QS_FINAL_PUSH_INTERMEDIATE
→ QS_FINAL_PUSH_RETREAT
→ QS_LIFT_LEVER_GRIP
→ QS_PART_UNDER_PROBE
→ QS_LIFT_LEVER_END
→ QS_LIFT_LEVER_GRIP
→ QS_RETRACT
→ HOME
```

## Allgemein

### `HOME`

**Zweck:** Definierte Ausgangs- und Endposition des Roboters. Der Arm ist kompakt und befindet sich außerhalb der engen Stationsbereiche.

**Bewegungshinweis:** Wird zusätzlich als getestete, kollisionsfreie Übergangsposition zwischen Drucker und Qualitätsstation verwendet.

**Gelenkwerte:**

```python
HOME = JointsPosition(
    0.009924629997073886,
    0.3479143782035235,
    -1.34,
    0.015432461468649183,
    -0.09059752007504551,
    0.10747130874178756,
)
```

### `TRANSFER_CLEARANCE`

**Zweck:** Kollisionsfreie Zwischenposition für den Wechsel von der Druckerstation zur Qualitätsstation.

**Bewegungshinweis:** Verwendet bewusst dieselben Gelenkwerte wie HOME.

**Gelenkwerte:**

```python
TRANSFER_CLEARANCE = JointsPosition(
    0.009924629997073886,
    0.3479143782035235,
    -1.34,
    0.015432461468649183,
    -0.09059752007504551,
    0.10747130874178756,
)
```

## Druckerstation

### `PRINTER_SAFE`

**Zweck:** Sichere Position vor dem Drucker. Von hier beginnt die kontrollierte Annäherung an das Druckbett.

**Bewegungshinweis:** Der Roboter befindet sich außerhalb der unmittelbaren Kollisionszone von Druckbett, Düse und Bauteil.

**Gelenkwerte:**

```python
PRINTER_SAFE = JointsPosition(
    -1.6109277397450201,
    0.61,
    -1.3142459215575717,
    -0.059732597137747145,
    -0.09980140480235944,
    0.10900528952967337,
)
```

### `PRINTER_APPROACH`

**Zweck:** Annäherungsposition unmittelbar vor dem Greifen des gedruckten Bauteils.

**Bewegungshinweis:** Der Greifer ist geöffnet. Von dieser Position wird nur noch die kurze Bewegung zur Greifposition ausgeführt.

**Gelenkwerte:**

```python
PRINTER_APPROACH = JointsPosition(
    -1.6307127921456277,
    0.182785287013836,
    -0.2068205485331538,
    -0.022917058228491882,
    -0.11360723189333033,
    0.11053927031755917,
)
```

### `PRINTER_PICK`

**Zweck:** Exakte Greifposition am gedruckten Bauteil beziehungsweise an dessen Haltegeometrie.

**Bewegungshinweis:** An dieser Position wird der Greifer geschlossen.

**Gelenkwerte:**

```python
PRINTER_PICK = JointsPosition(
    -1.5880988331289343,
    -0.46409656562833435,
    -0.12198358425221345,
    0.029238288559620074,
    -1.0186558967458583,
    -0.09654813604700241,
)
```

### `PRINTER_BREAK_OFF`

**Zweck:** Seitliche Abknickbewegung, mit der das gegriffene Bauteil von der Druckplatte gelöst wird.

**Bewegungshinweis:** Nur mit geschlossenem Greifer und ausgehend von PRINTER_PICK anfahren.

**Gelenkwerte:**

```python
PRINTER_BREAK_OFF = JointsPosition(
    -1.7783397215963161,
    -0.43985743297663704,
    -0.10531918055417155,
    -0.004509288773864029,
    -1.0278597814731723,
    -0.09808211683488821,
)
```

### `PRINTER_RETREAT`

**Zweck:** Rückzugsposition nach dem Abknicken, bevor der Roboter wieder PRINTER_SAFE anfährt.

**Bewegungshinweis:** Die getestete Annäherungsposition wird bewusst auch für den Rückzug verwendet.

**Gelenkwerte:**

```python
PRINTER_RETREAT = JointsPosition(
    -1.6307127921456277,
    0.182785287013836,
    -0.2068205485331538,
    -0.022917058228491882,
    -0.11360723189333033,
    0.11053927031755917,
)
```

## Qualitätsstation

### `QS_SAFE`

**Zweck:** Sichere Position vor der Qualitätsstation. Sie trennt weiträumige Transportbewegungen von den engen Bewegungen innerhalb der QS.

**Bewegungshinweis:** Diese Position wird vor und nach mehreren QS-Teilsequenzen verwendet.

**Gelenkwerte:**

```python
QS_SAFE = JointsPosition(
    1.5425052274903028,
    0.5009239030673623,
    -0.49920508614425185,
    0.11053927031755917,
    -0.9987141465033456,
    -0.09348017447123125,
)
```

### `QS_PART_RELEASE`

**Zweck:** Ablageposition, an der das transportierte Bauteil in der Qualitätsstation losgelassen wird.

**Bewegungshinweis:** Nach dem Öffnen kurz warten, damit der Arm das Bauteil nicht durch eine unmittelbar folgende Bewegung verschiebt.

**Gelenkwerte:**

```python
QS_PART_RELEASE = JointsPosition(
    1.6581716876784705,
    -0.46258161983760326,
    0.4915694609938732,
    -0.059732597137747145,
    -1.5509472301421758,
    0.1519567515904714,
)
```

### `QS_RETRACT`

**Zweck:** Rückzugsposition nach dem Ablegen beziehungsweise nach dem Loslassen des Hubhebels.

**Bewegungshinweis:** Der Greifer entfernt sich kontrolliert aus dem engen Bereich der QS.

**Gelenkwerte:**

```python
QS_RETRACT = JointsPosition(
    1.5881630407224745,
    -0.3247215528810752,
    1.186929578939438,
    0.13201500134795818,
    -1.5356074222633196,
    0.007762557529221059,
)
```

### `QS_ALIGNMENT_ORIENTATION`

**Zweck:** Position zum Drehen und Ausrichten des Greifers für die erste Produktverschiebung.

**Bewegungshinweis:** Diese Bewegung erfolgt mit normaler Armgeschwindigkeit; erst der Kontakt mit dem Produkt wird langsam ausgeführt.

**Gelenkwerte:**

```python
QS_ALIGNMENT_ORIENTATION = JointsPosition(
    1.5409833003825635,
    0.5509171141614879,
    -0.49920508614425185,
    0.026170326983848913,
    -0.7302675086233581,
    -1.7655192332665801,
)
```

### `QS_ALIGNMENT_CONTACT`

**Zweck:** Kontaktposition für die erste Produktverschiebung nach dem Ablegen.

**Bewegungshinweis:** Ab dieser Position wird die reduzierte Schiebegeschwindigkeit verwendet.

**Gelenkwerte:**

```python
QS_ALIGNMENT_CONTACT = JointsPosition(
    1.5683779883218665,
    0.16006110015286984,
    -0.8385529432680132,
    -0.012364499892878023,
    0.6610530659889187,
    -1.6289949431447581,
)
```

### `QS_ALIGNMENT_END`

**Zweck:** Endposition der ersten Produktverschiebung. Das Bauteil ist danach für die finale Einschubbewegung vorpositioniert.

**Bewegungshinweis:** Nur langsam aus QS_ALIGNMENT_CONTACT anfahren.

**Gelenkwerte:**

```python
QS_ALIGNMENT_END = JointsPosition(
    1.5333736648438685,
    0.022201033196341702,
    -0.6961480389392919,
    -0.1302957133804865,
    0.5858880073825219,
    -1.4955386145987073,
)
```

### `QS_FINAL_PUSH_CONTACT`

**Zweck:** Kontaktposition für das finale horizontale Einschieben des Bauteils in die Messvorrichtung.

**Bewegungshinweis:** Mit normaler Geschwindigkeit annähern; die eigentliche Bewegung ab der nächsten Position langsam ausführen.

**Gelenkwerte:**

```python
QS_FINAL_PUSH_CONTACT = JointsPosition(
    1.4344484028408293,
    -0.35805036027715886,
    0.33855993613003443,
    0.12434509740852961,
    -1.557083153293719,
    -0.12722775180471535,
)
```

### `QS_FINAL_PUSH_INTERMEDIATE`

**Zweck:** Zwischenposition für einen kontrollierten und kollisionsfreien Schubweg innerhalb der Messvorrichtung.

**Bewegungshinweis:** Teil der langsamen Schiebebewegung.

**Gelenkwerte:**

```python
QS_FINAL_PUSH_INTERMEDIATE = JointsPosition(
    1.4938035600426525,
    -0.7216373500526175,
    0.9081795534449195,
    0.04457809643847632,
    -1.722753078385368,
    -0.04899473162254786,
)
```

### `QS_FINAL_PUSH_END`

**Zweck:** Vorletzte Schubposition unmittelbar vor der endgültigen horizontalen Produktposition.

**Bewegungshinweis:** Teil der langsamen Schiebebewegung.

**Gelenkwerte:**

```python
QS_FINAL_PUSH_END = JointsPosition(
    1.4983693413658696,
    -0.748906374285777,
    0.917269228189306,
    0.05378198116579025,
    -1.5248695567481199,
    0.009296538317106862,
)
```

### `QS_FINAL_PUSH`

**Zweck:** Endgültige horizontale Schubposition des Bauteils in der Messvorrichtung.

**Bewegungshinweis:** Das Bauteil soll danach korrekt vor dem Hubmechanismus liegen.

**Gelenkwerte:**

```python
QS_FINAL_PUSH = JointsPosition(
    1.4983693413658696,
    -0.4913655898614938,
    0.450665924644134,
    0.038442173286934,
    -1.0968889169280263,
    -0.05513065477409018,
)
```

### `QS_FINAL_PUSH_RETREAT`

**Zweck:** Rückzugsposition nach dem finalen Produktschub.

**Bewegungshinweis:** Wird über QS_FINAL_PUSH_INTERMEDIATE angefahren, damit der Greifer nicht am positionierten Produkt hängen bleibt.

**Gelenkwerte:**

```python
QS_FINAL_PUSH_RETREAT = JointsPosition(
    1.4755404347497838,
    0.007051575289030998,
    -0.06593058999516344,
    0.16576257868144229,
    -1.4558404212932667,
    -0.22693650301728185,
)
```

### `QS_LIFT_LEVER_GRIP`

**Zweck:** Start- und Greifposition am Hubhebel der Qualitätsstation.

**Bewegungshinweis:** Greifer vor dem Anfahren öffnen und an dieser Position schließen.

**Gelenkwerte:**

```python
QS_LIFT_LEVER_GRIP = JointsPosition(
    1.4770623618575232,
    -0.6489199520975258,
    0.8051632396752064,
    0.05531596195367605,
    -1.297840400141045,
    -0.03518890453157697,
)
```

### `QS_PART_UNDER_PROBE`

**Zweck:** Zwischenposition der Hebelbewegung, durch die das Bauteil unter der Mitutoyo-Messnadel positioniert wird.

**Bewegungshinweis:** Langsam anfahren und vor dem nächsten Hebelschritt drei Sekunden warten.

**Gelenkwerte:**

```python
QS_PART_UNDER_PROBE = JointsPosition(
    1.5333736648438685,
    -0.6428601689346015,
    0.800618402303013,
    0.07985965455984623,
    -1.2993743809289309,
    0.006228576741335257,
)
```

### `QS_LIFT_LEVER_END`

**Zweck:** Endposition der Hebelbewegung. Der Hubmechanismus bringt das Bauteil auf die erforderliche Höhe für die Rauheitsmessung.

**Bewegungshinweis:** Langsam anfahren, drei Sekunden halten und danach langsam zum Hebelstart zurückfahren.

**Gelenkwerte:**

```python
QS_LIFT_LEVER_END = JointsPosition(
    1.4664088721033495,
    -0.8534376338462214,
    1.1763249584043203,
    -0.22080057986573953,
    -1.5678210188089179,
    -0.12262580944105839,
)
```
