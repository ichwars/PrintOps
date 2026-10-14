# Modellanbieter und MakerWorld-Import

MakerWorld ist derzeit der einzige unterstützte Modellanbieter. In der
MakerWorld-Seite bleibt der Ablauf gleich: Modell-URL einfügen, Druckprofil
wählen und die 3MF in die Bibliothek importieren. Metadaten sind ohne
Cloud-Anmeldung verfügbar; Downloads benötigen den gespeicherten Bambu-Cloud-Token.
Die interne Anbietergrenze ergänzt keine weiteren Plattformen oder Logins.

## Vertrag für Erweiterungen

`backend/app/services/model_providers/base.py` definiert den kleinen
`ModelProvider`-Vertrag für Design-Metadaten, Instanzen, Download-Manifest,
3MF-Download, Thumbnail und Freigabe des HTTP-Clients. Die Rückgabewerte behalten
die vorhandenen MakerWorld-Datenformen bei: numerische Design-/Profil-IDs,
`design.modelId` als Zeichenkette, Instanzen in `hits` und Download-Manifeste
mit `url` und optionalem `name`. Ein weiterer Anbieter müsste diese Datenformen
abbilden und einen eigenen geprüften Adapter mitbringen.

Eine unveränderliche `ProviderRegistration` enthält den `ProviderDescriptor`,
einen URL-Parser und eine Factory. Der Descriptor beschreibt `source_type`,
Anzeigenamen und Tokenpflicht für Downloads. Der Status verwendet diese
Tokenpflicht, ohne einen HTTP-Client anzulegen; er prüft wie bisher die
Verfügbarkeit des Tokens, nicht dessen Gültigkeit beim Anbieter.

`catalog.py` registriert ausdrücklich nur MakerWorld. Die Registry sucht nach
Bibliotheks-Quelltyp oder lässt den validierenden Parser eine Modell-URL
zuordnen. Eine weitere Registrierung allein ändert weder die festen
`/makerworld`-Routen noch den beim Import gespeicherten Quelltyp `makerworld`.
Ein weiterer Anbieter benötigt ausdrücklich festgelegte Anwendungsrouten und
eine passende Entscheidung über den gespeicherten Bibliotheks-Quelltyp.
Unbekannte URLs und doppelte Quelltypen werden abgelehnt. Der
MakerWorld-Parser bleibt maßgeblich für bekannte URL-Formen, einschließlich
Locale-Pfad, Slug, optionalem Schema und Profilfragment. Eine URL mit
`makerworld.com` lediglich im fremden Host oder Benutzerinfo-Feld passt nicht.

## Zuständigkeiten und Sicherheit

Die Registry speichert Definitionen und Factories, keine Dienste oder Tokens.
Jeder Aufruf erzeugt einen eigenen `MakerWorldAdapter` mit dem für diesen
Aufrufer aufgelösten Token. Der Adapter verwendet unverändert die bewährten
Methoden von `MakerWorldService`. Der im App-Lebenszyklus bereitgestellte
HTTP-Pool bleibt gemeinsam; `close()` schließt nur einen selbst angelegten
Client. Die bisherigen `MakerWorld*Error`-Importnamen bleiben als Aliase der
neutralen Provider-Fehler verfügbar.

Die bestehenden `/api/v1/makerworld`-Routen nutzen die Registry für
URL-Auflösung, Import, Thumbnail und Status. API-Pfade und Antwortschemas
bleiben gleich. Berechtigungen und die Cloud-Scope-Prüfung bleiben in der
Anwendung: API-Schlüssel benötigen für Status/Auflösung `can_read_status`,
für Import `can_manage_library` und für den Token des Schlüsselinhabers
zusätzlich `can_access_cloud`. Ohne Cloud-Scope bleibt öffentliche Auflösung
möglich, aber der echte Download-Manifest-Aufruf wird mit 401 abgelehnt.
Bei aktivierter Authentifizierung ersetzen eventuell behaltene globale
Cloud-Zugangsdaten keine fehlende berechtigte Benutzeridentität. Die gemeinsame
MakerWorld-Tokenauflösung für Status und Dienste liest globale Zugangsdaten
nur bei deaktivierter Authentifizierung; der bisherige anonyme Import mit
globalem Token bleibt in diesem Betriebsmodus möglich.

Ordnerwahl, Schreibschutz externer Ordner, Deduplizierung pro Profil,
Dateinamenbereinigung, Bibliotheks-Speicherung und `created_by_id` verbleiben
in der Routen-/Bibliotheksschicht. Download-Hostprüfung, gesperrte Redirects,
200-MB-3MF-Grenze und 10-MB-Thumbnail-Grenze verbleiben im Dienst. Signierte
CDN-Downloads erhalten keinen zusätzlichen Bambu-Bearer; S3-Signaturen behalten
ihren bestehenden unveränderten Query-String-Transport.

Vor Aufnahme eines weiteren Anbieters sind echte Adapter-/Routentests mit
lokalem HTTP-Transport für URL-Prüfung, Berechtigungen, getrennte Zugangsdaten,
Fehlercodes und Dateischutz erforderlich. Neue Berechtigungen oder
Anbieter-Auswahl in der Oberfläche sind eine eigene Produktentscheidung.
