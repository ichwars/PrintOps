#!/bin/sh
# PrintOps container entrypoint.
#
# The application starts under Docker's non-root identity. Compose uses a
# separate, short-lived container for ownership repair on managed volumes.
#
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
    if ! [ "$value" -ge 1 ] || ! [ "$value" -le 2147483647 ]; then
        fatal "${name} must be a decimal integer from 1 to 2147483647"
    fi
}

uid="$(id -u)"
gid="$(id -g)"
PUID="${PUID-$uid}"
PGID="${PGID-$gid}"
validate_id PUID "$PUID"
validate_id PGID "$PGID"
[ "$uid" -ne 0 ] && [ "$gid" -ne 0 ] || fatal "the application requires a non-root user and group"
[ "$uid" -eq "$PUID" ] && [ "$gid" -eq "$PGID" ] \
    || fatal "run the container as $PUID:$PGID to match PUID/PGID"
for target in /app/data /app/logs; do
    [ -d "$target" ] && [ -w "$target" ] && [ -x "$target" ] \
        || fatal "$target is not writable by $uid:$gid; prepare the volume or fix the bind mount"
done

if [ -n "${USE_SYSTEM_TRUST_STORE:-}" ]; then
    if ! find /usr/local/share/ca-certificates -name '*.crt' -type f -print -quit | grep -q .; then
        fatal "no .crt files in /usr/local/share/ca-certificates"
    fi
    find /usr/local/share/ca-certificates -name '*.crt' -type f -exec sh -c '
        for certificate do
            openssl x509 -in "$certificate" -noout || exit 1
        done
    ' sh {} + || fatal "invalid CA certificate"
    trust_dir="$(mktemp -d /tmp/printops-trust.XXXXXXXX)" || fatal "cannot create a certificate store"
    trap 'rm -rf -- "$trust_dir"' EXIT
    # Build a writable copy of the Debian trust store without changing /etc
    # or running system-package hooks. Retain the distribution's default CAs.
    update-ca-certificates --etccertsdir "$trust_dir" --hooksdir "$trust_dir/no-hooks" \
        || fatal "cannot build the certificate store"
    SSL_CERT_DIR="$trust_dir"
    SSL_CERT_FILE="$trust_dir/ca-certificates.crt"
    [ -s "$SSL_CERT_FILE" ] || fatal "certificate store has no CA bundle"
    export SSL_CERT_DIR SSL_CERT_FILE
    export CURL_CA_BUNDLE="${CURL_CA_BUNDLE-$SSL_CERT_FILE}"
    export REQUESTS_CA_BUNDLE="${REQUESTS_CA_BUNDLE-$SSL_CERT_FILE}"
fi

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
        # Camera live view degrades when its config directory is unwritable.
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

    "$GO2RTC_BIN" -config "${GO2RTC_CONFIG_DIR}/go2rtc.yaml" &
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
    "$@" &
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

start_go2rtc
run_supervised "$@"
