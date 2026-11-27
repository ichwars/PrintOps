# Capability Map: Home Assistant Integration (PrintOps → HA)

Status: mqtt-discovery + ha-entity-model (printer device) implemented; AMS sub-devices and energy/queue sensors deferred to V2 — model the entity set on the Bambu Lab HA
integration / Bambuddy upstream discovery (one device per printer, one per
AMS unit, familiar entity names), and exceed it with PrintOps-only data
(queue, energy, maintenance, multi-printer aggregation).

| Module id       | Responsibility                                                                 | Depends on            |
|-----------------|--------------------------------------------------------------------------------|-----------------------|
| mqtt-discovery  | HA device-discovery config topics, lifecycle (announce/remove/re-announce), settings + validation | mqtt-relay (existing) |
| ha-entity-model | Which PrintOps data becomes which HA entity (sensor/binary_sensor/event/device trigger), topic + payload contract | mqtt-discovery        |
| rest-webhook    | Docs + examples for REST API (scoped API keys) and webhook triggers in HA (existing, docs only) | —                     |
| hacs-integration| Optional HACS custom integration (separate repo) on top of the REST API       | ha-entity-model, rest-webhook |
| ha-docs         | Setup guide, example dashboard, automation recipes, troubleshooting           | all                   |

Build order: mqtt-discovery → ha-entity-model → rest-webhook → ha-docs →
hacs-integration (optional, V2).

Reference: Bambuddy upstream "Home Assistant Discovery"
(https://wiki.bambuddy.cool/features/home-assistant-discovery/) and the
ha-bambulab HACS integration entity naming.
