"""DeviceInfo, defined once (the kiosk_pi §16.1 convention)."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class HouseholdStateEntity(CoordinatorEntity):
    """One device for the whole layer.

    `_attr_has_entity_name = True` so ids slug from the device name:
    sensor.household_state_stage, not sensor.household_state_stage_stage.
    This is the fix kiosk_pi applied to the 22 Glances ids that carried
    the IP address in the id itself.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Household State",
            manufacturer="the home network",
            model="Directive resolver",
            sw_version="0.5.0",
            entry_type=None,
        )
