# Virtual Printers behind Docker bridge / NAT

A Virtual Printer can announce an address that belongs to the Docker host or
NAT gateway. In **Settings → Virtual Printer**, set **Advertised IPv4 address**
to the IPv4 address the slicer can reach. The setting is per Virtual Printer.
It controls SSDP `Location`, FTPS `PASV`, and the printer certificate's IP SAN.
Changing it restarts an enabled Virtual Printer and regenerates its certificate
under the existing shared Virtual Printer CA. The slicer still needs to trust
that CA and use the Virtual Printer's access code.

**Bind interface** must remain an interface inside the container (or a local
interface for native / host-network installations). The advertised address does
not create an interface, change listener bindings, open ports, or configure NAT.
It takes precedence over **Remote interface** for the address clients receive;
the remote interface still selects a local interface for proxy SSDP traffic.

Use a literal unicast IPv4 address, such as `192.168.1.40`. DNS names, IPv6,
addresses with ports, multicast, loopback, link-local, unspecified and reserved
addresses are rejected. PrintOps cannot validate whether a syntactically valid
address is reachable from every slicer, or identify a subnet's directed
broadcast address without the external network's subnet configuration.

Leaving the field empty restores the existing automatic behavior: server-mode
SSDP uses the selected remote interface, then the bind interface, then automatic
detection; FTPS uses the local control-connection address. The legacy
`VIRTUAL_PRINTER_PASV_ADDRESS` environment variable remains an FTPS-only fallback
when no per-printer override exists. Valid overrides take precedence over that
variable. Invalid fallback values are rejected at service construction; no
listener is opened with that configuration. Prefer the per-printer setting for
new bridge / NAT installations so discovery and upload agree.

## One Virtual Printer in bridge mode

This example assumes the Docker host's LAN address is `192.168.1.40`, the
container's fixed interface address is `172.30.0.2`, and the Virtual Printer's
database ID is **1**. Choose addresses and a bridge subnet appropriate for your
network. Save the following as `docker-compose.bridge-vp.yml` in the repository
root and run `docker compose -f docker-compose.bridge-vp.yml up -d --build`.

```yaml
services:
  printops:
    build: .
    restart: unless-stopped
    cap_drop: [ALL]
    cap_add: [CHOWN, DAC_OVERRIDE, SETGID, SETUID, NET_BIND_SERVICE]
    environment:
      PUID: "1000"
      PGID: "1000"
      TZ: Europe/Berlin
    volumes:
      - printops_data:/app/data
      - printops_logs:/app/logs
    ports:
      - "192.168.1.40:8000:8000"
      - "192.168.1.40:3000:3000"
      - "192.168.1.40:3002:3002"
      - "192.168.1.40:8883:8883"
      - "192.168.1.40:990:990"
      - "192.168.1.40:50000-50009:50000-50009"
      - "192.168.1.40:2021:2021/udp"
    networks:
      vp_bridge:
        ipv4_address: 172.30.0.2

networks:
  vp_bridge:
    ipam:
      config:
        - subnet: 172.30.0.0/24

volumes:
  printops_data:
  printops_logs:
```

Open `http://192.168.1.40:8000`, create an Archive, Review, or Queue Virtual
Printer, select `172.30.0.2` as its bind interface, and save `192.168.1.40` as
its advertised address. Set its access code, import the Virtual Printer CA into
the slicer, then enable it. Add it manually in the slicer using `192.168.1.40`
if discovery does not cross the bridge.

Published UDP port 2021 permits forwarded/unicast discovery traffic; publishing
it alone does **not** carry LAN broadcasts or multicast across Docker's bridge.
Automatic discovery requires a network path for SSDP, such as an appropriate
SSDP relay, macvlan, or host networking on Linux. The override corrects the
destination in announcements and replies that reach the slicer. It does not
provide an SSDP relay. With Linux host networking, choose a host-owned bind
interface; the override is usually unnecessary.

For VP ID 2, publish `50010-50019`; ID 3 uses `50020-50029`. The default is a
10-port slice per **database ID**, not creation order among remaining printers.
Check the passive range in the startup logs, especially if ports or slice sizes
are configured through environment variables. Preserve the advertised port
numbers on the host: `990:990` and identical passive ranges. A single host IPv4
address can serve one VP's fixed control ports. Multiple VPs need distinct
client-facing IP addresses, matching container bind interfaces and NAT mappings.

Proxy mode uses `50000-50100` for passive data and also needs its other forwarded
ports from the main [Compose configuration](../docker-compose.yml), including
file-transfer and camera ports when those features are used. FTPS data
listeners remain session-owned and peer-bound; the override does not make
permanent passive forwarders. Allow the required ports through the host
firewall only on the network where the slicer connects.

## Existing installation or another NAT gateway

If the container is already running, keep its existing bind interface and port
configuration. Set the advertised field to the reachable IPv4 of the Docker
host or gateway, and map MQTT, bind/detect, FTPS control and passive ports to the
same Virtual Printer with their original port numbers. Any gateway between the
slicer and Docker must preserve those mappings too.

The API accepts the same setting on creation and update. For example, updating
Virtual Printer ID 1 on an authenticated installation:

```bash
curl --fail-with-body -X PUT \
  -H "Authorization: Bearer ${PRINTOPS_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"advertised_ip":"192.168.1.40"}' \
  http://192.168.1.40:8000/api/v1/virtual-printers/1
```

Use a current authorized session token in `PRINTOPS_TOKEN`. Saving
`{"advertised_ip":null}` or `{"advertised_ip":""}` clears the override; omitting
the field during an update preserves it. Invalid input returns HTTP 422 without
modifying the printer. Read or list responses include `advertised_ip`.

To check a setup, confirm that discovery advertises the host/gateway address,
that authenticated FTPS `PASV` replies contain the same four IPv4 octets, and
that a small slicer upload completes. If login works but upload stalls, inspect
passive-port mappings and firewall rules. If discovery is absent but manual IP
connections work, inspect SSDP forwarding. Credentials and TLS settings are
independent of the address override.
