"""DeviceInfo, defined once."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION


class HouseholdStateEntity(CoordinatorEntity):
    """One device for the whole layer.

    `_attr_has_entity_name = True` so ids slug from the device name:
    sensor.household_state_stage, not sensor.household_state_stage_stage.
    This is the same fix applied elsewhere to entity ids that carried
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
            manufacturer="Household State",
            model="Directive resolver",
            sw_version=VERSION,
            entry_type=None,
        )
