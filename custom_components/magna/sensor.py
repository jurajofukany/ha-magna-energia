"""Sensor platform for the Magna Energia iPortal integration."""
from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BAND_KEYS, BAND_LABELS_SK, DELIVERY_POINTS, DOMAIN, PORTAL_BASE_URL
from .coordinator import MagnaCoordinator

_LOGGER = logging.getLogger(__name__)

_PERIOD_LABEL_SK = {"day": "deň", "month": "mesiac"}


@dataclass(frozen=True, kw_only=True)
class MagnaSensorDescription(SensorEntityDescription):
    """Sensor description mapping to a (period, metric) path in one point's metrics dict."""

    metrics_path: tuple[str, str] = ("", "")


def _band_and_total_descriptions(point_config: dict) -> list[MagnaSensorDescription]:
    descriptions: list[MagnaSensorDescription] = []

    for period, period_label in _PERIOD_LABEL_SK.items():
        if point_config["band_sensors"]:
            for band_key in BAND_KEYS:
                descriptions.append(
                    MagnaSensorDescription(
                        key=f"{period}_{band_key}",
                        translation_key=f"{period}_{band_key}",
                        name=f"{BAND_LABELS_SK[band_key]} ({period_label})",
                        metrics_path=(period, f"{band_key}_kwh"),
                        device_class=SensorDeviceClass.ENERGY,
                        state_class=SensorStateClass.TOTAL,
                        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                    )
                )

        descriptions.append(
            MagnaSensorDescription(
                key=f"{period}_total",
                translation_key=f"{period}_total",
                name=f"Spolu ({period_label})",
                metrics_path=(period, "total_kwh"),
                device_class=SensorDeviceClass.ENERGY,
                state_class=SensorStateClass.TOTAL,
                native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            )
        )

        if point_config["cost"]:
            descriptions.append(
                MagnaSensorDescription(
                    key=f"{period}_cost",
                    translation_key=f"{period}_cost",
                    name=f"Náklady podľa portálu ({period_label})",
                    metrics_path=(period, "total_eur"),
                    device_class=SensorDeviceClass.MONETARY,
                    state_class=SensorStateClass.TOTAL,
                    native_unit_of_measurement="EUR",
                )
            )

    if point_config["peak_power"]:
        descriptions.append(
            MagnaSensorDescription(
                key="peak_max_power",
                translation_key="peak_max_power",
                name="Maximálny výkon (tento mesiac)",
                metrics_path=("peak", "max_power_kw"),
                device_class=SensorDeviceClass.POWER,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=UnitOfPower.KILO_WATT,
            )
        )
        descriptions.append(
            MagnaSensorDescription(
                key="peak_max_power_at",
                translation_key="peak_max_power_at",
                name="Čas maximálneho výkonu (tento mesiac)",
                metrics_path=("peak", "max_power_at"),
                device_class=SensorDeviceClass.TIMESTAMP,
            )
        )

    return descriptions


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: MagnaCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[MagnaSensor] = []
    for point_key, point_config in DELIVERY_POINTS.items():
        for description in _band_and_total_descriptions(point_config):
            entities.append(MagnaSensor(coordinator, entry, point_key, point_config, description))
    async_add_entities(entities)


class MagnaSensor(CoordinatorEntity[MagnaCoordinator], SensorEntity):
    """One metric (a band/total kWh, a EUR cost, or a peak-power figure) for one point."""

    entity_description: MagnaSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MagnaCoordinator,
        entry: ConfigEntry,
        point_key: str,
        point_config: dict,
        description: MagnaSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._point_key = point_key

        self._attr_unique_id = f"{entry.entry_id}_{point_key}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{point_key}")},
            name=f"Magna Energia - {point_config['label']}",
            manufacturer="Magna Energia",
            model=point_config.get("eic"),
            configuration_url=PORTAL_BASE_URL,
        )

    @property
    def available(self) -> bool:
        return super().available and self._point_key in self.coordinator.data

    @property
    def native_value(self):
        period, metric_key = self.entity_description.metrics_path
        point_metrics = self.coordinator.data.get(self._point_key, {})
        return point_metrics.get(period, {}).get(metric_key)

    @property
    def extra_state_attributes(self) -> dict:
        period, _ = self.entity_description.metrics_path
        point_metrics = self.coordinator.data.get(self._point_key, {})
        period_metrics = point_metrics.get(period, {})
        if period in ("day", "month"):
            return {
                "obdobie_od": period_metrics.get("date_from"),
                "obdobie_do": period_metrics.get("date_to"),
            }
        return {}
