# Logos für Dokumentlayouts

Logos können als PNG, JPEG oder sicheres SVG mit höchstens 5 MiB hochgeladen
werden. PrintOps entfernt Metadaten und speichert das geprüfte Ergebnis als PNG.
SVG-Logos dürfen keine Skripte oder externen Referenzen enthalten.

Eine zusammenhängende SVG-Koordinatenfolge darf höchstens 16.384 Zeichen
enthalten. Bei Pfaden gilt diese Grenze für die Parameter zwischen zwei
expliziten Pfadbefehlen, bei Polygonen und Polylinien für das gesamte
`points`-Attribut. Die Grenze verhindert überlange Verarbeitung beim Upload.
Wissenschaftliche Zahlenschreibweisen und implizite Koordinaten innerhalb
dieser Grenze bleiben unterstützt.

Bei der Meldung `svg_path_complexity` das Logo mit expliziten Pfadbefehlen
neu exportieren oder als PNG hochladen. Große Pfade mit kurzen expliziten
Befehlen bleiben innerhalb des Uploadlimits zulässig.
