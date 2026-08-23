#!/bin/sh
# PrintOps container entrypoint.
#
# Runs as root (the image leaves USER unset, so containers start as
# root by default), chowns /app/data and /app/logs to PUID:PGID, then
# drops to PUID:PGID via gosu and execs the application. This fixes the
# class of "Permission denied" errors that bit users when:
#
#   - a Docker named volume was first created with root ownership and
#     the container was running with `user: 1000:1000` (named volumes
#     created by the daemon take its ownership; Dockerfile chmod hacks
#     cover the parent path but not subdirs created at runtime).
#   - a bind-mount source path didn't exist on the host yet, so dockerd
#     created it as root before the container started, leaving it
#     unwritable by uid 1000 inside the container — see #1211 / #668
#     for the virtual_printer bind-mount case the shipped compose
#     template ships uncommented.
#
# If the container is started with an explicit `user:` directive
# (compose `user:` or `docker run --user`), the entrypoint runs as that
# user instead of root and chown isn't possible. The script falls
# through to direct exec without modifying ownership — preserving the
# previous behavior for users who pin a specific uid via compose.

set -eu

fatal() {
    echo "[entrypoint] error: $*" >&2
    exit 1
}

validate_id() {
    name="$1"
    value="$2"
    case "$value" in
        ''|*[!0-9]*)
            fatal "${name} must be a decimal integer from 1 to 2147483647"
            ;;
    esac
    if [ "$value" -lt 1 ] || [ "$value" -gt 2147483647 ]; then
        fatal "${name} must be a decimal integer from 1 to 2147483647"
    fi
}

# Default to 1000:1000 to match the legacy `user: "1000:1000"` default
# in our previously-shipped compose template; overridable via env so
# users who run docker as a different uid can match their host without
# editing the compose user: directive.
PUID="${PUID-1000}"
PGID="${PGID-1000}"
validate_id PUID "$PUID"
validate_id PGID "$PGID"
echo "[entrypoint] target identity ${PUID}:${PGID} validated"

# go2rtc restreaming sidecar (camera live-view backend, see
# backend/app/services/go2rtc_client.py). Started as a background process
# rather than exec'd, because this script also needs to launch the main
# app — see the supervisor block near the bottom of this file for why we
# gave up the previous single-process `exec` model.
#
# Streams are managed at runtime through go2rtc's REST API, so the static
# config here only sets up loopback-only listeners; it never lists
# `streams:` entries on purpose.
#
# go2rtc itself, however, persists every runtime PUT /api/streams
# registration back into this file (its PatchConfig mechanism) so it can
# reload streams after its own restart. PrintOps's streams are the
# opposite of that: every registration is tied to a local proxy port or
# bridge process (create_tls_proxy, chamber_image_bridge) that is
# per-process and random — it cannot possibly still be valid after go2rtc
# itself restarts. Reloading a stale entry then means go2rtc dials a dead
# port forever until something re-registers the stream under the exact
# same name, which may never happen (#camera Phase D regression: this bit
# every printer after the first container restart following any viewer
# session). So the config is regenerated from scratch on *every* startup,
# not just the first — any streams: section from a previous run is
# deliberately discarded here, not preserved.
GO2RTC_BIN="/usr/local/bin/go2rtc"
GO2RTC_CONFIG_DIR="/app/data/go2rtc"
GO2RTC_PID=""

start_go2rtc() {
    if [ ! -x "$GO2RTC_BIN" ]; then
        echo "[entrypoint] go2rtc binary not found at ${GO2RTC_BIN}; camera live view will be unavailable" >&2
        return
    fi

    mkdir -p "$GO2RTC_CONFIG_DIR" 2>/dev/null || true
    if [ ! -d "$GO2RTC_CONFIG_DIR" ] || [ ! -w "$GO2RTC_CONFIG_DIR" ]; then
        # Can happen when the container is started already non-root (no
        # chown pass ran — see the header comment) against a data volume
        # not already owned by that uid. Camera live view degrades rather
        # than taking the whole entrypoint down with it under `set -e`.
        echo "[entrypoint] cannot write ${GO2RTC_CONFIG_DIR}; camera live view will be unavailable" >&2
        return
    fi

    cat > "${GO2RTC_CONFIG_DIR}/go2rtc.yaml" <<-'EOF'
		# Managed by PrintOps and regenerated on every container start — do
		# not add a "streams:" section here, it would be silently discarded.
		# Camera streams are registered and removed at runtime via go2rtc's
		# REST API (see backend/app/services/go2rtc_client.py). All listeners
		# are loopback-only: go2rtc has no authentication of its own, and
		# PrintOps's token-gated HTTP/WS routes (and, if HA RTSP passthrough
		# is enabled, backend/app/services/rtsp_auth_proxy.py) are the only
		# sanctioned way to reach it. RTSP is on a non-standard port
		# (18554, not 8554) specifically so it's never mistaken for a
		# directly-reachable, unauthenticated RTSP server — the passthrough
		# proxy is the only thing allowed to dial it, and it does so
		# explicitly by this port number, kept in sync in that module.
		api:
		  listen: "127.0.0.1:1984"
		rtsp:
		  listen: "127.0.0.1:18554"
		webrtc:
		  listen: "127.0.0.1:8555"
		EOF

    if [ "$(id -u)" -eq 0 ]; then
        chown -R -h -- "${PUID}:${PGID}" "$GO2RTC_CONFIG_DIR" 2>/dev/null || true
        gosu "${PUID}:${PGID}" "$GO2RTC_BIN" -config "${GO2RTC_CONFIG_DIR}/go2rtc.yaml" &
    else
        "$GO2RTC_BIN" -config "${GO2RTC_CONFIG_DIR}/go2rtc.yaml" &
    fi
    GO2RTC_PID=$!
    echo "[entrypoint] go2rtc started (pid ${GO2RTC_PID})"
}

# Supervise the main app (and go2rtc) instead of exec'ing directly, so a
# SIGTERM/SIGINT from Docker can be forwarded to both children before this
# script exits. This intentionally stays a plain trap+wait loop rather than
# pulling in a real init system (s6, supervisord, tini): two long-running
# children is the simplest case that still needs *some* supervision, and
# this script already ran as PID 1 with full signal responsibility before
# go2rtc existed.
run_supervised() {
    if [ "$(id -u)" -ne 0 ]; then
        "$@" &
    else
        gosu "${PUID}:${PGID}" "$@" &
    fi
    app_pid=$!

    term_handler() {
        echo "[entrypoint] shutting down"
        if [ -n "$GO2RTC_PID" ]; then
            kill -TERM "$GO2RTC_PID" 2>/dev/null || true
        fi
        kill -TERM "$app_pid" 2>/dev/null || true
        wait "$app_pid" 2>/dev/null || true
        if [ -n "$GO2RTC_PID" ]; then
            wait "$GO2RTC_PID" 2>/dev/null || true
        fi
        exit 0
    }
    trap term_handler TERM INT

    # Not `wait "$app_pid"; app_exit=$?` — under `set -e`, a nonzero wait
    # (e.g. the app was killed by a signal) would abort the script on that
    # line, skipping app_exit=$? and the go2rtc cleanup below entirely.
    if wait "$app_pid"; then
        app_exit=0
    else
        app_exit=$?
    fi
    if [ -n "$GO2RTC_PID" ]; then
        kill -TERM "$GO2RTC_PID" 2>/dev/null || true
        wait "$GO2RTC_PID" 2>/dev/null || true
    fi
    exit "$app_exit"
}

if [ "$(id -u)" -eq 0 ]; then
    # Root-only stage: update the trust store and normalize volume
    # ownership, then re-exec fully into the unprivileged identity below —
    # never fall through to start_go2rtc/run_supervised while still root.
    #
    # A previous version of this script gosu'd go2rtc and the app
    # individually while staying root itself for the container's whole
    # lifetime, so it could supervise both and forward signals. That broke
    # tests/docker/assert-running-container.sh's "no root process for the
    # container's lifetime" guarantee, which inspects /proc/1 directly. So
    # instead, root does its setup work and then execs `gosu` into a
    # second invocation of this very script — that invocation becomes PID
    # 1, already unprivileged (id -u is non-zero the moment it starts), and
    # falls through to the same start_go2rtc + run_supervised call below
    # that a container started non-root to begin with also reaches.

    # If requested, update and use the system trust store inside the container.
    # Users can set USE_SYSTEM_TRUST_STORE to any non-empty value to enable.
    if [ -n "${USE_SYSTEM_TRUST_STORE:-}" ]; then
        echo "[entrypoint] USE_SYSTEM_TRUST_STORE is set"
        # Check if we have any certificates to process. Error if directory is empty
        if ls -1 /usr/local/share/ca-certificates/*.crt >/dev/null 2>&1; then
            echo "[entrypoint] .crt files found in /usr/local/share/ca-certificates"
        else
            fatal "no .crt files in /usr/local/share/ca-certificates"
        fi
        if command -v update-ca-certificates >/dev/null 2>&1; then
            echo "[entrypoint] update-ca-certificates found; updating system trust store"
            if update-ca-certificates --fresh ; then
                echo "[entrypoint] update-ca-certificates succeeded; exporting SSL_CERT_DIR=/etc/ssl/certs"
                export SSL_CERT_DIR="/etc/ssl/certs"
            else
                fatal "update-ca-certificates failed"
            fi
        else
            fatal "update-ca-certificates not found; cannot update trust store"
        fi
    else
        echo "[entrypoint] USE_SYSTEM_TRUST_STORE not set; skipping system trust store update"
    fi

    # `chown -R` is gated behind a top-level ownership check so a correctly-
    # owned directory isn't traversed on every container start. A user with
    # a multi-GB archive directory would otherwise pay seconds-to-minutes
    # of chown traversal at every restart.
    chown_if_needed() {
        target="$1"
        [ -d "$target" ] || mkdir -p -- "$target" || fatal "cannot create ${target}"
        current="$(stat -c '%u:%g' "$target" 2>/dev/null || echo '')"
        if [ "$current" != "$PUID:$PGID" ]; then
            echo "[entrypoint] normalizing ownership of ${target} to ${PUID}:${PGID}"
            chown -R -h -- "${PUID}:${PGID}" "$target" \
                || fatal "cannot set ownership of ${target}; check the mount and PUID/PGID"
        fi
    }

    chown_if_needed /app/data
    # A nested bind mount has its own ownership. The parent can already match
    # PUID:PGID while Docker has created this mount point as root, so it needs an
    # independent check. Ignore symlinks: ownership normalization must never
    # traverse outside the managed data tree.
    if [ -d /app/data/virtual_printer ] && [ ! -L /app/data/virtual_printer ]; then
        chown_if_needed /app/data/virtual_printer
    fi
    chown_if_needed /app/logs

    # Drop privileges by exec'ing back into this script under gosu. python's
    # file capabilities (cap_net_bind_service=+ep, set in the Dockerfile)
    # survive the uid switch, so binding to :322 / :990 still works post-drop.
    echo "[entrypoint] starting application as ${PUID}:${PGID}"
    exec gosu "${PUID}:${PGID}" "$0" "$@"
fi

# Reached either because the container was started non-root to begin with
# (no chown was possible or needed — see header comment) or because root
# just re-exec'd into this same script via gosu above. Either way, this is
# the final, already-unprivileged PID 1.
start_go2rtc
run_supervised "$@"
