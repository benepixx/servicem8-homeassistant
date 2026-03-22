"""Sensor platform for ServiceM8 Business Dashboard."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import SensorDef, ServiceM8DashboardCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ServiceM8DashboardCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        ServiceM8DashboardSensor(coordinator, entry, definition)
        for definition in coordinator.data["sensors"]
    ]
    async_add_entities(entities)


class ServiceM8DashboardSensor(CoordinatorEntity[ServiceM8DashboardCoordinator], SensorEntity):
    """Representation of an aggregated ServiceM8 sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ServiceM8DashboardCoordinator,
        entry: ConfigEntry,
        definition: SensorDef,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = None
        self._entry = entry
        self._key = definition.key
        self._attr_name = definition.name
        self._attr_unique_id = f"{entry.entry_id}_{definition.key}"
        self._attr_icon = definition.icon
        self._attr_native_unit_of_measurement = definition.unit
        self._attr_device_class = definition.device_class
        self._attr_state_class = definition.state_class
        self._attr_suggested_display_precision = definition.suggested_display_precision
        self._attr_entity_category = definition.entity_category
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="ServiceM8",
            model="Business Dashboard",
            name="ServiceM8 Dashboard",
            configuration_url="https://developer.servicem8.com/docs/getting-started",
        )

    @property
    def native_value(self):
        definition = self._definition
        return definition.value if definition else None

    @property
    def extra_state_attributes(self):
        definition = self._definition
        return definition.attributes if definition else None

    @property
    def _definition(self) -> SensorDef | None:
        for item in self.coordinator.data["sensors"]:
            if item.key == self._key:
                return item
        return None
