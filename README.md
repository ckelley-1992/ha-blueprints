# ha-blueprints

Home Assistant blueprints.

## Motion light with minimum on-time and manual override

[![Open your Home Assistant instance and show the blueprint import dialog with this blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fckelley-1992%2Fha-blueprints%2Fblob%2Fmain%2Fmotion_light_min_on.yaml)

[`motion_light_min_on.yaml`](motion_light_min_on.yaml) turns lights on with motion or occupancy. It never turns off a light someone else turned on.

- **Minimum on-time.** The light stays on at least this long, then until the sensor has been clear for a delay.
- **Manual turn-ons are left alone.** A light turned on at the switch, in an app or with Apple Home/Siri is never turned off. To claim a light that motion turned on, flick the switch off and back on.
- **Other HA automations are optionally adopted.** A light turned on by another automation can be turned off once the room is empty.
- **Fail-on.** An unavailable sensor never counts as clear, and a restart or automation reload never turns a light off. Turn-on conditions (such as *Sun is set*) only gate turning on.
- **Optional pause.** Flip the switch quickly several times (6 by default) to stop motion turning the light on. Flip it again to resume. It also resumes at sunrise.
- **Optional "triggered by" status.** A dropdown helper shows whether the last on/off came from an automation, software (app, Apple Home) or the wall switch. With a Shelly in Edge mode, its switch input tells a wall flip apart from Apple Home.

**Per room, it needs:**
- an `input_boolean`, which tracks whether the automation owns the light;
- a `timer` with *Restore* enabled.

The pause adds an `input_boolean` and a `counter`. The status needs an `input_select` with the options `Automation`, `Software`, `Wall switch`.

**Updating:** HA records where a blueprint came from. Push a new version here, then in Home Assistant use **⋮ → Re-import blueprint** on it. Automations made from it keep their settings.

**Tests:** `tests/run.sh` installs Home Assistant (version pinned in the script) into a temporary venv. It runs HA's config check on the blueprint, then replays the scenarios in [`tests/sim.py`](tests/sim.py) against relay-like test lights that behave like a Shelly. It needs [uv](https://docs.astral.sh/uv/).

[SETUP.md](SETUP.md) has the notes for my own install.
