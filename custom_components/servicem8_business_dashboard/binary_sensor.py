"""Binary sensor platform for ServiceM8 Business Dashboard."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BinarySensorDef, ServiceM8DashboardCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ServiceM8DashboardCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        ServiceM8DashboardBinarySensor(coordinator, entry, definition)
        for definition in coordinator.data["binary_sensors"]
    ]
    async_add_entities(entities)


class ServiceM8DashboardBinarySensor(CoordinatorEntity[ServiceM8DashboardCoordinator], BinarySensorEntity):
    """Representation of a ServiceM8 alert-style binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ServiceM8DashboardCoordinator,
        entry: ConfigEntry,
        definition: BinarySensorDef,
    ) -> None:
        super().__init__(coordinator)
        self._key = definition.key
        self._attr_name = definition.name
        self._attr_unique_id = f"{entry.entry_id}_{definition.key}"
        self._attr_icon = definition.icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="ServiceM8",
            model="Business Dashboard",
            name="ServiceM8 Dashboard",
            configuration_url="https://developer.servicem8.com/docs/getting-started",
        )

    @property
    def is_on(self) -> bool | None:
        definition = self._definition
        return definition.value if definition else None

    @property
    def extra_state_attributes(self):
        definition = self._definition
        return definition.attributes if definition else None

    @property
    def _definition(self) -> BinarySensorDef | None:
        for item in self.coordinator.data["binary_sensors"]:
            if item.key == self._key:
                return item
        return None
