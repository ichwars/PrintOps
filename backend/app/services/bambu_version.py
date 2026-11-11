"""Printer and AMS version metadata, independent of frame arrival order."""

import logging

from backend.app.services.drying_telemetry import observe_version_info

logger = logging.getLogger("backend.app.services.bambu_mqtt")
_AMS_MODULE_PREFIXES = ("ams/", "ams_f1/", "n3f/", "n3s/")


class BambuVersionMixin:
    def _handle_version_info(self, data: dict):
        """Handle version info response from get_version command.

        Parses firmware version from the 'ota' module in the module list.
        Also extracts AMS unit firmware versions from AMS modules and stores
        them on the corresponding AMS unit in raw_data so the status route can
        expose them to the frontend.

        AMS module naming conventions (numeric suffix is the AMS unit ID):
        - ``ams/<id>``  – original AMS
        - ``n3f/<id>``  – AMS 2 Pro (H2D Pro and similar)
        - ``n3s/<id>``  – AMS HT (H2D Pro and similar)

        Message format:
        {
            "command": "get_version",
            "module": [
                {"name": "ota", "sw_ver": "01.08.05.00"},
                {"name": "rv1126", "sw_ver": "00.00.14.74"},
                {"name": "ams/0", "sw_ver": "00.00.06.96", "sn": "ABC123"},
                {"name": "n3f/0", "sw_ver": "03.00.21.29", "sn": "19C06A552504488"},
                {"name": "n3s/128", "sw_ver": "03.00.21.29", "sn": "19F06A561801096"},
                ...
            ]
        }
        """
        from backend.app.services.bambu_mqtt import normalize_am_unit_id

        observe_version_info(self.state, data)
        modules = data.get("module", [])
        if not isinstance(modules, list):
            return

        state_changed = False
        for module in modules:
            if not isinstance(module, dict):
                continue
            if module.get("name") == "ota":
                version = module.get("sw_ver")
                if version:
                    old_version = self.state.firmware_version
                    self.state.firmware_version = version
                    if old_version != version:
                        logger.info("[%s] Firmware version: %s", self.serial_number, version)
                    state_changed = True
                break

        # Extract AMS unit firmware versions from AMS modules.
        # See module-level _AMS_MODULE_PREFIXES for supported naming conventions.
        # Always cache regardless of whether AMS data has arrived yet — get_version
        # often arrives before the first push_status, so caching must be unconditional.
        ams_raw = self.state.raw_data.get("ams")
        for module in modules:
            if not isinstance(module, dict):
                continue
            name = module.get("name", "")
            if not isinstance(name, str) or not any(name.startswith(prefix) for prefix in _AMS_MODULE_PREFIXES):
                continue
            try:
                ams_id = normalize_am_unit_id(int(name.split("/", 1)[1]))
            except (ValueError, IndexError):
                continue
            sw_ver = module.get("sw_ver", "")
            sn = module.get("sn", "")

            # Extract module type from prefix (e.g. "ams/0" → "ams", "n3f/0" → "n3f")
            module_type = name.split("/", 1)[0]

            # Always cache so _apply_ams_version_cache can apply it when AMS data arrives
            if sw_ver or sn or module_type:
                self._ams_version_cache[ams_id] = {"sw_ver": sw_ver, "sn": sn, "module_type": module_type}
                state_changed = True

            # Also directly update any AMS unit already present in raw_data
            if ams_raw and isinstance(ams_raw, list):
                for ams_unit in ams_raw:
                    if not isinstance(ams_unit, dict):
                        continue
                    try:
                        unit_id = int(ams_unit.get("id")) if ams_unit.get("id") is not None else None
                    except (ValueError, TypeError):
                        unit_id = None
                    if unit_id == ams_id:
                        if sw_ver:
                            ams_unit["sw_ver"] = sw_ver
                            logger.debug("[%s] AMS %s firmware: %s", self.serial_number, ams_id, sw_ver)
                        # Only set sn from version info if not already present in AMS data
                        if sn and not ams_unit.get("sn"):
                            ams_unit["sn"] = sn
                        if module_type:
                            ams_unit["module_type"] = module_type
                        break

        # Trigger state change callback AFTER both loops so AMS sn/sw_ver are
        # included in the broadcast (not just the printer firmware version).
        if state_changed and self.on_state_change:
            self.on_state_change(self.state)

        # Warn if any AMS unit is still missing serial number or firmware version
        # after processing the version info response. Warn only once per connection
        # to avoid repeated noise on older firmware that doesn't report these fields.
        if ams_raw and isinstance(ams_raw, list):
            for ams_unit in ams_raw:
                if not isinstance(ams_unit, dict):
                    continue
                ams_id = ams_unit.get("id", "?")
                if not ams_unit.get("sn") and not ams_unit.get("serial_number"):
                    key = (ams_id, "sn")
                    if key not in self._ams_version_warned:
                        self._ams_version_warned.add(key)
                        logger.warning(
                            "[%s] AMS unit %s: serial number not available in version info",
                            self.serial_number,
                            ams_id,
                        )
                if not ams_unit.get("sw_ver"):
                    key = (ams_id, "sw_ver")
                    if key not in self._ams_version_warned:
                        self._ams_version_warned.add(key)
                        logger.warning(
                            "[%s] AMS unit %s: firmware version not available in version info",
                            self.serial_number,
                            ams_id,
                        )

    def _apply_ams_version_cache(self, ams_list: list) -> None:
        """Apply cached AMS firmware/SN (from get_version) onto an AMS list in-place.

        get_version may arrive before pushall/AMS status, and AMS unit IDs may be
        strings in MQTT payloads. This helper normalizes IDs and fills missing
        sw_ver/sn fields without overwriting values already present.
        """
        if not ams_list or not isinstance(ams_list, list):
            return
        cache = self._ams_version_cache
        if not cache:
            return
        for unit in ams_list:
            if not isinstance(unit, dict):
                continue
            raw_id = unit.get("id")
            try:
                unit_id = int(raw_id) if raw_id is not None else None
            except (ValueError, TypeError):
                unit_id = None
            if unit_id is None:
                continue
            cached = cache.get(unit_id)
            if not cached:
                continue
            sw_ver = cached.get("sw_ver") or ""
            sn = cached.get("sn") or ""
            if sw_ver and not unit.get("sw_ver"):
                unit["sw_ver"] = sw_ver
            # Only set sn if not already present in AMS data
            if sn and not unit.get("sn") and not unit.get("serial_number"):
                unit["sn"] = sn
            module_type = cached.get("module_type") or ""
            if module_type and not unit.get("module_type"):
                unit["module_type"] = module_type
