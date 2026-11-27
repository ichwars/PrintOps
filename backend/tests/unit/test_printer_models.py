"""Unit tests for printer model utilities."""

import pytest

from backend.app.services.camera import get_camera_port, supports_rtsp
from backend.app.services.firmware_check import API_KEY_TO_DEV_MODEL, MODEL_TO_API_KEY
from backend.app.services.printer_manager import (
    supports_airduct,
    supports_chamber_heater,
    supports_chamber_temp,
)
from backend.app.utils.printer_models import (
    CARBON_ROD_MODELS,
    LINEAR_RAIL_MODELS,
    STEEL_ROD_MODELS,
    get_rod_type,
    h2c_nozzle_mapping_capability,
    has_ethernet,
    has_external_storage,
    has_remote_storage_toggle,
    is_dual_nozzle_model,
    is_gcode_compatible,
    normalize_printer_model,
    normalize_printer_model_id,
    supports_nozzle_flow_type,
    uses_exhaust_fan_label,
)


class TestGetRodType:
    """Tests for get_rod_type() rod/rail classification."""

    @pytest.mark.parametrize("model", ["X1C", "X1", "X1E", "P1P", "P1S"])
    def test_carbon_rod_models(self, model: str):
        assert get_rod_type(model) == "carbon"

    @pytest.mark.parametrize("model", ["C11", "C12", "C13"])
    def test_carbon_rod_internal_codes(self, model: str):
        assert get_rod_type(model) == "carbon"

    def test_p2s_is_steel_rod(self):
        """P2S uses hardened steel rods, not carbon rods (#640)."""
        assert get_rod_type("P2S") == "steel_rod"

    def test_p2s_internal_code_is_steel_rod(self):
        """N7 (P2S internal code) uses steel rods."""
        assert get_rod_type("N7") == "steel_rod"

    @pytest.mark.parametrize("model", ["A1", "A1 Mini", "H2D", "H2D Pro", "H2C", "H2S"])
    def test_linear_rail_models(self, model: str):
        assert get_rod_type(model) == "linear_rail"

    @pytest.mark.parametrize("model", ["N1", "N2S", "A11", "A12", "O1D", "O1E", "O2D", "O1C", "O1C2", "O1S"])
    def test_linear_rail_internal_codes(self, model: str):
        assert get_rod_type(model) == "linear_rail"

    def test_unknown_model_returns_none(self):
        assert get_rod_type("UNKNOWN") is None

    def test_none_returns_none(self):
        assert get_rod_type(None) is None

    def test_case_insensitive(self):
        assert get_rod_type("p2s") == "steel_rod"
        assert get_rod_type("x1c") == "carbon"
        assert get_rod_type("a1") == "linear_rail"

    def test_strips_whitespace_and_dashes(self):
        assert get_rod_type(" P2S ") == "steel_rod"
        assert get_rod_type("A1-Mini") == "linear_rail"


class TestX2DModel:
    """X2D printer support (issue #988).

    The X2D is a dual-nozzle enclosed printer launched April 2026. It shares
    the hardened steel rod hardware with P2S (NOT carbon rods) and uses
    RTSP on port 322 like other X/H series printers. Internal SSDP/MQTT
    model code is "N6"; serial numbers begin with "20P9".
    """

    def test_x2d_is_steel_rod_display_name(self):
        assert get_rod_type("X2D") == "steel_rod"

    def test_x2d_is_steel_rod_internal_code(self):
        assert get_rod_type("N6") == "steel_rod"

    def test_x2d_model_id_map(self):
        assert normalize_printer_model_id("N6") == "X2D"

    def test_x2d_model_map(self):
        assert normalize_printer_model("Bambu Lab X2D") == "X2D"

    def test_x2d_has_no_ethernet_display_name(self):
        """X2D spec sheet: "Ethernet — Not Available" (Wi-Fi only)."""
        assert has_ethernet("X2D") is False

    def test_x2d_has_no_ethernet_internal_code(self):
        assert has_ethernet("N6") is False

    def test_x2d_supports_rtsp_display_name(self):
        assert supports_rtsp("X2D") is True

    def test_x2d_supports_rtsp_internal_code(self):
        assert supports_rtsp("N6") is True

    def test_x2d_camera_port_is_rtsp(self):
        assert get_camera_port("N6") == 322
        assert get_camera_port("X2D") == 322

    def test_x2d_not_in_carbon_rod_set(self):
        """Regression guard: X2D has hardened steel rods, not carbon (#988).

        A prior PR classified X2D as carbon; the reporter confirmed it uses
        the same stainless steel rod gantry as P2S. This assertion pins the
        classification so a future change that reverts it will fail loudly.
        """
        assert "X2D" not in CARBON_ROD_MODELS
        assert "N6" not in CARBON_ROD_MODELS
        assert "X2D" in STEEL_ROD_MODELS
        assert "N6" in STEEL_ROD_MODELS


class TestA2LModel:
    """A2L printer support (#1684).

    The A2L is a hybrid 3D printer + cutter/plotter announced June 2026. It
    uses linear rails like the A1 family, has NO Ethernet (Wi-Fi 2.4 GHz only),
    a low-rate chamber-image camera on port 6000 (no RTSP), and a single FDM
    extruder (the second "tool head" in BambuStudio's profile is the cutter,
    not a second extruder — must NOT be classified as dual-nozzle). Internal
    SSDP/MQTT model code is "N9"; serial numbers begin with "26A19".
    """

    def test_a2l_is_linear_rail_display_name(self):
        assert get_rod_type("A2L") == "linear_rail"

    def test_a2l_is_linear_rail_internal_code(self):
        assert get_rod_type("N9") == "linear_rail"

    def test_a2l_model_id_map(self):
        assert normalize_printer_model_id("N9") == "A2L"

    def test_a2l_model_map(self):
        assert normalize_printer_model("Bambu Lab A2L") == "A2L"

    def test_a2l_has_no_ethernet_display_name(self):
        """A2L specs (bambulab.com/de-de/a2l/specs) list Ethernet 'Nicht verfügbar'."""
        assert has_ethernet("A2L") is False

    def test_a2l_has_no_ethernet_internal_code(self):
        assert has_ethernet("N9") is False

    def test_a2l_does_not_support_rtsp_display_name(self):
        """A2L uses the low-rate chamber-image protocol on port 6000, not RTSP."""
        assert supports_rtsp("A2L") is False

    def test_a2l_does_not_support_rtsp_internal_code(self):
        assert supports_rtsp("N9") is False

    def test_a2l_camera_port_is_chamber_image(self):
        assert get_camera_port("A2L") == 6000
        assert get_camera_port("N9") == 6000

    def test_a2l_is_not_dual_nozzle(self):
        """A2L has a single FDM extruder + a cutter/plotter head. The
        BambuStudio profile flag ``use_double_extruder_default_texture`` flags
        the dual TOOL HEADS, not dual filament extrusion — A2L must not land
        in the dual-nozzle group or AMS routing will target the deputy slot
        and the firmware will reject the print with 07FF_8012.
        """
        assert is_dual_nozzle_model("A2L") is False
        assert is_dual_nozzle_model("N9") is False

    def test_a2l_in_linear_rail_set(self):
        assert "A2L" in LINEAR_RAIL_MODELS
        assert "N9" in LINEAR_RAIL_MODELS

    def test_a2l_not_in_carbon_or_steel_rod_sets(self):
        assert "A2L" not in CARBON_ROD_MODELS
        assert "N9" not in CARBON_ROD_MODELS
        assert "A2L" not in STEEL_ROD_MODELS
        assert "N9" not in STEEL_ROD_MODELS


class TestH3CModel:
    """H3C printer support: recognition and printer control only.

    Internal model code "N10" comes from BambuStudio 02.09.01.70's
    ``resources/profiles/BBL/machine/Bambu Lab H3C.json``. The H3C has nine
    tool heads, an active chamber heater (65 °C) and Wi-Fi only (no Ethernet).
    BambuStudio models the nine tools as ONE extruder with nine nozzles, so the
    H3C must stay out of the dual-nozzle and H2C nozzle-rack groups: both carry
    wire-ID assumptions (0 = right / 1 = left, rack IDs 16-21) that do not
    describe this printer.
    """

    def test_model_code_maps_to_display_name(self):
        assert normalize_printer_model_id("N10") == "H3C"
        assert normalize_printer_model("Bambu Lab H3C") == "H3C"

    @pytest.mark.parametrize("model", ["H3C", "N10"])
    def test_has_no_ethernet(self, model: str):
        assert has_ethernet(model) is False

    @pytest.mark.parametrize("model", ["H3C", "N10"])
    def test_camera_uses_rtsp(self, model: str):
        assert supports_rtsp(model) is True
        assert get_camera_port(model) == 322

    @pytest.mark.parametrize("model", ["H3C", "N10"])
    def test_has_no_dual_nozzle_or_h2c_rack_dispatch(self, model: str):
        assert is_dual_nozzle_model(model) is False
        assert h2c_nozzle_mapping_capability(model, "N10", "01.02.00.00") == (False, "not_h2c")

    @pytest.mark.parametrize("model", ["H3C", "N10"])
    def test_chamber_sensor_heater_and_airduct(self, model: str):
        assert supports_chamber_temp(model) is True
        assert supports_chamber_heater(model) is True
        assert supports_airduct(model) is True

    def test_rod_type_is_steel_rod(self):
        """Metal linear rods on X and Y (no printhead rail), per Bambu's H3C
        wiki main-components page and CNC Kitchen's review.

        Unknown (None) made maintenance fall back to "Clean Carbon Rods".
        """
        assert get_rod_type("H3C") == "steel_rod"
        assert get_rod_type("N10") == "steel_rod"

    def test_firmware_check_keys(self):
        assert MODEL_TO_API_KEY["H3C"] == "h3c"
        assert MODEL_TO_API_KEY["N10"] == "h3c"
        assert API_KEY_TO_DEV_MODEL["h3c"] == "N10"


class TestA1SeriesModelIds:
    """Regression guard for the A1-family internal-code → display-name map.

    The serial-prefix and firmware-API key tables across the codebase agree
    that N2S is the A1 (serial prefix 039) and N1 is the A1 Mini (serial
    prefix 030). PRINTER_MODEL_ID_MAP had these swapped, which silently
    misclassified A1 as A1 Mini in any path that resolved by internal code.
    """

    def test_n2s_is_a1(self):
        assert normalize_printer_model_id("N2S") == "A1"

    def test_n1_is_a1_mini(self):
        assert normalize_printer_model_id("N1") == "A1 Mini"


class TestDualNozzleModel:
    """is_dual_nozzle_model — the single source of truth for nozzle class,
    consumed by start_print, the K-profile routes, and the re-slice guard."""

    def test_h2d_and_pro_are_dual(self):
        # Takes a normalized model code (like has_ethernet) — "H2D Pro" with a
        # space is accepted; full "Bambu Lab …" names are normalized by callers.
        assert is_dual_nozzle_model("H2D") is True
        assert is_dual_nozzle_model("H2D Pro") is True
        assert is_dual_nozzle_model("H2DPRO") is True

    def test_internal_codes_are_dual(self):
        assert is_dual_nozzle_model("O1D") is True  # H2D
        assert is_dual_nozzle_model("O1E") is True  # H2D Pro

    def test_single_nozzle_models_are_not_dual(self):
        # H2S is in the H2 family but single-nozzle (#1386) — must be False.
        for model in ("X1C", "X1E", "P1S", "P1P", "A1", "A1 Mini", "P2S", "H2S"):
            assert is_dual_nozzle_model(model) is False, model

    def test_none_and_empty_are_not_dual(self):
        assert is_dual_nozzle_model(None) is False
        assert is_dual_nozzle_model("") is False


class TestSupportsNozzleFlowType:
    def test_a_series_has_one_flow_variant(self):
        for model in ("A1", "A1 Mini", "A1MINI", "A2L"):
            assert supports_nozzle_flow_type(model) is False, model

    def test_a_series_internal_codes(self):
        for code in ("N1", "N2S", "N9", "A04", "A11", "A12"):
            assert supports_nozzle_flow_type(code) is False, code

    def test_other_single_nozzle_models_offer_both_flows(self):
        for model in ("X1", "X1C", "X1E", "P1P", "P1S", "P2S", "H2S"):
            assert supports_nozzle_flow_type(model) is True, model

    def test_dual_nozzle_models_offer_both_flows(self):
        for model in ("H2D", "H2D Pro", "H2C"):
            assert supports_nozzle_flow_type(model) is True, model

    def test_unknown_and_empty_default_to_supported(self):
        assert supports_nozzle_flow_type(None) is True
        assert supports_nozzle_flow_type("") is True
        assert supports_nozzle_flow_type("SomeFuturePrinter") is True


class TestGcodeCompatibility:
    def test_exact_match_is_compatible(self):
        assert is_gcode_compatible("H2D", "H2D") is True
        assert is_gcode_compatible("O1D", "H2D") is True

    @pytest.mark.parametrize("target", ["X1", "X1C", "X1E", "P1P", "P1S"])
    def test_x1_p1_family_is_compatible(self, target: str):
        assert is_gcode_compatible("X1C", target) is True

    def test_cross_family_mismatch_is_blocked(self):
        assert is_gcode_compatible("A1", "P1S") is False
        assert is_gcode_compatible("H2D", "P1S") is False

    def test_missing_metadata_stays_compatible(self):
        assert is_gcode_compatible(None, "P1S") is True
        assert is_gcode_compatible("P1S", None) is True


class TestHasExternalStorage:
    """Pins which Bambu models have a MicroSD slot. The connection
    diagnostic flips its ``external_storage`` check from ``fail`` to
    ``skip`` based on this — a false add (a model with a real slot marked
    no-storage) would silently disable a genuine fail signal for its users.

    See TestExternalStorageClassification for the per-model spec-sheet
    facts; this class pins the diagnostic-facing behaviour.
    """

    @pytest.mark.parametrize("model", ["A2L", "a2l", "N9"])
    def test_a2l_has_no_reachable_toggle(self, model: str):
        # #3499: no option on the printer or in either slicer.
        assert has_remote_storage_toggle(model) is False

    @pytest.mark.parametrize(
        "model",
        ["X1C", "X1E", "X1", "P1S", "P1P", "A1", "A1 Mini", "A2L"],
    )
    def test_models_with_a_card_slot_have_external_storage(self, model: str):
        assert has_external_storage(model) is True

    def test_unknown_model_defaults_to_true(self):
        # Default-true keeps the diagnostic active for new Bambu models;
        # add them to NO_EXTERNAL_STORAGE_MODELS explicitly when they ship
        # without a slot.
        assert has_external_storage("BrandNewModel2027") is True

    def test_none_and_empty_default_to_true(self):
        assert has_external_storage(None) is True
        assert has_external_storage("") is True


class TestP3CModel:
    """P3C printer support (released Nov 24, 2026; internal code "N11").

    The P3C brings the H3C's SwapTek tool changer downmarket: one extruder
    (FlexFeed) feeding up to seven docked PrintTools, so like the H3C it must
    stay out of the dual-nozzle group. Per the official spec sheet
    (bambulab.com/en-us/p3c/specs) it has NO Ethernet (Wi-Fi 6 only) and NO
    MicroSD slot (built-in 64 GB eMMC + USB), steel linear rods on X and Y
    (CNC Kitchen hands-on), an enclosed but not actively heated chamber, and
    a 1080p live-view camera. Serial numbers begin with "331".
    """

    def test_model_code_maps_to_display_name(self):
        assert normalize_printer_model_id("N11") == "P3C"
        assert normalize_printer_model("Bambu Lab P3C") == "P3C"

    @pytest.mark.parametrize("model", ["P3C", "N11"])
    def test_is_steel_rod(self, model: str):
        assert get_rod_type(model) == "steel_rod"
        assert model in STEEL_ROD_MODELS

    @pytest.mark.parametrize("model", ["P3C", "N11"])
    def test_not_linear_rail_or_carbon(self, model: str):
        assert model not in LINEAR_RAIL_MODELS
        assert model not in CARBON_ROD_MODELS

    @pytest.mark.parametrize("model", ["P3C", "N11"])
    def test_has_no_ethernet(self, model: str):
        assert has_ethernet(model) is False

    @pytest.mark.parametrize("model", ["P3C", "N11"])
    def test_has_no_external_storage_slot(self, model: str):
        """Spec sheet: built-in 64 GB eMMC + USB port, no card slot."""
        assert has_external_storage(model) is False

    @pytest.mark.parametrize("model", ["P3C", "N11"])
    def test_not_dual_nozzle(self, model: str):
        """One extruder, up to seven docked PrintTools (Swaptek) — like the
        H3C, a tool changer is not a dual-nozzle printer."""
        assert is_dual_nozzle_model(model) is False

    @pytest.mark.parametrize("model", ["P3C", "N11"])
    def test_single_nozzle_flow_class(self, model: str):
        """All PrintTools share one flow class (max 40 mm³/s); Bambu sells
        no high-flow variant, so the Standard/High-Flow picker stays hidden."""
        assert supports_nozzle_flow_type(model) is False

    @pytest.mark.parametrize("model", ["P3C", "N11"])
    def test_camera_uses_rtsp(self, model: str):
        assert supports_rtsp(model) is True
        assert get_camera_port(model) == 322

    @pytest.mark.parametrize("model", ["P3C", "N11"])
    def test_chamber_sensor_without_heater(self, model: str):
        assert supports_chamber_temp(model) is True
        assert supports_chamber_heater(model) is False
        assert supports_airduct(model) is False

    def test_firmware_check_keys(self):
        assert MODEL_TO_API_KEY["P3C"] == "p3c"
        assert MODEL_TO_API_KEY["N11"] == "p3c"
        assert API_KEY_TO_DEV_MODEL["p3c"] == "N11"


class TestEthernetClassification:
    """Official spec sheets: only the X1E and the H2D Pro have an RJ45 port.

    X1C (BL-P001), P1S (C12), P2S (N7), H2D (O1D), H2C, H2S and X2D (N6) all
    list "Ethernet: Not available" — Wi-Fi only. The wired_network sentinel
    (wifi_signal == -90) must therefore never fire for them.
    """

    @pytest.mark.parametrize("model", ["X1E", "C13", "H2D Pro", "H2DPRO", "O1E", "O2D"])
    def test_ethernet_models(self, model: str):
        assert has_ethernet(model) is True

    @pytest.mark.parametrize(
        "model",
        ["X1", "X1C", "BL-P001", "BL-P002", "P1P", "P1S", "P2S", "A1", "A2L", "H2D", "H2C", "H2S", "X2D", "H3C", "P3C"],
    )
    def test_no_ethernet_models(self, model: str):
        assert has_ethernet(model) is False


class TestExternalStorageClassification:
    """MicroSD-slot facts from the official spec sheets.

    Slot present: X1/X1C/X1E, P1P/P1S (Micro SD), A1/A1 mini/A2L (Micro SD is
    their only storage). Slot absent (built-in eMMC + USB only): P2S, X2D,
    H2D, H2D Pro, H2C, H2S, H3C, P3C.
    """

    @pytest.mark.parametrize("model", ["A1", "A1 Mini", "A1MINI", "A1-Mini", "a1", "N1", "N2S", "A04", "A11", "A12"])
    def test_a1_series_has_a_microsd_slot(self, model: str):
        assert has_external_storage(model) is True

    @pytest.mark.parametrize(
        "model",
        [
            "P2S",
            "N7",
            "X2D",
            "N6",
            "H2D",
            "O1D",
            "H2D Pro",
            "H2DPRO",
            "O1E",
            "O2D",
            "H2C",
            "O1C",
            "O1C2",
            "H2S",
            "O1S",
            "H3C",
            "N10",
            "P3C",
            "N11",
        ],
    )
    def test_emmc_generation_has_no_card_slot(self, model: str):
        assert has_external_storage(model) is False

    @pytest.mark.parametrize("model", ["X1", "X1C", "X1E", "P1P", "P1S", "A2L"])
    def test_sd_slot_models_keep_storage_check(self, model: str):
        assert has_external_storage(model) is True

    @pytest.mark.parametrize("model", ["A1", "A1 Mini", "N1", "N2S", "A04", "A11", "A12"])
    def test_a1_series_has_no_remote_storage_toggle(self, model: str):
        """#1703 regression guard: the A1 family stores prints on its MicroSD
        (no internal storage), so the "store to external storage" option never
        appears and home_flag bit 11 is never set. The diagnostic skip must
        keep working — now via the toggle exclusion instead of a phantom
        "no slot" claim."""
        assert has_remote_storage_toggle(model) is False


class TestH3CRodType:
    """The H3C runs on metal linear rods (X and Y), not a printhead rail.

    Bambu's wiki main-components page: "The X-axis utilizes metal linear
    rods, bearing sleeves, and belt drives" (Y-axis also "linear rods"); CNC
    Kitchen: "two linear rods for the printhead instead of a linear rail".
    Bambu does not declare the rod material; the rods-class (oil-based)
    maintenance regime is the correct one, so H3C/N10 sits in
    STEEL_ROD_MODELS, not LINEAR_RAIL_MODELS.
    """

    @pytest.mark.parametrize("model", ["H3C", "N10"])
    def test_rod_type_is_steel_rod(self, model: str):
        assert get_rod_type(model) == "steel_rod"
        assert model in STEEL_ROD_MODELS

    @pytest.mark.parametrize("model", ["H3C", "N10"])
    def test_not_linear_rail(self, model: str):
        assert model not in LINEAR_RAIL_MODELS


class TestExhaustFanLabel:
    """BambuStudio machine profiles label fan 3 "Chamber" only on the
    X1/X1C/X1E and P1S; every other model (P1P, P2S, X2D, H2 series, H3C,
    P3C) uses the default "Exhaust" label."""

    @pytest.mark.parametrize("model", ["X1", "X1C", "X1E", "P1S", "BL-P001", "BL-P002", "C12", "C13"])
    def test_chamber_label_models(self, model: str):
        assert uses_exhaust_fan_label(model) is False

    @pytest.mark.parametrize(
        "model",
        [
            "P1P",
            "C11",
            "P2S",
            "N7",
            "X2D",
            "N6",
            "H2D",
            "O1D",
            "H2D Pro",
            "H2C",
            "O1C",
            "H2S",
            "O1S",
            "H3C",
            "N10",
            "P3C",
            "N11",
        ],
    )
    def test_exhaust_label_models(self, model: str):
        assert uses_exhaust_fan_label(model) is True
