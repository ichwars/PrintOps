# Docker runtime security

PrintOps uses a short root initialization phase so named volumes and bind mounts
remain compatible with configurable host user IDs. The Python application does
not run as root.

## Startup sequence

1. Validate `PUID` and `PGID` as decimal values from 1 through 2147483647.
2. Normalize ownership of `/app/data` and `/app/logs` when required.
3. Optionally update the system trust store when `USE_SYSTEM_TRUST_STORE` is set.
4. Replace the init process with `gosu PUID:PGID` and `python -m uvicorn`.

Python becomes PID 1 and retains only `CAP_NET_BIND_SERVICE`, which is required
for the virtual-printer listeners on ports 322 and 990.

## Capability allowlist

The init phase receives only `CHOWN`, `DAC_OVERRIDE`, `SETGID`, `SETUID`, and
`NET_BIND_SERVICE`. PrintOps does not require privileged mode, the Docker
socket, host devices, `video` or `dialout` membership, `SYS_ADMIN`, `NET_ADMIN`,
or `NET_RAW`. Printers and camera streams are accessed over the network; FFmpeg
runs in userspace.

## Choosing PUID and PGID

The defaults are `1000:1000`. For bind mounts, use `id -u` and `id -g` on the
Docker host and set the matching values in `.env`. Values of 0 are rejected.

## Explicit Docker user mode

When `user:` or `docker run --user` starts the container as non-root, the
entrypoint cannot change volume ownership or the system trust store. Prepare
both on the host first. `USE_SYSTEM_TRUST_STORE` intentionally fails in this
mode rather than being ignored.

## Migration

Existing installations must update their Compose service as well as the image.
Keeping an older Compose file leaves Docker's broad default capability set in
place during initialization. Copy the current `cap_drop`/`cap_add` block from
`docker-compose.yml`, or apply this equivalent policy:

```yaml
cap_drop:
  - ALL
cap_add:
  - CHOWN
  - DAC_OVERRIDE
  - SETGID
  - SETUID
  - NET_BIND_SERVICE
```

Installations with `PUID=0` or `PGID=0` must also switch to a non-root host
identity before upgrading. If startup reports an ownership error, correct the
host mount permissions or select matching IDs; PrintOps will not continue with
unsafe permissions.
