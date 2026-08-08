# Mobiler NFC-Ablauf für Fremdspulen

Status: Produktvorschlag, noch nicht implementiert

Festgehalten: 2026-08-08

## Ziel

Nicht-Bambu-Spulen sollen sich ohne Raspberry Pi, separaten NFC-Leser oder
Nachbildung eines Bambu-RFID-Tags schnell identifizieren und einem AMS-Slot
zuweisen lassen.

Der geplante Bedienablauf ist:

1. Jede Spule erhält in PrintOps einen zufälligen, stabilen Scan-Link, zum
   Beispiel `/s/7K4M9X`.
2. PrintOps erzeugt daraus einen NFC-Inhalt und einen QR-Code.
3. Der Benutzer beschreibt einen günstigen NTAG einmalig mit dem Smartphone
   und befestigt ihn an der Spule.
4. Beim Antippen öffnet sich eine kleine mobile PrintOps-Seite mit:
   - Spulendaten und Restmenge,
   - dem zuletzt verwendeten Drucker,
   - den verfügbaren AMS-Slots,
   - der Aktion **Zuweisen und konfigurieren**.
5. PrintOps weist die Spule zu und setzt Material, Farbe, Filament-Preset und
   K-Profil über die vorhandene Drucker- und MQTT-Logik.
6. Gewicht und Verbrauch bleiben ausschließlich in PrintOps beziehungsweise
   im konfigurierten Spoolman. Der NFC-Tag muss nach einem Druck nicht neu
   beschrieben werden.

Der Tag enthält im ersten Ausbauschritt nur den stabilen Link. PrintOps bleibt
damit die maßgebliche Datenquelle; geänderte Restmengen, Profile oder Farben
veralten nicht auf dem Tag.

## Was der Benutzer dafür benötigt

### Minimalausstattung

- Ein NFC-fähiges Smartphone.
- Pro Spule einen beschreibbaren **NTAG213**-Aufkleber. NTAG215 und NTAG216
  funktionieren ebenfalls, bieten für einen kurzen URL-Datensatz aber keinen
  notwendigen Mehrwert.
- Eine stabile PrintOps-Adresse, die vom Smartphone erreichbar ist.
- Einen in PrintOps eingerichteten Bambu-Drucker mit AMS oder AMS Lite.
- Vollständige Spulendaten in PrintOps oder Spoolman, insbesondere Material,
  Farbe und das gewünschte Filament-Preset; ein K-Profil ist optional.
- Einen PrintOps-Benutzer mit den Berechtigungen zum Lesen und Ändern des
  Inventars sowie zum Konfigurieren des Druckers.

Für die geplante direkte Schreibfunktion im Browser ist ein NFC-fähiges
Android-Gerät mit Chrome der einfachste Zielpfad. Chrome unterstützt Web NFC
auf Android und kann NDEF-URL-Datensätze lesen und schreiben. Web NFC verlangt
eine sichere HTTPS-Verbindung und eine ausdrückliche Benutzeraktion. Da Web NFC
nicht browserübergreifend verfügbar ist, muss PrintOps zusätzlich einen
QR-Code und einen alternativen Schreibweg vorsehen.

Auf Geräten ohne Web-NFC-Schreibzugriff kann der von PrintOps erzeugte Link mit
einer NFC-Schreib-App auf den Tag geschrieben werden. Das spätere Antippen
öffnet nur eine gewöhnliche NDEF-URL und benötigt keine dauerhaft installierte
PrintOps-App.

### Nicht erforderlich

- Kein Raspberry Pi.
- Kein PN5180- oder ACR122U-Leser.
- Keine Waage und kein SpoolBuddy-Display.
- Kein Bambu-kompatibler MIFARE-Classic-Tag.
- Kein erneutes Beschreiben des Tags nach jedem Druck.

Eine zweite NFC-Marke auf der gegenüberliegenden Spulenseite kann den Zugriff
bequemer machen, ist aber nicht erforderlich. Tags dürfen zunächst nicht
permanent schreibgeschützt werden, damit die Spule später neu verknüpft werden
kann.

## Noch in PrintOps zu implementieren

Der beschriebene Ablauf ist eine festgehaltene Produktidee und noch keine
zugesicherte Ist-Funktion. Für die Umsetzung werden mindestens benötigt:

1. Ein zufälliger, nicht erratbarer Scan-Token pro Spule; fortlaufende
   Datenbank-IDs dürfen nicht als öffentlicher Schlüssel dienen.
2. Eine Auflösung des Tokens gegen die jeweils aktive Inventarquelle, also die
   lokale PrintOps-Datenbank oder Spoolman.
3. Eine mobile Route wie `/s/{token}` mit Spulenübersicht und AMS-Auswahl.
4. Eine authentifizierte Zuweisungsaktion, die vorhandene Slot-Zuordnung und
   MQTT-Konfiguration wiederverwendet.
5. Ein NFC-/QR-Bereich in der Spulenansicht, der den Scan-Link anzeigt, als
   QR-Code ausgibt und auf unterstützten Android-Geräten als NDEF-URL schreibt.
6. Eine konfigurierbare, stabile externe beziehungsweise lokale Basis-URL für
   generierte Links.
7. Eindeutige Behandlung von archivierten, gelöschten oder neu verknüpften
   Spulen sowie eine widerrufbare Token-Rotation.
8. Tests für lokale Inventare und Spoolman, Berechtigungen, mobile Darstellung,
   ungültige Tokens und die AMS-Zuweisung.

## Grenzen

Der NTAG wird nicht vom unveränderten Bambu-AMS als Bambu-Filament erkannt. Das
Smartphone identifiziert die Spule gegenüber PrintOps; anschließend konfiguriert
PrintOps den ausgewählten AMS-Slot. Der Ablauf ersetzt damit die manuelle
Filamentauswahl, aber nicht das proprietäre Bambu-RFID-Verfahren.

Eine spätere Erweiterung kann zusätzlich OpenTag3D oder TigerTag lesen und
schreiben. Diese Interoperabilität ist für den einfachen Link-basierten
Erstausbau nicht erforderlich.

## Referenzen

- [OpenSpoolMan](https://github.com/drndos/openspoolman)
- [TigerPOD](https://github.com/TigerTag-Project/TigerPOD)
- [TigerTag RFID Guide](https://github.com/TigerTag-Project/TigerTag-RFID-Guide)
- [Web NFC in Chrome für Android](https://developer.chrome.com/docs/capabilities/nfc)
- [MDN: Web NFC API](https://developer.mozilla.org/en-US/docs/Web/API/Web_NFC_API)
