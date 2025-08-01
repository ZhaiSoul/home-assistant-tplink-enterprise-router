"""Component providing support for TPLinkRouter button entities."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TPLinkEnterpriseRouterCoordinator


@dataclass
class TPLinkEnterpriseRouterButtonEntityDescriptionMixin:
    method: Callable[[TPLinkEnterpriseRouterCoordinator], Any]


@dataclass
class TPLinkButtonEntityDescription(
    ButtonEntityDescription, TPLinkEnterpriseRouterButtonEntityDescriptionMixin
):
    """A class that describes button entities for the host."""


BUTTON_TYPES = (
    TPLinkButtonEntityDescription(
        key="refresh",
        name="Refresh",
        translation_key="refresh",
        device_class=ButtonDeviceClass.UPDATE,
        entity_category=EntityCategory.CONFIG,
        method=lambda coordinator: coordinator.refresh(),
    ),
    TPLinkButtonEntityDescription(
        key="reboot",
        name="Reboot",
        translation_key="reboot",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        method=lambda coordinator: coordinator.reboot(),
    ),
    TPLinkButtonEntityDescription(
        key="reboot_ap",
        name="Reboot AP",
        translation_key="reboot_ap",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        method=lambda coordinator: coordinator.reboot_ap(),
    ),
    TPLinkButtonEntityDescription(
        key="reboot_ap_and_router",
        name="Reboot AP and Router",
        translation_key="reboot_ap_and_router",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        method=lambda coordinator: coordinator.reboot_ap_and_router(),
    ),
    TPLinkButtonEntityDescription(
        key="turn_on_ap_light",
        name="Turn On AP Light",
        translation_key="turn_on_ap_light",
        device_class=ButtonDeviceClass.UPDATE,
        entity_category=EntityCategory.CONFIG,
        method=lambda coordinator: coordinator.set_ap_light("on"),
    ),
    TPLinkButtonEntityDescription(
        key="turn_off_ap_light",
        name="Turn Off AP Light",
        translation_key="turn_off_ap_light",
        device_class=ButtonDeviceClass.UPDATE,
        entity_category=EntityCategory.CONFIG,
        method=lambda coordinator: coordinator.set_ap_light("off"),
    ),
)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    buttons = []

    for description in BUTTON_TYPES:
        buttons.append(TPLinkEnterpriseRouterButtonEntity(coordinator, description))
    async_add_entities(buttons, False)


class TPLinkEnterpriseRouterButtonEntity(CoordinatorEntity[TPLinkEnterpriseRouterCoordinator], ButtonEntity):
    entity_description: TPLinkButtonEntityDescription

    def __init__(
            self,
            coordinator: TPLinkEnterpriseRouterCoordinator,
            description: TPLinkButtonEntityDescription,
    ) -> None:
        super().__init__(coordinator)

        self.entity_id = f"button.{DOMAIN}_{description.key}_{coordinator.unique_id}"
        self._attr_unique_id = f"{DOMAIN}_{description.key}_{coordinator.unique_id}"
        self._attr_device_info = coordinator.device_info
        self.entity_description = description
        self._attr_has_entity_name = True

    async def async_press(self) -> None:
        await self.entity_description.method(self.coordinator)
