"""Dutch notification language keeps interpolation and fallback behavior."""

from string import Formatter

from backend.app.i18n import EN, TRANSLATIONS, Translator, get_translation


def test_selected_dutch_language_renders_print_and_printer_notifications():
    translator = Translator("nl")
    assert translator.t("notification.print_started") == "Afdruk gestart"
    assert translator.t("notification.print_progress", progress=35) == "Afdruk voor 35% voltooid"
    assert translator.t("notification.printer_disconnected", printer="Printer A") == "Printer A is losgekoppeld"
    assert translator.t("notification.slot_at_percent", printer="Printer A", slot=2, percent=15) == (
        "Printer A: sleuf 2 op 15%"
    )


def test_dutch_notification_catalog_covers_every_event_and_preserves_parameters():
    dutch = TRANSLATIONS["nl"]["notification"]
    assert dutch.keys() == EN["notification"].keys()
    formatter = Formatter()
    for key, english in EN["notification"].items():
        placeholders = {name for _, name, _, _ in formatter.parse(english) if name is not None}
        translated = {name for _, name, _, _ in formatter.parse(dutch[key]) if name is not None}
        assert translated == placeholders, key


def test_unknown_language_and_missing_key_keep_existing_fallback():
    assert get_translation("unsupported", "notification.print_started") == "Print Started"
    assert get_translation("nl", "notification.missing") == "notification.missing"
    assert get_translation("de", "notification.print_started") == "Druck gestartet"
