#!/usr/bin/env bash
# Prepare a code identity; Local Network approval remains a user action.
set -euo pipefail

[[ "${1:-}" == "macos" ]] || exit 0
python_bin="${2:-}"
[[ -f "$python_bin" && -x "$python_bin" ]] || exit 0

warn() {
    printf '[PrintOps] WARNING: %s\n' "$*" >&2
}

if ! command -v codesign >/dev/null 2>&1; then
    warn "codesign is missing. Install the Xcode command line tools with 'xcode-select --install', then rerun install/update_macos.sh as your installation user."
    exit 0
fi

base_exe="$("$python_bin" -c 'import os, sys; print(os.path.realpath(getattr(sys, "_base_executable", None) or sys.executable))' 2>/dev/null)" || exit 0
[[ -n "$base_exe" && -f "$base_exe" && -x "$base_exe" ]] || exit 0
targets=("$base_exe")
framework="${base_exe%/bin/*}"
if [[ "$framework" != "$base_exe" && -d "$framework/Resources/Python.app" ]]; then
    targets+=("$framework/Resources/Python.app")
fi

for target in "${targets[@]}"; do
    if probe="$(LC_ALL=C codesign -dv "$target" 2>&1)"; then
        continue
    fi
    # A failed probe can also mean unreadable or invalid code. Fail closed.
    if [[ "$probe" != "$target: code object is not signed at all" ]]; then
        warn "Could not establish an unsigned signature for $target; leaving it unchanged. Check its code signature and rerun install/update_macos.sh."
        continue
    fi
    # No --force: a signature added since the probe must also remain intact.
    if LC_ALL=C codesign --sign - "$target" >/dev/null 2>&1; then
        printf '[PrintOps] Ad-hoc signed %s. Approve Python in System Settings > Privacy & Security > Local Network if prompted.\n' "$target"
    else
        warn "Could not sign $target; PrintOps may be unable to reach local printers. Check file permissions and rerun install/update_macos.sh as your installation user."
    fi
done
exit 0
