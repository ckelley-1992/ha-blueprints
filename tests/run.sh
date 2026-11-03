#!/bin/bash
# Validate motion_light_min_on.yaml with Home Assistant's own config check, then
# replay the scenarios in tests/sim.py against relay-like test lights.
# Usage: tests/run.sh   (set HA_VENV to reuse a venv elsewhere)
set -euo pipefail

HA_VERSION="2026.10.4"
HERE="$(cd "$(dirname "$0")" && pwd)"
BLUEPRINT="$HERE/../motion_light_min_on.yaml"
CONF="$HERE/haconf"
VENV="${HA_VENV:-${TMPDIR:-/tmp}/ha-blueprint-test-venv}"

if ! "$VENV/bin/hass" --version 2>/dev/null | grep -qx "$HA_VERSION"; then
  echo "Installing Home Assistant $HA_VERSION into $VENV ..."
  rm -rf "$VENV"
  uv venv --python 3.14 "$VENV" >/dev/null
  uv pip install --python "$VENV/bin/python" "homeassistant==$HA_VERSION" >/dev/null
fi

# Fresh state every run: copy the blueprint in, plus a variant whose sunrise
# trigger is a test event the simulation can fire.
rm -rf "$CONF/.storage" "$CONF/blueprints" "$CONF"/home-assistant.log*
mkdir -p "$CONF/blueprints/automation/ckelley"
cp "$BLUEPRINT" "$CONF/blueprints/automation/ckelley/motion_light_min_on.yaml"
"$VENV/bin/python" -I - "$CONF/blueprints/automation/ckelley" <<'EOF'
import pathlib, sys
d = pathlib.Path(sys.argv[1])
src = (d / "motion_light_min_on.yaml").read_text()
old = "  - trigger: sun\n    event: sunrise\n    id: resume\n"
assert src.count(old) == 1, "sunrise trigger not found"
(d / "motion_light_testsunrise.yaml").write_text(
    src.replace(old, "  - trigger: event\n    event_type: test_sunrise\n    id: resume\n"))
EOF

echo "== HA config check"
check=$("$VENV/bin/hass" --script check_config -c "$CONF" 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -v '^INFO')
echo "$check" | tail -3
if echo "$check" | grep -qiE "failed config|invalid config|error"; then exit 1; fi

echo "== Scenarios"
"$VENV/bin/python" -I "$HERE/sim.py" "$CONF" 2>&1 \
  | grep -vE "^(INFO|DEBUG)|custom integration|Python 3.14|Skipping pip|not been tested"

echo "== Unexpected warnings/errors in the HA log"
grep -E "WARNING|ERROR" "$CONF/home-assistant.log" \
  | grep -vE "Skipping pip|custom integration fakelight" || echo "none"
