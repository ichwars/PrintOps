# Spec: ha-entity-model — V1

## Objective
Define which PrintOps data is exposed to Home Assistant as which entity, with
topic and payload contract. Goal: feel like the Bambu Lab HA integration (one
printer device with state/progress/temperatures/fans/AMS slots, event
entities, device triggers) — and add what only PrintOps knows: queue state,
energy, maintenance, multi-printer overview. Depends on `SPEC-mqtt-discovery`
for the announcement mechanism.

## Tech Stack
Same as mqtt-discovery: paho-mqtt via `mqtt_relay.py`, device-discovery
entities referencing relay topics; new retained topics added to the relay
only where listed below. No new dependencies.

## Commands
- `./test_backend.sh`; targeted: `venv/bin/python3 -m pytest backend/tests -k "mqtt or ha_" -q`
- `cd frontend && npm run test:run`

## Project Structure
```
backend/app/services/mqtt_relay.py        → add retained topics: printers/{s}/queue, printers/{s}/energy, queue/state
backend/app/services/mqtt_discovery.py    → entity definitions (name, component, templates, device_class, unit, icon, enabled_by_default)
backend/app/services/ha_entity_model.py   → new: declarative entity catalog per printer/AMS + PrintOps extras
backend/tests/test_ha_entity_model.py     → new tests
docs/home-assistant-discovery.md          → entity reference for users
```

## Entity Set (V1)
Modeled on the Bambu/ha-bambulab + Bambuddy upstream entity tables. State is
read from the existing retained topic `printops/printers/{serial}/status`
(JSON) via `value_template`/`json_attributes_topic` — no schema change to it.

Printer device (`printops_{serial}`):
- Sensor: printer state (`idle`/`printing`/`paused`/`finished`/`failed`/`preparing`/`slicing`), stage, progress %, remaining time (min), end time (timestamp device class), WiFi signal
- Sensors (device_class temperature): nozzle, nozzle target, bed, bed target, chamber, chamber target, nozzle 2 + target on dual-nozzle models — model-gated like upstream (X1/X1C/X1E/X2D/P2S/H2C/H2D/H2S/H3C/P3C for chamber; door binary sensor where the model has one)
- Fan sensors: auxiliary, chamber, heatbreak — `enabled_by_default: false`
- Binary sensors: online, door (model-gated), chamber light
- Event entities + device triggers on existing event topics: print
  `started`/`completed`/`failed`, printer `error`, `filament_low`

AMS device per unit (`printops_{serial}_ams_{id}`, `via_device` printer):
- Sensors: humidity %, temperature °C (not AMS Lite), drying time remaining
  (AMS 2 Pro / AMS HT only)
- Slot sensors: state = filament type or `empty`; attributes `color`,
  `remaining`, `brand`, `name`

PrintOps-only additions ("a Stück besser"):
- Retained `printops/printers/{serial}/queue` (jobs pending/running for that
  printer) → sensors: queue length, current job name/progress
- Retained `printops/queue/state` (global) → sensor: total pending/running
- Retained `printops/printers/{serial}/energy` from smart-plug HA energy
  entities → sensor with `device_class: energy`, `state_class: total_increasing`
  (last_reset via timestamp of first reading)
- Event entity + trigger: maintenance alert (`printops/maintenance/alert`)
- Smart plugs: energy sensor per plug (from `printops/smart_plugs/energy`)

## Code Style
Declarative catalog: one Python dataclass per entity kind, built from printer
state + model registry (`backend/app/utils/printer_models.py`); discovery
module renders them into the device-discovery `entities` array. Templates as
Jinja2 strings, unit/device_class/state_class set explicitly.

## Testing Strategy
- Unit: catalog generation per printer model (chamber/door/nozzle-2 gating),
  AMS slot count per unit type, template rendering against sample status JSON.
- Relay tests: new retained topics published with correct payloads.
- Manual: HA shows all entities with correct values on a live printer; event
  entities fire on print start/complete.

## Boundaries
- Always: entity names/object_ids stable once shipped (HA entity_ids derive
  from them); keep existing topics unchanged; tests green.
- Ask first: adding new retained relay topics; exposing data that leaves the
  printer scope (API-key printer scopes must be respected for plug energy).
- Never: expose credentials or LAN URLs of other devices in attributes;
  change the status topic payload shape.

## Success Criteria
- HA device per printer shows the full entity set above with correct live
  values; AMS units appear as sub-devices; events fire device triggers.
- Queue/energy/maintenance entities appear and update.
- `./test_backend.sh` and frontend `test:run` green.

## Out of Scope (Deferred)
- Camera entity, pause/stop/light/speed control from HA (V2, via REST or HACS).
- HACS custom integration (separate repo, V2).
- Filament inventory / archive data in HA.

## Open Questions
1. Smart-plug switch (controllable) in V1 or V2? Proposal: V2 — V1 read-only
   like the Bambu reference.
2. Energy source: only smart-plug HA entities, or also printer-reported power?
   Proposal: both, printer power as additional sensor when available.
