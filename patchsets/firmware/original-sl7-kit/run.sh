#!/usr/bin/env bash
set -u
KIT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if (( EUID != 0 )); then exec sudo bash "$0" "$@"; fi
MODE=${1:-all}
case "$MODE" in
    all)
        bash "$KIT/collect.sh" before || exit $?
        bash "$KIT/fix.sh"
        ;;
    collect) bash "$KIT/collect.sh" after ;;
    after)
        bash "$KIT/collect.sh" after --no-live
        bash "$KIT/wifi.sh"
        ;;
    wifi) bash "$KIT/wifi.sh" ;;
    quick) bash "$KIT/collect.sh" quick --no-live ;;
    fix) bash "$KIT/fix.sh" ;;
    undo) bash "$KIT/undo.sh" ;;
    *) echo 'Usage: sudo bash run.sh [all|after|collect|quick|fix|wifi|undo]'; exit 2 ;;
esac
