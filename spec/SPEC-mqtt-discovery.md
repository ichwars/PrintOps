# Spec: mqtt-discovery — V1

## Objective
Add an optional Home Assistant MQTT discovery layer to the existing MQTT
relay, so HA creates one device per printer (and per AMS unit) automatically —
no YAML, no manual MQTT sensors. Discovery is announced only while the relay
is enabled and connected; devices are removed again when discovery, MQTT, or
the printer goes away. Entity content is specified separately in
`SPEC-ha-entity-model.md`; this module owns the mechanism.

## Tech Stack
- Backend: Python 3.12, FastAPI, paho-mqtt (already used by
  `backend/app/services/mqtt_relay.py`). No new dependencies.
- Discovery format: HA **device discovery** — one retained config message per
  device at `{discovery_prefix}/device/printops_{serial}/config` with a
  `device` block and an `entities` array referencing the relay's existing
  state/event topics (same mechanism as Bambuddy upstream, HA ≥ 2023.7).
- Frontend: React + TypeScript settings UI (Settings → Network → MQTT
  Publishing), i18n keys in all locales.

## Commands
- Backend checks: `./test_backend.sh` (ruff + basedpyright + pytest)
- Targeted tests: `venv/bin/python3 -m pytest backend/tests -k mqtt -q`
- Frontend checks: `cd frontend && npm run test:run` (vitest + i18n + mocker security)
- Lint: `venv/bin/python3 -m ruff check backend/`, `cd frontend && npm run lint`

## Project Structure
```
backend/app/services/mqtt_discovery.py   → new: discovery publisher (announce/remove/re-announce)
backend/app/services/mqtt_relay.py       → hook discovery into connect/disconnect/printer add/remove/shutdown
backend/app/schemas/settings.py          → new settings keys (below)
backend/app/api/routes/settings.py       → validation: discovery prefix ≠ topic prefix, no wildcards
frontend/src/pages/SettingsPage.tsx      → toggle + discovery prefix field in MQTT card
frontend/src/i18n/locales/*.ts           → new keys in every locale
backend/tests/test_mqtt_discovery.py     → new tests
frontend/src/__tests__/...               → settings UI tests
docs/home-assistant-discovery.md         → user docs
spec/SPEC-ha-entity-model.md             → entity content contract
```

## Settings (new keys in settings schema)
- `ha_discovery_enabled: bool = false`
- `ha_discovery_prefix: str = "homeassistant"`

Validation (settings save + backup restore):
- prefix normalized without leading/trailing slashes; must differ from
  `mqtt_topic_prefix` while discovery is on (error message shown in UI);
  a restored backup with both equal keeps discovery off
- prefix must not contain `+` or `#`
- discovery requires `mqtt_enabled` and a configured broker

## Code Style
Follow `mqtt_relay.py`: module-level logger, async methods returning bool,
`_publish(topic, payload, retain)` for all broker writes, paho client retired
via `retire_paho_client`. Type hints everywhere (basedpyright strict).

## Behavior (mechanism only)
1. **Announce**: after a printer connects and sends its first status, publish
   one retained device-discovery message per printer and per AMS unit
   (`printops_{serial}`, `printops_{serial}_ams_{id}`, AMS linked via
   `via_device`). Re-announce all devices when the broker connection is
   (re)established and when HA's birth message (`{discovery_prefix}/status` =
   `online`) is received.
2. **Availability**: entities carry availability rules — relay online
   (`{topic_prefix}/status` = `online`, LWT `offline`) AND printer connected.
   Printer offline → all its entities unavailable except an `online`
   binary sensor that reports the printer disconnected.
3. **Removal**: publish empty retained payloads to all own config topics when:
   discovery toggled off, MQTT publishing disabled, topic or discovery prefix
   changed, printer deleted, or on clean shutdown. If the broker is
   unreachable, queue the removal and execute it when the broker is reachable
   again (including after a restart).
4. **Constraints**: discovery messages reference only existing relay topics —
   the relay's topic schema does not change in this module. Document: run only
   one PrintOps instance per topic prefix on a broker.

## Testing Strategy
- `backend/tests/test_mqtt_discovery.py`: fake paho client; assert config
  topics/payloads (device block, entities reference, retain), announce on
  first status, re-announce on birth message/reconnect, removal on
  toggle/prefix change/printer delete/shutdown, deferred removal when broker
  down, prefix validation rules, restore-keeps-off rule.
- Settings route tests for validation; frontend vitest for the new toggle and
  i18n completeness (`check:i18n`).
- Manual check: `mosquitto_sub -t "homeassistant/device/#" -v` shows configs
  after printer connects; HA (Settings → Devices & Services → MQTT) lists the
  devices.

## Boundaries
- Always: keep existing relay topics/payloads byte-compatible; run
  `./test_backend.sh` and frontend `test:run` before commit; i18n keys in all
  locales.
- Ask first: adding settings keys to the backup/restore category list;
  any change to existing topic payloads.
- Never: publish discovery when prefix == topic prefix; remove devices
  belonging to another instance/prefix; commit credentials.

## Success Criteria
- With relay connected and discovery on, `mosquitto_sub` shows retained
  `homeassistant/device/printops_*/config` messages and HA auto-creates the
  devices with available entities after a printer's first status.
- Toggling discovery off, deleting a printer, or changing prefixes removes
  the devices (empty retained configs), even after a restart in between.
- Prefix validation rejects `homeassistant` == topic prefix and wildcards.
- Full backend suite and frontend suite green; ruff/basedpyright clean.

## Out of Scope (Deferred)
- Entity content beyond referencing existing topics (→ SPEC-ha-entity-model).
- New relay topics (queue state, energy) — allowed only via ha-entity-model.
- Camera entity, printer control (pause/stop/light) from HA — V2 via REST API
  or HACS integration.
- HACS custom integration — separate repo, V2.

## Open Questions
1. Device discovery (one message per device, Bambuddy-style) vs. classic
   per-entity discovery (`homeassistant/sensor/.../config`, ha-bambulab-style)
   — I propose device discovery; confirm?
2. Should `manufacturer` in `device` be "Bambu Lab" (printers are Bambu) or
   "PrintOps"? Proposal: Bambu Lab with `via_device`-style attribution to
   PrintOps in the device name.
3. Keep discovery read-only in V1 (like Bambuddy) — confirm?
