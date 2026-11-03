"""Run the motion-light blueprint inside a headless Home Assistant and play
out the agreed scenarios against relay-like lights. Timings: min_on = 4s,
clear_delay = 2s, pause = 6 presses with at most 1s between them."""

import asyncio
import sys

import homeassistant.bootstrap as b
from homeassistant import runner
from homeassistant.components.light.const import DATA_COMPONENT
from homeassistant.core import Context

# Only load what the test config asks for (no frontend, network, discovery).
b.DEFAULT_INTEGRATIONS = set()
b.CRITICAL_INTEGRATIONS = set()
b.FRONTEND_INTEGRATIONS = set()
b.STAGE_0_INTEGRATIONS = []
b.STAGE_1_INTEGRATIONS = set()
b.DISCOVERY_INTEGRATIONS = ()

DARK = "input_boolean.is_dark"
ROOMS = {
    "deck": dict(sensor="binary_sensor.deck_motion_combined", light="light.deck_wafer",
                 flag="input_boolean.deck_triggered_with_motion", timer="timer.deck_motion_hold",
                 pause="input_boolean.deck_motion_paused", counter="counter.deck_toggle_counter",
                 source="input_select.deck_light_source", wall="binary_sensor.deck_wall_input"),
    "shed": dict(sensor="binary_sensor.shed_motion", light="light.shed_light",
                 flag="input_boolean.shed_triggered_with_motion", timer="timer.shed_motion_hold",
                 pause="input_boolean.shed_motion_paused", counter="counter.shed_toggle_counter",
                 source=None, wall=None),
    "garage": dict(sensor="binary_sensor.garage_occupancy", light="light.garage_light",
                   flag="input_boolean.garage_triggered_with_motion", timer="timer.garage_motion_hold",
                   pause=None, counter=None, source="input_select.garage_light_source", wall=None),
}
AUTO, SOFT, WALL = "Automation", "Software", "Wall switch"
OTHER = Context(parent_id="other_automation_run")

results = []


async def main(config_dir):
    hass = await b.async_setup_hass(runner.RuntimeConfig(config_dir=config_dir, skip_pip=True))
    await hass.async_start()
    await hass.async_block_till_done()
    admin = await hass.auth.async_create_user("Dashboard user", group_ids=["system-admin"])

    def st(e):
        s = hass.states.get(e) if e else None
        return s.state if s else None

    async def settle(sec=0.0):
        if sec:
            await asyncio.sleep(sec)
        await hass.async_block_till_done()

    async def svc(service, entity, context=None):
        d, s = service.split(".")
        await hass.services.async_call(d, s, {"entity_id": entity}, blocking=True, context=context)

    def room(name):
        r = ROOMS[name]

        def sensor(state):
            hass.states.async_set(r["sensor"], state, {"device_class": "motion"}, context=Context())

        def flip_input():
            if r["wall"]:
                hass.states.async_set(r["wall"], "off" if st(r["wall"]) == "on" else "on",
                                      {"device_class": "power"}, context=Context())

        async def press(on=None, input_first=False):
            """Wall switch on a Shelly in Edge mode: the relay flips locally and
            reports with no context of its own (HA applies any command context
            that is under 5 s old). The switch input sensor reports separately,
            normally a moment after the relay."""
            if on is None:
                on = st(r["light"]) != "on"
            if input_first:
                flip_input()
            hass.data[DATA_COMPONENT].get_entity(r["light"]).wall_switch(on)
            if not input_first:
                hass.loop.call_later(0.05, flip_input)
            await settle()

        async def presses(n, gap):
            for _ in range(n):
                await press()
                await settle(gap)

        def check(label, cond):
            results.append((label, cond))
            extra = ""
            if r["pause"]:
                extra += f" paused={st(r['pause'])} count={st(r['counter'])}"
            if r["source"]:
                extra += f" source={st(r['source'])!r}"
            print(f"  {'PASS' if cond else 'FAIL'}  {label}  [light={st(r['light'])} "
                  f"flag={st(r['flag'])} timer={st(r['timer'])} sensor={st(r['sensor'])}{extra}]")

        async def reset():
            sensor("off")
            await settle()
            await press(False)
            await svc("input_boolean.turn_off", r["flag"])
            await svc("timer.cancel", r["timer"])
            await svc("input_boolean.turn_on", DARK)
            await settle(5.5)  # let pending triggers, press windows and command contexts expire
            if r["pause"]:
                await svc("input_boolean.turn_off", r["pause"])
                await svc("counter.reset", r["counter"])
            await settle()

        return r, sensor, press, presses, check, reset

    r, sensor, press, presses, check, reset = room("deck")
    LIGHT, FLAG, TIMER, PAUSE, COUNTER, SRC = (r["light"], r["flag"], r["timer"],
                                              r["pause"], r["counter"], r["source"])

    # ---------------- core behavior ----------------
    print("S1 motion, then leave right away -> on for min_on, then off")
    await reset()
    sensor("on"); await settle(0.5)
    check("light on + owned + timer active, triggered by Automation",
          st(LIGHT) == "on" and st(FLAG) == "on" and st(TIMER) == "active" and st(SRC) == AUTO)
    sensor("off"); await settle(2.5)
    check("still on before min_on ends (clear fired, timer active)", st(LIGHT) == "on")
    await settle(2.5)
    check("off after min_on, triggered by Automation",
          st(LIGHT) == "off" and st(FLAG) == "off" and st(SRC) == AUTO)

    print("S2 stay past min_on -> on until clear_delay after leaving")
    await reset()
    sensor("on"); await settle(6)
    check("still on while occupied past min_on", st(LIGHT) == "on" and st(TIMER) == "idle")
    sensor("off"); await settle(1)
    check("still on inside clear_delay", st(LIGHT) == "on")
    await settle(2)
    check("off after clear_delay", st(LIGHT) == "off" and st(FLAG) == "off")

    print("S3 snowblowing: switched on at the wall, motion comes and goes")
    await reset()
    await press(True); await settle(0.5)
    check("wall on: not owned, triggered by Wall switch",
          st(LIGHT) == "on" and st(FLAG) == "off" and st(SRC) == WALL)
    sensor("on"); await settle(1); sensor("off"); await settle(8)
    check("wall-on light never turned off", st(LIGHT) == "on" and st(FLAG) == "off")

    print("S3b on from Apple Home (HomeKit Bridge: no user, no parent)")
    await reset()
    await svc("light.turn_on", LIGHT, context=Context()); await settle(0.5)
    check("triggered by Software (no wall flip)", st(SRC) == SOFT)
    sensor("on"); await settle(1); sensor("off"); await settle(8)
    check("Apple Home light never turned off", st(LIGHT) == "on" and st(FLAG) == "off")

    print("S3c on from the HA app / dashboard (has an HA user)")
    await reset()
    await svc("light.turn_on", LIGHT, context=Context(user_id=admin.id)); await settle(0.5)
    check("triggered by Software, not owned", st(SRC) == SOFT and st(FLAG) == "off")
    sensor("on"); await settle(1); sensor("off"); await settle(8)
    check("app light never turned off", st(LIGHT) == "on")

    print("S4 claim: motion turns on, flick off/on within 5 s, then lie still")
    await reset()
    sensor("on"); await settle(0.5)
    check("owned after motion", st(FLAG) == "on")
    await press(False); await settle(0.3); await press(True); await settle(0.5)
    check("flick released ownership, triggered by Wall switch",
          st(LIGHT) == "on" and st(FLAG) == "off" and st(TIMER) == "idle" and st(SRC) == WALL)
    sensor("off"); await settle(8)
    check("claimed light never turned off", st(LIGHT) == "on")

    print("S5 dark gate only blocks turning on (midnight/sunrise bug)")
    await reset()
    await svc("input_boolean.turn_off", DARK)
    sensor("on"); await settle(1)
    check("no turn-on while gate closed", st(LIGHT) == "off" and st(FLAG) == "off")
    sensor("off"); await settle(0.5)
    await svc("input_boolean.turn_on", DARK)
    sensor("on"); await settle(0.5)
    check("turns on when gate open", st(LIGHT) == "on" and st(FLAG) == "on")
    await svc("input_boolean.turn_off", DARK)
    sensor("off"); await settle(6)
    check("still turns off after gate closes", st(LIGHT) == "off" and st(FLAG) == "off")

    print("S6 another HA automation turns the light on -> adopted")
    await reset()
    await svc("light.turn_on", LIGHT, context=OTHER); await settle(0.5)
    check("adopted: owned + timer active, triggered by Automation",
          st(FLAG) == "on" and st(TIMER) == "active" and st(SRC) == AUTO)
    await settle(5)
    check("adopted light off once empty", st(LIGHT) == "off" and st(FLAG) == "off" and st(SRC) == AUTO)

    print("S7 reload/restart reconcile never turns anything off")
    await reset()
    sensor("on"); await settle(0.5)
    await svc("timer.cancel", TIMER)
    hass.bus.async_fire("automation_reloaded"); await settle(0.5)
    check("owned light kept on, timer re-armed",
          st(LIGHT) == "on" and st(TIMER) == "active" and st(SRC) == AUTO)
    sensor("off"); await settle(5)
    check("then turns off normally", st(LIGHT) == "off")
    await svc("input_boolean.turn_on", FLAG)
    hass.bus.async_fire("automation_reloaded"); await settle(0.5)
    check("stale claim on an off light is dropped", st(FLAG) == "off")

    print("S8 sensor goes unavailable while owned -> fail on")
    await reset()
    sensor("on"); await settle(0.5)
    sensor("unavailable"); await settle(7)
    check("unavailable sensor never turns light off", st(LIGHT) == "on" and st(FLAG) == "on")
    sensor("off"); await settle(3)
    check("turns off once sensor reports clear", st(LIGHT) == "off")

    print("S9 wall off while owned, later wall on -> honored")
    await reset()
    sensor("on"); await settle(0.5)
    await press(False); await settle(0.5)
    check("wall off released ownership", st(FLAG) == "off" and st(TIMER) == "idle")
    sensor("off"); await settle(3)
    await press(True); await settle(0.5)
    sensor("on"); await settle(0.5); sensor("off"); await settle(7)
    check("later wall on never turned off", st(LIGHT) == "on" and st(FLAG) == "off")

    # ---------------- pause ----------------
    blinks = []

    def on_change(event):
        new = event.data.get("new_state")
        if event.data.get("entity_id") == LIGHT and new and new.state == "on":
            blinks.append(new.context.id)

    def resume_blinks():
        """'on' changes made by the run that resumed (it also flipped the pause toggle)."""
        return blinks.count(hass.states.get(PAUSE).context.id)

    hass.bus.async_listen("state_changed", on_change)

    print("P1 six quick flips (light was off) -> paused, light off")
    await reset()
    await presses(6, 0.25)
    await settle(0.5)
    check("paused, light off, counter reset, nothing owned",
          st(PAUSE) == "on" and st(LIGHT) == "off" and st(COUNTER) == "0" and st(FLAG) == "off")
    sensor("on"); await settle(1)
    check("motion does not turn light on while paused", st(LIGHT) == "off" and st(FLAG) == "off")
    sensor("off"); await settle(2.5)

    print("P2 paused: fire pit with the light on at the wall; other automations not adopted")
    await press(True); await settle(0.5)
    sensor("on"); await settle(1); sensor("off"); await settle(7)
    check("wall light stays on while paused", st(LIGHT) == "on" and st(FLAG) == "off" and st(PAUSE) == "on")
    await press(False); await settle(1.5)
    await svc("light.turn_on", LIGHT, context=OTHER); await settle(0.5)
    check("HA-automation turn-on not adopted while paused", st(LIGHT) == "on" and st(FLAG) == "off")
    await press(False); await settle(1.5)

    print("P3 six quick flips again -> resumed with one blink")
    await svc("counter.reset", COUNTER); await settle(1.5)
    blinks.clear()
    await presses(6, 0.25)
    await settle(1.5)
    check("resumed, one blink, ends off and unowned",
          st(PAUSE) == "off" and resume_blinks() == 1 and st(LIGHT) == "off"
          and st(FLAG) == "off" and st(TIMER) == "idle")
    sensor("on"); await settle(0.5)
    check("motion works again after resume", st(LIGHT) == "on" and st(FLAG) == "on")

    print("P4 flips too slow -> no pause")
    await reset()
    await presses(6, 1.4)
    check("not paused", st(PAUSE) == "off")

    print("P5 other automations' on/offs never count as presses")
    await reset()
    for _ in range(3):
        await svc("light.turn_on", LIGHT, context=Context(parent_id="other_automation_run"))
        await settle(0.5)
        await svc("light.turn_off", LIGHT, context=Context(parent_id="other_automation_run"))
        await settle(0.5)
    await settle(0.5)
    check("counter untouched, not paused", st(COUNTER) == "0" and st(PAUSE) == "off")

    print("P6 pause from a dashboard/Siri (toggle flipped directly)")
    await reset()
    await svc("input_boolean.turn_on", PAUSE); await settle(0.2)
    sensor("on"); await settle(1)
    check("motion blocked", st(LIGHT) == "off")
    sensor("off"); await settle(0.5)

    # ---------------- inside the 5 s command-context window ----------------
    print("K1 flips within 5 s of motion turning the light on still pause it")
    await reset()
    sensor("on"); await settle(0.5)
    check("owned after motion", st(FLAG) == "on")
    await presses(6, 0.25); await settle(0.5)
    check("paused, light off, unowned", st(PAUSE) == "on" and st(LIGHT) == "off" and st(FLAG) == "off")

    print("K2 resume flips within 5 s of the pause turning the light off")
    blinks.clear()
    await presses(6, 0.25); await settle(1.5)
    check("resumed with one blink", st(PAUSE) == "off" and resume_blinks() == 1 and st(LIGHT) == "off")
    sensor("off"); await settle(2.5)

    print("K3 automation turns the light off, wall on within 5 s -> honored")
    await reset()
    sensor("on"); await settle(0.5); sensor("off"); await settle(4.5)
    check("auto-off happened", st(LIGHT) == "off" and st(FLAG) == "off")
    await press(True); await settle(0.5)
    check("wall on right after auto-off is not owned, triggered by Wall switch",
          st(LIGHT) == "on" and st(FLAG) == "off" and st(SRC) == WALL)
    sensor("on"); await settle(0.5); sensor("off"); await settle(8)
    check("and is never turned off", st(LIGHT) == "on")

    print("K4 another automation turns it on, wall off/on within 5 s -> honored")
    await reset()
    await svc("light.turn_on", LIGHT, context=OTHER); await settle(0.5)
    check("adopted", st(FLAG) == "on")
    await press(False); await settle(0.3); await press(True); await settle(0.5)
    check("flick released it", st(LIGHT) == "on" and st(FLAG) == "off" and st(SRC) == WALL)
    await settle(6)
    check("never turned off", st(LIGHT) == "on")

    print("T1 'triggered by' covers off too, and either report order from the Shelly")
    await reset()
    await press(True); await settle(0.5)
    await press(False); await settle(1.5)
    check("wall off: triggered by Wall switch", st(LIGHT) == "off" and st(SRC) == WALL)
    await press(True, input_first=True); await settle(1.5)
    check("input reported before the relay: still Wall switch", st(LIGHT) == "on" and st(SRC) == WALL)
    await svc("light.turn_off", LIGHT, context=Context(user_id=admin.id)); await settle(1.5)
    check("app off: triggered by Software", st(LIGHT) == "off" and st(SRC) == SOFT)
    await svc("light.turn_on", LIGHT, context=Context()); await settle(1.5)
    check("Apple Home on: triggered by Software, not owned", st(SRC) == SOFT and st(FLAG) == "off")
    sensor("on"); await settle(0.5); sensor("off"); await settle(7)
    check("and never turned off", st(LIGHT) == "on")

    # ---------------- shed: sunrise resume, no status helper ----------------
    r, sensor, press, presses, check, reset = room("shed")
    print("R1 shed paused overnight -> sunrise resumes it, no blink")
    await reset()
    await presses(6, 0.25); await settle(0.5)
    check("shed paused", st(r["pause"]) == "on" and st(r["light"]) == "off")
    hass.bus.async_fire("test_sunrise"); await settle(1)
    check("sunrise resumed, light still off", st(r["pause"]) == "off" and st(r["light"]) == "off")
    sensor("on"); await settle(0.5)
    check("motion works after sunrise resume", st(r["light"]) == "on" and st(r["flag"]) == "on")
    sensor("off"); await settle(5)

    # ---------------- garage: status helper, no pause ----------------
    r, sensor, press, presses, check, reset = room("garage")
    print("G1 garage without pause settings behaves normally")
    await reset()
    sensor("on"); await settle(0.5)
    check("motion turns on + owned, triggered by Automation",
          st(r["light"]) == "on" and st(r["flag"]) == "on" and st(r["source"]) == AUTO)
    sensor("off"); await settle(5)
    check("turns off after min_on", st(r["light"]) == "off" and st(r["source"]) == AUTO)
    await presses(6, 0.25); await settle(0.5)
    sensor("on"); await settle(0.5)
    check("rapid flips do nothing special; motion still works", st(r["light"]) == "on")
    await reset()
    await press(True); await settle(1.5)
    check("no wall switch sensor set: wall flip shows as Wall switch", st(r["source"]) == WALL)

    await hass.async_stop()
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


asyncio.run(main(sys.argv[1]))
