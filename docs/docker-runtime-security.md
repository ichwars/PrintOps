# Docker runtime security

The production image starts as UID/GID `1000:1000`. With the supplied Compose
file, `PUID` and `PGID` select the application identity and the owner of the
managed storage. Both values must be decimal integers from 1 through 2147483647.

## Startup and privileges

1. The one-shot `printops-init` service prepares `/app/data`, `/app/logs` and
   the optional `/app/data/virtual_printer` bind mount. It has no network,
   a read-only root filesystem and only `CHOWN` and `DAC_OVERRIDE`. It repairs
   ownership only when a directory has a different owner. Symlinks are never
   followed by the ownership repair.
2. Compose starts `printops` after successful volume initialization. Docker
   starts its entrypoint, the application, go2rtc and the health probe under
   the selected non-root identity. The application has only `NET_BIND_SERVICE`
   to bind virtual-printer ports 322 and 990.
3. When `USE_SYSTEM_TRUST_STORE` is set, the entrypoint combines Debian's
   default CAs with the PEM `*.crt` certificates mounted read-only at
   `/usr/local/share/ca-certificates`. It builds a temporary trust store for
   application processes. Python TLS clients load the bundle explicitly, including
   when file capabilities put OpenSSL in secure execution. Startup fails if
   the opt-in has no valid certificates.

## Upgrading or using a custom Compose file

Use the Compose example from the same PrintOps version as your image. Carry
over the two service definitions and preserve your existing volumes, image
tag, ports, environment and additional mounts. Set `PUID` and `PGID` in
`.env` to match your host user when using bind mounts. Add managed data,
logs and the optional native virtual-printer directory to both services.
Mount certificates, external library folders, backup destinations and sockets
only on `printops`. Prepare write permissions for any separate backup or
external upload mount on the host.

Stop the application before changing the owner of existing storage. Apply
the new Compose configuration with `docker compose up -d`. If the application
reports unwritable data or logs, check the initializer with
`docker compose logs printops-init`.

## Direct Docker runs

Fresh named volumes work with the image's default identity. For existing
volumes or bind mounts, ensure that the selected user owns the data and logs
before starting the container. To choose another identity, use
`docker run --user UID:GID` and use matching values if also setting `PUID`
or `PGID`. Mount optional CA certificates as described above.
