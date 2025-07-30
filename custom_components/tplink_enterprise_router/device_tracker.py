import asyncio
import logging

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.components.device_tracker.config_entry import BaseTrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import translation
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TPLinkEnterpriseRouterCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    if not entry.data.get("enable_host_entity", False):
        return

    coordinator: TPLinkEnterpriseRouterCoordinator = hass.data[DOMAIN][entry.entry_id]
    tracker = DeviceTracker(hass, entry, coordinator, async_add_entities)

    """ Update the status of the old devices. """
    await tracker.init()
    await tracker.create_old_hosts()

    @callback
    def coordinator_updated():
        """Update the status of the devices."""
        asyncio.create_task(async_callback())

    async def async_callback():
        await tracker.update_hosts(coordinator.status['hosts_dict'])

    entry.async_on_unload(coordinator.async_add_listener(coordinator_updated))
    coordinator_updated()


class DeviceTracker:
    disconnected_text = "disconnected"
    connected_text = "connected"

    def __init__(self,
                 hass: HomeAssistant,
                 entry: ConfigEntry,
                 coordinator: TPLinkEnterpriseRouterCoordinator,
                 async_add_entities: AddEntitiesCallback
                 ) -> None:
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, version=1, key=f"{DOMAIN}_{entry.entry_id}")
        self.mac_list = []
        self.tracked: {str, TPLinkTracker} = {}
        self.coordinator = coordinator
        self.async_add_entities = async_add_entities

    async def init(self):
        self.mac_list = await self._get_tracked_mac_list()

        """ Setup translations """
        translations = await translation.async_get_translations(
            self.hass,
            self.hass.config.language,
            "component",
            [DOMAIN],
        )
        DeviceTracker.disconnected_text = translations.get(
            "component.tplink_enterprise_router.component.tplink_enterprise_router.entity.disconnected"
        )
        DeviceTracker.connected_text = translations.get(
            "component.tplink_enterprise_router.component.tplink_enterprise_router.entity.connected"
        )

    async def create_old_hosts(self):
        entities = []
        for mac in self.mac_list:
            entity = TPLinkTracker(mac, self.coordinator)
            entities.append(entity)
            self.tracked[mac] = entity
        self.async_add_entities(entities, False)

    async def update_hosts(self, host_dict: dict) -> None:
        # Get the tracked_devices setting from config options
        tracked_devices_str = self.entry.options.get("tracked_devices", "")
        
        # Filter host_dict if tracked_devices is specified
        if tracked_devices_str:
            # Parse the comma-separated MAC addresses
            tracked_macs = [mac.strip().lower() for mac in tracked_devices_str.split(",")]
            # Filter the host_dict to only include tracked devices
            host_dict = {mac: device for mac, device in host_dict.items() 
                        if mac.lower() in tracked_macs}
        
        new_mac_list = list(host_dict.keys())
        added = list(set(new_mac_list) - set(self.mac_list))
        removed = list(set(self.mac_list) - set(new_mac_list))

        merged_mac_list = list(set(self.mac_list + new_mac_list))
        self.mac_list = merged_mac_list
        await self._save_tracked_mac_list(merged_mac_list)

        entities = []
        for mac in added:
            entity = TPLinkTracker(mac, self.coordinator)
            entities.append(entity)
        self.async_add_entities(entities, False)

    async def _get_tracked_mac_list(self) -> list:
        data = await self._async_load_data()
        return data.get("mac_list", [])

    async def _save_tracked_mac_list(self, mac_list: list) -> None:
        await self._async_save_data({
            "mac_list": mac_list
        })

    async def _async_load_data(self) -> dict:
        data = await self.store.async_load()
        return data or {}

    async def _async_save_data(self, data: dict) -> None:
        await self.store.async_save(data)


class TPLinkTracker(CoordinatorEntity, BaseTrackerEntity):
    """Representation of network device."""

    def __init__(
            self,
            mac,
            coordinator: TPLinkEnterpriseRouterCoordinator,
    ) -> None:
        """Initialize the tracked device."""
        self.mac = mac
        self.device = coordinator.status['hosts_dict'].get(mac, {})
        entry_key = coordinator.entry.entry_id
        self.hass = coordinator.hass
        
        # Create a unique ID for the entity
        self._attr_unique_id = f"{DOMAIN}_host_{mac}_{entry_key}"
        self.entity_id = f"device_tracker.{DOMAIN}_host_{mac}_{entry_key}"
        
        # Define device info for the client device (not the router)
        self._attr_device_info = {
            "identifiers": {
                # Set MAC address as the primary identifier
                (DOMAIN, mac),
                # Add additional identifier that Nmap integration uses
                ("nmap_tracker", mac)
            },
            "name": self._get_device_name(),
            "manufacturer": self.device.get("manufacturer", "Unknown"),
            "model": self.device.get("model", "Network Client"),
            "via_device": (DOMAIN, coordinator.entry.entry_id),  # Link to the router
        }

        super().__init__(coordinator)
        
        # Register or update the device after initialization
        self._register_device()

    @property
    def is_connected(self) -> bool:
        """Return true if the client is connected to the network."""
        return self.device.get("mac") is not None

    @property
    def is_wired(self) -> bool:
        return self.device.get("type") == "wired"

    @property
    def source_type(self) -> str:
        """Return the source type of the client."""
        return SourceType.ROUTER

    def _get_device_name(self) -> str:
        """Get the name of the device."""
        # First try to get the hostname
        hostname = self.device.get("hostname") if self.device else None
        
        # Check if hostname is valid
        if hostname and hostname != '' and hostname != "anonymous" and hostname != "---":
            return hostname
        
        # If hostname is not valid, try to get the name from the device
        name = self.device.get("name") if self.device else None
        if name and name != '' and name != "anonymous" and name != "---":
            return name
            
        # If name is not valid, use MAC address
        if self.mac:
            return self.mac
            
        # Last resort - use a generic name
        return "Network Device"
            
    def _register_device(self) -> None:
        """Register the device and update its area if needed."""
        device_registry = dr.async_get(self.hass)
        
        # Check if device already exists
        existing_device = device_registry.async_get_device({(DOMAIN, self.mac)})
        
        # Prepare device info
        device_info = {
            "config_entry_id": self.coordinator.entry.entry_id,
            "identifiers": {(DOMAIN, self.mac)},
            "name": self._get_device_name(),
            "via_device": (DOMAIN, self.coordinator.entry.entry_id),
        }
        
        # Only set manufacturer and model if they don't already exist or if we have new info
        if not existing_device or not existing_device.manufacturer:
            device_info["manufacturer"] = self.device.get("manufacturer", "Unknown")
        
        if not existing_device or not existing_device.model:
            device_info["model"] = self.device.get("model", "Network Client")
        
        # Register or update the device
        device = device_registry.async_get_or_create(**device_info)
        _LOGGER.info("Registered device %s with ID: %s", self.mac, device.id)
        
        # Try to find matching Nmap device by MAC address
        nmap_devices = [
            d for d in device_registry.devices.values()
            if any(ident[0] == "nmap_tracker" and ident[1] == self.mac 
                  for ident in d.identifiers)
        ]
        
        if nmap_devices:
            nmap_device = nmap_devices[0]
            _LOGGER.info(
                "Found matching Nmap device for %s: %s (area_id: %s)", 
                self.mac, 
                nmap_device.id, 
                nmap_device.area_id
            )
            
            # If Nmap device has an area assigned, use that area for our device
            if nmap_device.area_id:
                device_registry.async_update_device(
                    device.id, 
                    area_id=nmap_device.area_id
                )
                _LOGGER.info(
                    "Updated device %s area to match Nmap device area: %s", 
                    self.mac, 
                    nmap_device.area_id
                )
            else:
                _LOGGER.info("Nmap device %s has no area assigned", nmap_device.id)
                
                # Try to get area from entity registry
                entity_registry = er.async_get(self.hass)
                nmap_entities = [
                    e for e in entity_registry.entities.values()
                    if e.device_id == nmap_device.id and e.area_id
                ]
                
                if nmap_entities:
                    area_id = nmap_entities[0].area_id
                    _LOGGER.info(
                        "Found area %s from Nmap entity %s", 
                        area_id, 
                        nmap_entities[0].entity_id
                    )
                    device_registry.async_update_device(
                        device.id, 
                        area_id=area_id
                    )
        else:
            _LOGGER.info("No matching Nmap device found for %s", self.mac)
            
            # Try to get area from entity registry directly
            entity_registry = er.async_get(self.hass)
            nmap_entities = [
                e for e in entity_registry.entities.values()
                if e.unique_id == self.mac and e.platform == "nmap_tracker" and e.area_id
            ]
            
            if nmap_entities:
                area_id = nmap_entities[0].area_id
                _LOGGER.info(
                    "Found area %s from Nmap entity with MAC %s", 
                    area_id, 
                    self.mac
                )
                device_registry.async_update_device(
                    device.id, 
                    area_id=area_id
                )
        
        # Store device ID for later use
        self.device_id = device.id
            
    @property
    def name(self) -> str:
        """Return the name of the client."""
        return self._get_device_name()

    @property
    def hostname(self) -> str:
        """Return the hostname of the client."""
        return self.device.get('hostname')

    @property
    def mac_address(self) -> str:
        """Return the mac address of the client."""
        return self.mac

    @property
    def state(self) -> str:
        if self.is_wired:
            return DeviceTracker.connected_text if self.is_connected else DeviceTracker.disconnected_text

        return self.device.get("ap_name", DeviceTracker.disconnected_text)

    @property
    def ip_address(self) -> str:
        """Return the ip address of the client."""
        return self.device.get("ip")

    @property
    def icon(self) -> str:
        if self.is_wired:
            return "mdi:lan-connect" if self.is_connected else "mdi:lan-disconnect"

        """Return device icon."""
        return "mdi:access-point-network" if self.is_connected else "mdi:access-point-network-off"

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {
            'hostname': self.hostname,
            'ip_address': self.ip_address,
            'mac_address': self.mac_address,
        }

    # @property
    # def data(self) -> dict[str, str]:
    #     return dict(self.extra_state_attributes.items() | {
    #         'hostname': self.hostname,
    #         'ip_address': self.ip_address,
    #         'mac_address': self.mac_address,
    #     }.items())

    @property
    def entity_registry_enabled_default(self) -> bool:
        return True

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.device = self.coordinator.status['hosts_dict'].get(self.mac, {})
        
        # Update device name if it has changed
        device_registry = dr.async_get(self.hass)
        if hasattr(self, 'device_id'):
            device = device_registry.async_get_device({(DOMAIN, self.mac)})
            new_name = self._get_device_name()
            if device and device.name != new_name:
                _LOGGER.info(
                    "Updating device %s name from '%s' to '%s'", 
                    self.mac, 
                    device.name, 
                    new_name
                )
                device_registry.async_update_device(
                    self.device_id,
                    name=new_name
                )
        
        # Check for Nmap device area changes and sync if needed
        self._sync_with_nmap_device()
        
        self.async_write_ha_state()
        
    def _sync_with_nmap_device(self) -> None:
        """Sync area with Nmap device if it exists."""
        if not hasattr(self, 'device_id'):
            _LOGGER.warning("Device ID not set for %s, cannot sync area", self.mac)
            return
            
        device_registry = dr.async_get(self.hass)
        
        # Get our device
        our_device = device_registry.async_get_device({(DOMAIN, self.mac)})
        if not our_device:
            _LOGGER.warning("Could not find our device for %s", self.mac)
            return
            
        _LOGGER.info(
            "Syncing area for device %s (current area: %s)", 
            self.mac, 
            our_device.area_id
        )
            
        # Find matching Nmap device
        nmap_devices = [
            d for d in device_registry.devices.values()
            if any(ident[0] == "nmap_tracker" and ident[1] == self.mac 
                  for ident in d.identifiers)
        ]
        
        area_id_to_set = None
        
        if nmap_devices:
            nmap_device = nmap_devices[0]
            _LOGGER.info(
                "Found matching Nmap device for %s: %s (area_id: %s)", 
                self.mac, 
                nmap_device.id, 
                nmap_device.area_id
            )
            
            # If Nmap device has an area assigned, use that area for our device
            if nmap_device.area_id:
                area_id_to_set = nmap_device.area_id
            else:
                _LOGGER.info("Nmap device %s has no area assigned", nmap_device.id)
                
                # Try to get area from entity registry
                entity_registry = er.async_get(self.hass)
                nmap_entities = [
                    e for e in entity_registry.entities.values()
                    if e.device_id == nmap_device.id and e.area_id
                ]
                
                if nmap_entities:
                    area_id_to_set = nmap_entities[0].area_id
                    _LOGGER.info(
                        "Found area %s from Nmap entity %s", 
                        area_id_to_set, 
                        nmap_entities[0].entity_id
                    )
        else:
            _LOGGER.info("No matching Nmap device found for %s", self.mac)
            
            # Try to get area from entity registry directly
            entity_registry = er.async_get(self.hass)
            nmap_entities = [
                e for e in entity_registry.entities.values()
                if e.unique_id == self.mac and e.platform == "nmap_tracker" and e.area_id
            ]
            
            if nmap_entities:
                area_id_to_set = nmap_entities[0].area_id
                _LOGGER.info(
                    "Found area %s from Nmap entity with MAC %s", 
                    area_id_to_set, 
                    self.mac
                )
        
        # Update device area if needed
        if area_id_to_set and area_id_to_set != our_device.area_id:
            _LOGGER.info(
                "Updating device %s area from %s to %s", 
                self.mac, 
                our_device.area_id, 
                area_id_to_set
            )
            device_registry.async_update_device(
                our_device.id, 
                area_id=area_id_to_set
            )