"""On/off light that behaves like a Shelly relay: a command's state lands a
moment later, and wall-switch flips are written with no context of their own,
so HA tags them with the last command's context for 5 s."""

from homeassistant.components.light import ColorMode, LightEntity

LATENCY = 0.15


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    async_add_entities([FakeRelayLight(name) for name in config["names"]])


class FakeRelayLight(LightEntity):
    _attr_should_poll = False
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, name):
        self._attr_name = name
        self._attr_unique_id = f"fake_{name.lower().replace(' ', '_')}"
        self._attr_is_on = False

    def _report(self, on):
        self._attr_is_on = on
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        self.hass.loop.call_later(LATENCY, self._report, True)

    async def async_turn_off(self, **kwargs):
        self.hass.loop.call_later(LATENCY, self._report, False)

    def wall_switch(self, on):
        self._report(on)
