"""Incremental fan and accessory fields from Bambu MQTT printer reports."""


def update_fan_fields(self, data, logger) -> None:
    # Fan speeds (MQTT sends as string "0"-"15" representing speed levels, or percentage)
    # Convert to 0-100 percentage for display
    def parse_fan_speed(value: str | int | None) -> int | None:
        if value is None:
            return None
        try:
            speed = int(value)
            # MQTT reports 0-15 speed levels, convert to percentage (0-100)
            # 15 = 100%, so multiply by 100/15 ≈ 6.67
            if speed <= 15:
                return round(speed * 100 / 15)
            # If already a percentage (0-255 scale from some printers), convert
            elif speed <= 255:
                return round(speed * 100 / 255)
            return speed
        except (ValueError, TypeError):
            return None

    # Log fan fields once for debugging
    if not hasattr(self, "_fan_fields_logged"):
        fan_fields = {k: v for k, v in data.items() if "fan" in k.lower()}
        if fan_fields:
            logger.debug("[%s] Fan fields in MQTT data: %s", self.serial_number, fan_fields)
            self._fan_fields_logged = True

    if "cooling_fan_speed" in data:
        self.state.cooling_fan_speed = parse_fan_speed(data["cooling_fan_speed"])
    if "big_fan1_speed" in data:
        self.state.big_fan1_speed = parse_fan_speed(data["big_fan1_speed"])
    if "big_fan2_speed" in data:
        self.state.big_fan2_speed = parse_fan_speed(data["big_fan2_speed"])
    if "heatbreak_fan_speed" in data:
        self.state.heatbreak_fan_speed = parse_fan_speed(data["heatbreak_fan_speed"])


def update_hardware_fields(self, data, logger, FilaSwitchState) -> None:
    # Log vir_slot data (once) - this may contain per-extruder slot mapping for H2D
    if "vir_slot" in data and not hasattr(self, "_vir_slot_logged"):
        logger.debug("[%s] vir_slot data: %s", self.serial_number, data["vir_slot"])
        self._vir_slot_logged = True

    # Log nozzle hardware info fields (once)
    nozzle_fields = {
        k: v
        for k, v in data.items()
        if "nozzle" in k.lower() or "hw" in k.lower() or "extruder" in k.lower() or "upgrade" in k.lower()
    }
    if nozzle_fields and not hasattr(self, "_nozzle_fields_logged"):
        logger.debug("[%s] Nozzle/hardware fields in MQTT data: %s", self.serial_number, nozzle_fields)
        self._nozzle_fields_logged = True
    # Parse active extruder from device.extruder.state bit 8
    # bit 8 = 0 → RIGHT extruder (active_extruder=0)
    # bit 8 = 1 → LEFT extruder (active_extruder=1)
    if "device" in data and isinstance(data.get("device"), dict):
        device = data["device"]
        # One-shot identification probe: surface whatever the firmware uses to
        # name itself so an unknown model in a support bundle becomes self-
        # diagnosing. INFO level so it shows up without debug logging. Falls
        # back to dumping device.keys() if none of the known fields are present
        # (so a future Bambu rename like `model_name` is still observable).
        if not getattr(self, "_device_id_logged", False):
            id_fields = {
                k: device.get(k)
                for k in ("dev_model_name", "dev_product_name", "dev_id", "project_name")
                if k in device
            }
            if id_fields:
                logger.info("[%s] Device identification: %s", self.serial_number, id_fields)
            else:
                logger.info(
                    "[%s] Device identification: no known id fields; device.keys=%s",
                    self.serial_number,
                    sorted(device.keys()),
                )
            self._device_id_logged = True
        if "extruder" in device and "state" in device["extruder"]:
            state_val = device["extruder"]["state"]
            # Extract bit 8 for extruder position
            new_extruder = (state_val >> 8) & 0x1
            if new_extruder != self.state.active_extruder:
                logger.debug(
                    f"[{self.serial_number}] ACTIVE EXTRUDER CHANGED (state bit 8): {self.state.active_extruder} -> {new_extruder} (0=right, 1=left) [state={state_val}]"
                )
                self.state.active_extruder = new_extruder

    # Log device.extruder structure for active extruder
    if "device" in data and isinstance(data.get("device"), dict):
        device = data["device"]
        if "extruder" in device:
            ext_data = device["extruder"]
            # Log 'state' field - OrcaSlicer uses bits 12-14 for switch state
            if "state" in ext_data:
                state_val = ext_data["state"]
                # Extract bits 12-14 (3 bits) for switch state
                switch_state = (state_val >> 12) & 0x7
                logger.debug(
                    f"[{self.serial_number}] device.extruder.state={state_val} (switch_state bits 12-14: {switch_state})"
                )
            # Log 'cur' field if present (might indicate current/active extruder)
            if "cur" in ext_data:
                logger.debug("[%s] device.extruder.cur: %s", self.serial_number, ext_data["cur"])

    # Filament Track Switch (FTS) detection — #1162. Presence of
    # device.fila_switch in MQTT means the FTS accessory is installed.
    if "device" in data and isinstance(data.get("device"), dict):
        fs_data = data["device"].get("fila_switch")
        if isinstance(fs_data, dict):
            in_raw = fs_data.get("in")
            out_raw = fs_data.get("out")
            self.state.fila_switch = FilaSwitchState(
                installed=True,
                in_slots=list(in_raw) if isinstance(in_raw, list) else [],
                out_extruders=list(out_raw) if isinstance(out_raw, list) else [],
                stat=int(fs_data.get("stat", 0) or 0),
                info=int(fs_data.get("info", 0) or 0),
            )


def update_stage_fields(self, data, logger, get_stage_name) -> None:
    # Calibration stage tracking
    if "stg_cur" in data:
        new_stg = data["stg_cur"]
        prev_stg = self.state.stg_cur
        # Always log ANY stg_cur change for debugging filament operations
        if new_stg != prev_stg:
            logger.debug(f"[{self.serial_number}] stg_cur changed: {prev_stg} -> {new_stg} ({get_stage_name(new_stg)})")
        self.state.stg_cur = new_stg
        # #1721 end-of-print finish photo trigger.
        # Stage 22 = "Filament unloading" fires at end-of-print AND
        # during mid-print color swaps. The end-of-print gate
        # (progress>=99 / layer>=total / remaining<=0) disambiguates
        # — those signals only line up at the real end. Edge-only
        # (prev != 22) so the trigger fires once per stage entry.
        if (
            new_stg == 22
            and prev_stg != 22
            and self._was_running
            and not self._finish_photo_captured
            and self.on_finish_photo_moment
        ):
            progress = self.state.progress or 0.0
            layer_num = self.state.layer_num or 0
            total_layers = self.state.total_layers or 0
            remaining = self.state.remaining_time or 0
            is_end_of_print = progress >= 99 or (total_layers > 0 and layer_num >= total_layers) or remaining <= 0
            if is_end_of_print:
                self._finish_photo_captured = True
                logger.info(
                    f"[{self.serial_number}] FINISH PHOTO MOMENT (stage-22) — "
                    f"progress={progress}, layer={layer_num}/{total_layers}, "
                    f"remaining={remaining}min, timelapse_active={self._timelapse_during_print}"
                )
                self.on_finish_photo_moment(
                    {
                        "trigger": "stage_22",
                        "filename": self._previous_gcode_file or self.state.gcode_file,
                        "subtask_name": self.state.subtask_name,
                        "timelapse_was_active": self._timelapse_during_print,
                    }
                )
    if "stg" in data:
        self.state.stg = data["stg"] if isinstance(data["stg"], list) else []
