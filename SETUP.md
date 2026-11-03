# Motion lights: setup

One blueprint (`motion_light_min_on.yaml`) drives all four rooms. Each room needs:
- an **ownership toggle**: the `input_boolean` you already use, e.g. `input_boolean.deck_triggered_with_motion`
- a **hold timer**: new, with Restore on
- an **automation** created from the blueprint

## How it behaves
- Motion turns the light on (after dark, for the deck and yard). The light stays on for at least the **min on-time**. After that, it turns off once the sensor has been clear for the **clear delay**.
- **You turn it on, you turn it off.** A light turned on by switch, app, Siri or Apple Home is never turned off by this automation.
- **Motion turned it on but you want it to stay on** (under the car, snowblowing)? Flick the switch off and back on. It's yours now.
- Lights turned on by other Home Assistant automations are adopted. They go off once the room is empty.
- The after-dark gate only blocks turning on. A light turned on at 23:50 still turns off after midnight.
- Fail-on: an offline sensor never counts as "clear", and a restart or automation reload never turns a light off.
- Optional **pause** (deck, shed): flip the switch quickly to stop motion turning the light on, e.g. for a fire-pit night. See section 5.

## 0. Wall switches must switch the light directly
The blueprint can tell your flips apart from automations only if the switch drives the relay itself. If an HA automation turns the light on when the switch flips, HA records every flip as made by an automation. Then:
- the pause counter never counts, and
- a light you turned on at the wall gets taken over and turned off once the room is empty.

**How to check:** flip the switch, then look at the light's newest logbook line. If it says "triggered by automation …", fix it.

**Fix (Shelly Plus 1PM):**
1. In the Shelly web UI, open the switch's **Input/Output settings**, keep the input mode as **Switch**, and change the output type from **Detached** to **Edge**. With Edge, every flip toggles the light, like a 3-way switch. Don't pick "Toggle": on this firmware it ties one switch position to ON and the other to OFF.
2. Disable the HA automation that did the switching (for the deck, "Deck Wall Switch v2").

As a bonus, the wall switch then works even when HA or Wi-Fi is down.

## 1. Install and update the blueprint
The blueprint lives at <https://github.com/ckelley-1992/ha-blueprints>. Its `source_url` points HA back there.

**Updating:** push the change to GitHub. Then in HA, go to **Settings → Automations & scenes → Blueprints**, open the blueprint's **⋮** menu, and choose **Re-import blueprint**. It overwrites the file in place, and every automation keeps its settings.

**One-time switchover for my HA Green:** the existing file, `/config/blueprints/automation/motion_light_after_min.yaml`, has no `source_url` yet.
1. Paste the GitHub version over it with File editor one last time.
2. Reload automations.

After that, use Re-import. Don't import the GitHub URL as a new blueprint: that makes a second copy at a new path, and the existing automations keep using the old one.

## 2. Create the helpers
Go to **Settings → Devices & services → Helpers → Create helper**.
- **Timer**, one per room, e.g. "Deck motion hold" → `timer.deck_motion_hold`. Leave the duration at anything, because the automation sets it. **Turn on "Restore"**.
- **Toggle**: reuse your existing ones. Create "<Room> triggered with motion" only for rooms that don't have one.

## 3. Swap each room over (do it in this order)
1. **Disable** the old automation (⋮ → Disable). Don't delete it yet. Two automations on one light will fight.
2. Turn the room's ownership toggle **off**. A stale `on` is exactly what used to turn off manual lights.
3. Go to **Blueprints → "Motion light with minimum on-time and manual override" → Create automation**, fill it in from the table below, and save it as e.g. "Deck Motion v3".

| Setting | Deck | Yard | Garage | Eve room #2 |
|---|---|---|---|---|
| Motion / occupancy sensor | `binary_sensor.deck_motion_combined` | yard group | Eve occupancy | Eve occupancy |
| Lights | deck wafer light | yard light(s) | garage light(s) | room light(s) |
| Ownership toggle | `input_boolean.deck_triggered_with_motion` | existing | existing / new | existing / new |
| Minimum on-time timer | `timer.deck_motion_hold` | `timer.yard_motion_hold` | `timer.garage_motion_hold` | `timer.<room>_motion_hold` |
| Minimum on-time | 5 min | 5 min | 10 min | 5 min |
| Clear delay | 1 min | 1 min | 10 min | 2 min |
| Adopt lights turned on by other HA automations | on | on | on | on |
| Turn-on conditions | Sun is set | Sun is set | none | whatever the old one had |

To add the deck/yard turn-on condition, go to **Add condition** and choose **Sun is set**, which is true from sunset to sunrise. Don't choose "It is night": it only becomes true once the sky is fully dark, about 1.5 hours after sunset. In YAML:
```yaml
condition: sun.is_set
```

The garage values are starting points. The Eve sensor's own occupancy hold time adds on top of the clear delay.

## 4. Test each room
Open the automation's **Traces**, and keep the room's toggle and timer on a dashboard while you test.
1. Walk in with the light off (after dark outdoors): the light turns on, the toggle turns on and the timer starts. Leave right away: the light stays on until the timer ends, then goes off.
2. Turn the light on at the switch, walk around, then leave: the light **stays on** and the toggle stays off.
3. Let motion turn it on, then flick the switch off and back on: the toggle goes off, and the light stays on past every timer.
4. Restart HA while motion owns a light: the light stays on, then turns off normally later.

Once a room passes, delete its old automation, or keep it disabled as a fallback.

## 5. Pause (deck, shed)
**Using it**
- **Pause:** flip the switch quickly **6 times** (on, off, on, off, on, off), with no more than 3 s between flips. The light turns off to confirm. Motion won't turn it on until you resume, but you can still turn it on by hand for the fire pit.
- **Resume:** do the same 6 flips. The light blinks once to confirm.
- **Sunrise** resumes it automatically, so a pause can't be forgotten for days.
- The pause is an ordinary toggle, so you can also flip it from a dashboard, or by voice if you expose it to Apple Home.

**Setting it up**
1. **Update the blueprint.** In File editor, open `blueprints/automation/ckelley/motion_light_min_on.yaml`, replace everything with the new version, and save. Then go to Developer tools → YAML and reload **Automations**. All four room automations pick up the change. The pause settings are optional and start empty, so nothing else changes.
2. **Retire the old override.** Disable "Deck light motion override", the old press-counting/timer setup, and "Deck Wall Switch v2". Set the Shelly to Edge first (section 0). Otherwise the old override can still switch the new automation off, and wall flips won't count.
3. **Make sure the deck motion automation is enabled.** The old override may have left it off.
4. Create a **Toggle** helper, "Deck motion paused" → `input_boolean.deck_motion_paused`.
5. **Check the counter.** Reuse `counter.deck_toggle_counter`. In its helper settings, confirm initial value 0, step 1, and no maximum below 6.
6. Open the deck motion automation, expand **Pause (optional)**, and set **Pause toggle** and **Switch press counter**. The defaults are 6 presses (the same as your old `above: 5`), at most 3 s between presses, and resume at sunrise.
7. **Shed:** do the same with its own toggle and counter, e.g. `input_boolean.shed_motion_paused` and `counter.shed_toggle_counter`.

**Test it:**
1. Do 6 quick flips: the light ends off and the pause toggle turns on.
2. Walk around: the light stays off.
3. Turn the light on by hand: it stays on.
4. Do 6 quick flips again: one blink, and the pause toggle turns off.
5. Walk around: motion works again.

## 6. "Triggered by" status (Shelly lights)
Each light gets a dropdown that shows what made its last on or off:
- **Automation:** motion, or another HA automation.
- **Software:** the HA app, a dashboard, Apple Home or Siri.
- **Wall switch:** someone flipped the switch.

**Setting it up, per light:**
1. Create a **Dropdown** helper, e.g. "Deck light triggered by", with exactly these options: `Automation`, `Software`, `Wall switch`.
2. Open the room's motion automation and expand **Dashboard status (optional)**:
   - **Triggered by:** the dropdown.
   - **Wall switch sensor:** the Shelly's switch input, e.g. `binary_sensor.decklight_input_0_input`. Only use the input that the wall switch is wired to, with the Shelly in Edge mode, and not the driveway's RAB motion input.

With a wall switch sensor set, pause counts only wall flips, so the HA app and Apple Home never count toward pausing. Without one, HA can't tell Apple Home from the wall switch, and both show as **Wall switch**.

## Garage door (Apple Home): recommendation
HA can't tell your Apple Home door automation apart from you pressing the switch. If Apple Home turns the garage light on before HA's motion does, HA treats it as manual and leaves it on. Motion already fires as the door opens, so **removing the light from the Apple Home door automation** lets HA handle it consistently.

## Rollback
Disable the v3 automation and re-enable the old one.
