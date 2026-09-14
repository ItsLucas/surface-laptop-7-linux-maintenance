#!/usr/bin/env bash
# Shared setup. Run the kit with sudo bash run.sh.
set -u
KIT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if (( EUID != 0 )); then
    echo 'Please run: sudo bash run.sh' >&2
    exit 1
fi
OWNER=${SUDO_USER:-root}
USER_HOME=$(getent passwd "$OWNER" | cut -d: -f6)
USER_HOME=${USER_HOME:-/root}
RESULTS="$USER_HOME/sl7-diag"
mkdir -p "$RESULTS"
chmod 700 "$RESULTS"
chown "$OWNER" "$RESULTS"
STAMP=$(date +%Y%m%d-%H%M%S)-$$

say() { printf '\n%s\n' "$*"; }
runlog() {
    local name=$1
    shift
    { printf 'COMMAND:'; printf ' %q' "$@"; printf '\n';
      timeout --kill-after=3s 45s "$@"; rc=$?; printf '\nEXIT=%s\n' "$rc";
    } >"$OUT/$name.txt" 2>&1
    return 0
}
shelllog() { local name=$1; shift; runlog "$name" bash -c "$*"; }
finish_output() {
    chown -R "$OWNER" "$OUT"
    local archive_rc=0
    tar -C "$RESULTS" -czf "$OUT.tar.gz" "$(basename "$OUT")" || archive_rc=$?
    if (( archive_rc > 1 )); then
        say "Archive failed; all collected files remain in: $OUT"
        return 0
    fi
    chown "$OWNER" "$OUT.tar.gz"
    printf '%s\n' "$OUT.tar.gz" >"$RESULTS/LATEST.txt"
    chown "$OWNER" "$RESULTS/LATEST.txt"
    say "Saved: $OUT.tar.gz"
}
