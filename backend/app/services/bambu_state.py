"""Decoded printer state, health reports and firmware stage names."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from backend.app.services.drying_telemetry import DryingTelemetry


@dataclass
class MQTTLogEntry:
    """Log entry for MQTT message debugging."""

    timestamp: str
    topic: str
    direction: str  # "in" or "out"
    payload: dict


@dataclass
class HMSError:
    """Health Management System error from printer."""

    code: str
    attr: int  # Attribute value for constructing wiki URL
    module: int
    severity: int  # 1=error (stopped), 2=warning (paused), 3=notice, 0=invalid
    message: str = ""
    # User-facing remediation actions from the bundled HMS catalog (e.g. "RESUME_PRINTING",
    # "CHECK_ASSISTANT"). Defaults to an empty list rather than None so the field always
    # satisfies HMSErrorResponse.actions: list[str] — a future code path that builds an
    # HMSError without explicitly passing actions can't silently land None on the schema
    # boundary and raise ValidationError at routes/printers.py response time.
    actions: list[str] = field(default_factory=list)
    # The `subtask_id` snapshotted from PrinterState when this error surfaced; Bambu's
    # HMS-aware commands echo it back as `job_id`. None for idle errors with no job.
    job_id: str | None = None
    # Canonical hex identifier for the firmware's `err` matching: 16 chars for the
    # 64-bit `hms[]` array path (`f"{attr:08X}{code:08X}"`), 8 chars for the
    # 32-bit `print_error` path. The frontend echoes this back to
    # execute_hms_action; the truncated 8-char short code that `_parse_status`
    # used to send caused the firmware to silently reject HMS commands on H2C
    # (#1830) and on `hms[]`-sourced faults generally.
    full_code: str = ""
    description: str | None = None  # Manufacturer text, resolved once using the serial prefix.


def _is_print_error_entry(error: HMSError) -> bool:
    """Whether this entry came from the 32-bit `print_error` field, whose
    full code has 8 hex digits; an `hms[]` entry's has 16."""
    return len(error.full_code) == 8


def _hms_short_code(error: HMSError) -> str:
    """The MMMM_EEEE short code of an entry from either source."""
    module = (error.attr >> 16) & 0xFFFF
    # The low half only: an hms[] code carries its alert level above it
    # (0x18061 for 0500_8061), and read whole it never matched, listing the
    # fault twice (M-U9).
    number = (int(error.code.replace("0x", ""), 16) & 0xFFFF) if error.code else 0
    return f"{module:04X}_{number:04X}"


def _hms_short_codes(errors: list) -> set[str]:
    return {_hms_short_code(e) for e in errors}


# HMS short codes the firmware emits during normal user-cancel sequences.
# These aren't faults — they're status echoes that confirm the cancel happened.
# Filtering them at parse-time keeps them out of state.hms_errors entirely,
# so they don't drive the printer card's "X problem" badge, the red pip, or
# any other consumer that treats hms_errors as the active-fault list.
_HMS_USER_ACTION_CODES: frozenset[str] = frozenset(
    {
        "0300_400C",  # "The task was canceled."
        "0500_400E",  # "Printing was cancelled."
    }
)


@dataclass
class NozzleInfo:
    """Nozzle hardware configuration."""

    nozzle_type: str = ""  # "stainless_steel" or "hardened_steel"
    nozzle_diameter: str = ""  # e.g., "0.4"


def nozzle_print_time_s(value: object) -> int | None:
    """A nozzle's accumulated print time from its ``nozzle_info`` entry (#1908).

    H2C firmware reports it per nozzle as ``p_t``, in seconds. Older firmware
    and other models leave it out, which stays None so the UI hides the row
    instead of showing "0h". A bool is an int to Python but never a duration.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return int(value)


@dataclass
class FilaSwitchState:
    """Filament Track Switch (FTS) accessory state.

    The FTS is an external accessory that mediates filament routing between an
    AMS and the printer's extruders. When installed, the AMS no longer has a
    fixed extruder assignment — any slot can be routed to any extruder via the
    track switch. Detected from print.device.fila_switch in MQTT.
    """

    installed: bool = False
    # in[track] = currently loaded slot for that track (-1 = empty). The slot
    # value is reported as observed in MQTT (treated as a global tray ID).
    in_slots: list[int] = field(default_factory=list)
    # out[track] = extruder this track terminates at (0 = right/main, 1 = left)
    out_extruders: list[int] = field(default_factory=list)
    stat: int = 0  # status flags (0 = idle)
    info: int = 0  # info flags


@dataclass
class PrintOptions:
    """AI detection and print options from xcam data."""

    # Core AI detectors
    spaghetti_detector: bool = False
    print_halt: bool = False
    halt_print_sensitivity: str = "medium"  # Spaghetti sensitivity
    first_layer_inspector: bool = False
    printing_monitor: bool = False  # AI print quality monitoring
    buildplate_marker_detector: bool = False
    allow_skip_parts: bool = False
    # Additional AI detectors - decoded from cfg bitmask
    nozzle_clumping_detector: bool = True
    nozzle_clumping_sensitivity: str = "medium"
    pileup_detector: bool = True
    pileup_sensitivity: str = "medium"
    airprint_detector: bool = True
    airprint_sensitivity: str = "medium"
    auto_recovery_step_loss: bool = True  # Uses print.print_option command
    filament_tangle_detect: bool = False


if TYPE_CHECKING:
    from backend.app.services.pause_eta import PauseTracking


@dataclass
class PrinterState:
    drying_telemetry: DryingTelemetry = field(default_factory=DryingTelemetry)
    pause_tracking: "PauseTracking | None" = None
    connection_generation: int = 0
    connected: bool = False
    state: str = "unknown"
    current_print: str | None = None
    subtask_name: str | None = None
    progress: float = 0.0
    remaining_time: int = 0
    layer_num: int = 0
    total_layers: int = 0
    temperatures: dict = field(default_factory=dict)
    raw_data: dict = field(default_factory=dict)
    gcode_file: str | None = None
    subtask_id: str | None = None
    hms_errors: list = field(default_factory=list)  # List of HMSError
    kprofile_diameters: set[str] = field(default_factory=set)
    kprofiles: list = field(default_factory=list)  # List of KProfile
    sdcard: bool = False  # SD card inserted
    store_to_sdcard: bool = False  # Store sent files on SD card (home_flag bit 11)
    timelapse: bool = False  # Timelapse recording active
    ipcam: bool = False  # Live view / camera streaming enabled
    wifi_signal: int | None = None  # WiFi signal strength in dBm
    wired_network: bool = False  # Ethernet connection detected (home_flag bit 18)
    door_open: bool = False  # Enclosure door open (home_flag bit 23; models with a door sensor: X1/X1C/X1E/X2D/P2S/H2*)
    # Nozzle hardware info (for dual nozzle printers, index 0 = left, 1 = right)
    nozzles: list = field(default_factory=lambda: [NozzleInfo(), NozzleInfo()])
    # AI detection and print options
    print_options: PrintOptions = field(default_factory=PrintOptions)
    # Calibration stage tracking (from stg_cur and stg fields)
    stg_cur: int = -1  # Current stage index (-1 = not calibrating)
    stg: list = field(default_factory=list)  # List of stages to execute
    # Air conditioning mode (0=cooling, 1=heating)
    airduct_mode: int = 0
    # Print speed level (1=silent, 2=standard, 3=sport, 4=ludicrous)
    speed_level: int = 2
    # Chamber light on/off
    chamber_light: bool = False
    # Active extruder for dual nozzle (0=right, 1=left) - from device.extruder.info[X].hnow
    active_extruder: int = 0
    # Currently loaded tray (global ID): 254/255 = external spools, 255 = no filament on legacy printers
    tray_now: int = 255
    # Raw firmware target/previous slot for paused AMS runout guidance.
    tray_tar: int = 255
    tray_pre: int = 255
    # Last valid tray_now (0-253) — survives unload (255) for usage tracking after print completes
    last_loaded_tray: int = -1
    # Pending load target - used to track what tray we're loading for H2D disambiguation
    pending_tray_target: int | None = None
    pending_tray_target_at: float | None = None
    # AMS status for filament change tracking (from print.ams.ams_status field)
    # ams_status is a combined value: lower 8 bits = sub status, bits 8-15 = main status
    # Main status: 0=idle, 1=filament_change, 2=rfid_identifying, 3=assist, 4=calibration, etc.
    ams_status: int = 0
    ams_status_main: int = 0  # (ams_status >> 8) & 0xFF
    ams_status_sub: int = 0  # ams_status & 0xFF
    # mc_print_sub_stage - filament change step indicator from print.mc_print_sub_stage
    # Used by OrcaSlicer/BambuStudio to track progress during filament load/unload
    mc_print_sub_stage: int = 0
    # AMS mapping for dual nozzle: which slot is active (from ams.ams_exist_bits/tray_exist_bits)
    ams_mapping: list = field(default_factory=list)
    # Per-AMS extruder map: {ams_id: extruder_id} where 0=right/main, 1=left/deputy
    print_ams_mapping: list[int] | None = None
    ams_extruder_map: dict = field(default_factory=dict)
    # Filament Track Switch (FTS) accessory — when installed, AMS info reports
    # bits 8-11 = 0xE (uninitialized) because routing is dynamic. See #1162.
    fila_switch: "FilaSwitchState" = field(default_factory=lambda: FilaSwitchState())
    # Plate dispatched by PrintOps for the current print. Some firmware versions
    # (P1S 01.10.00.00) only put the .3mf filename in print.gcode_file, so the
    # regex used to derive the plate number from the path always falls back to
    # plate 1 — and the printer card shows the wrong thumbnail (#1166). When
    # PrintOps dispatches the print itself we know the plate authoritatively;
    # we record it here and prefer it over the gcode_file regex. The subtask
    # field guards against staleness: if the printer is currently running a
    # different subtask (e.g. a Studio-direct dispatch), these values are
    # ignored. Cleared on disconnect.
    dispatched_plate_id: int | None = None
    dispatched_subtask: str | None = None
    # H2D per-extruder tray_now from snow field: {extruder_id: normalized_global_tray_id}
    # snow encodes AMS ID in high byte: ams_id = snow >> 8, slot = snow & 0xFF
    h2d_extruder_snow: dict = field(default_factory=dict)
    # H2C nozzle rack: full device.nozzle.info array for tool-changer printers (>2 nozzles)
    nozzle_rack: list = field(default_factory=list)
    # Timestamp of last AMS data update (for RFID refresh detection)
    last_ams_update: float = 0.0
    # Printable objects for skip object functionality: {identify_id: object_name}
    printable_objects: dict = field(default_factory=dict)
    # Objects that have been skipped during the current print
    skipped_objects: list = field(default_factory=list)
    # Fan speeds (0-100 percentage, None if not available for this model)
    cooling_fan_speed: int | None = None  # Part cooling fan
    big_fan1_speed: int | None = None  # Auxiliary fan
    big_fan2_speed: int | None = None  # Chamber/exhaust fan
    heatbreak_fan_speed: int | None = None  # Hotend heatbreak fan
    left_aux_fan_speed: int | None = None  # Part 10, second aux (right on X2D)
    exhaust_fan_present: bool | None = None
    # Tray change history during current print: [(global_tray_id, layer_num), ...]
    # Used by usage tracker to split filament weight on mid-print tray switch
    tray_change_log: list = field(default_factory=list)
    # Spools assigned to a tray during the current print, and the spool each
    # assigned tray held at its start (services.spool_swaps, #3325).
    spool_change_log: list = field(default_factory=list)
    # Firmware version info (from info.module[name="ota"].sw_ver)
    firmware_version: str | None = None
    # Developer LAN mode: parsed from MQTT "fun" field bit 0x20000000
    # True = dev mode ON (no encryption), False = dev mode OFF (encryption required), None = unknown
    developer_mode: bool | None = None
    # AMS Filament Backup: bit 18 of top-level print.cfg hex on new-protocol Bambu
    # printers (H/X/P/H2 families). True=ON, False=OFF, None=unknown (e.g. A1 family
    # which uses the old protocol path; field not yet found). Consumers must treat
    # None as "no opinion" — preserving today's behaviour, NOT as "disabled".
    ams_filament_backup: bool | None = None


# Stage name mapping from BambuStudio DeviceManager.cpp
STAGE_NAMES = {
    0: "Printing",
    1: "Auto bed leveling",
    2: "Heatbed preheating",
    3: "Vibration compensation",
    4: "Changing filament",
    5: "M400 pause",
    6: "Paused (filament ran out)",
    7: "Heating nozzle",
    8: "Calibrating dynamic flow",
    9: "Scanning bed surface",
    10: "Inspecting first layer",
    11: "Identifying build plate type",
    12: "Calibrating Micro Lidar",
    13: "Homing toolhead",
    14: "Cleaning nozzle tip",
    15: "Checking extruder temperature",
    16: "Paused by the user",
    17: "Pause (front cover fall off)",
    18: "Calibrating the micro lidar",
    19: "Calibrating flow ratio",
    20: "Pause (nozzle temperature malfunction)",
    21: "Pause (heatbed temperature malfunction)",
    22: "Filament unloading",
    23: "Pause (step loss)",
    24: "Filament loading",
    25: "Motor noise cancellation",
    26: "Pause (AMS offline)",
    27: "Pause (low speed of the heatbreak fan)",
    28: "Pause (chamber temperature control problem)",
    29: "Cooling chamber",
    30: "Pause (Gcode inserted by user)",
    31: "Motor noise showoff",
    32: "Pause (nozzle clumping)",
    33: "Pause (cutter error)",
    34: "Pause (first layer error)",
    35: "Pause (nozzle clog)",
    36: "Measuring motion precision",
    37: "Enhancing motion precision",
    38: "Measure motion accuracy",
    39: "Nozzle offset calibration",
    40: "High temperature auto bed leveling",
    41: "Auto Check: Quick Release Lever",
    42: "Auto Check: Door and Upper Cover",
    43: "Laser Calibration",
    44: "Auto Check: Platform",
    45: "Confirming BirdsEye Camera location",
    46: "Calibrating BirdsEye Camera",
    47: "Auto bed leveling - phase 1",
    48: "Auto bed leveling - phase 2",
    49: "Heating chamber",
    50: "Cooling heatbed",
    51: "Printing calibration lines",
    52: "Auto Check: Material",
    53: "Live View Camera Calibration",
    54: "Waiting for heatbed temperature",
    55: "Auto Check: Material Position",
    56: "Cutting Module Offset Calibration",
    57: "Measuring Surface",
    58: "Thermal Preconditioning",
    59: "Homing Blade Holder",
    60: "Calibrating Camera Offset",
    61: "Calibrating Blade Holder Position",
    62: "Hotend Pick and Place Test",
    63: "Waiting for Chamber temperature",
    64: "Preparing Hotend",
    65: "Calibrating nozzle clumping detection",
    66: "Purifying the chamber air",
    74: "Preparing",  # Seen on H2D during print preparation
    77: "Preparing AMS",
}


def get_stage_name(stage: int) -> str:
    """Get human-readable stage name from stage number."""
    return STAGE_NAMES.get(stage, f"Unknown stage ({stage})")
