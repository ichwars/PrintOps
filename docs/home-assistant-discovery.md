# Home Assistant MQTT discovery

With **Home Assistant discovery** enabled, the MQTT relay tells Home Assistant
how to read what it already publishes. Each printer shows up in Home Assistant
as a device with its sensors and event entities — no YAML, no manual MQTT
sensors. This complements the HACS integration
([ha-printops](https://github.com/xeonixo/ha-printops)), which polls the REST
API instead; the two can be used side by side.

It is read-only: Home Assistant can show the printer's state and react to its
events, but cannot control the printer through discovery.

## Requirements

- The MQTT relay is set up and connected (Settings → Network → MQTT Publishing).
- Home Assistant's MQTT integration is connected to the **same broker**.
- MQTT discovery is on in Home Assistant (default: Settings → Devices &
  services → MQTT → Configure).

## Turning it on

1. Settings → Network → **MQTT Publishing**.
2. Enable MQTT publishing and connect.
3. Turn on **Home Assistant Discovery**.
4. Leave the **Discovery prefix** at `homeassistant` unless you changed it in
   Home Assistant.

| Setting | Description | Default |
| --- | --- | --- |
| Home Assistant discovery | Publish one device discovery message per printer | Off |
| Discovery prefix | Prefix Home Assistant listens on for discovery | `homeassistant` |

The discovery prefix must differ from the topic prefix and must not contain
`+` or `#`; the settings save rejects invalid combinations. Run only one
PrintOps instance per topic prefix on a broker — two instances would retract
each other's devices.

## What appears in Home Assistant

Each printer becomes a device (manufacturer Bambu Lab, model, serial, firmware;
links to the external URL if set). Entities read the existing retained status
topic `printops/printers/{serial}/status` and are available only while the
relay is online and the printer is connected.

Sensors: state, stage, progress, remaining time, current print, layer, nozzle /
nozzle target / bed / bed target / chamber temperature, WiFi signal (disabled
by default), cooling/aux/chamber/heatbreak fan (aux and heatbreak disabled by
default).

Binary sensors: online, chamber light.

Event entities: print started / completed / failed, printer error,
filament low (state topics `printops/printers/{serial}/print/...`,
`.../error`, `.../filament/low`).

## Lifecycle

- A printer is announced after it connects and sends its first status.
- Devices are re-announced when the broker reconnects and when Home Assistant
  sends its birth message (`homeassistant/status` = `online`); configs are
  retained, so HA also finds them after its own restart.
- Deleting a printer, disabling discovery, disabling MQTT, or changing either
  prefix retracts the devices (empty retained config). If the broker is
  unreachable at that moment, the removal is queued and executed once the
  broker is reachable again, including after a restart.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| No device appears | Relay shows connected; HA MQTT integration uses the same broker; discovery prefix matches; printer has reported at least one status |
| `mosquitto_sub -t "homeassistant/device/#" -v` shows nothing | Discovery is off, or discovery prefix == topic prefix (rejected at save) |
| Device stays after removal | Delete it in HA (Settings → Devices & services → MQTT) or clear the retained config on the broker |
| All entities unavailable | PrintOps or the printer is offline — see the availability rules above |
