import voluptuous as vol
import logging
from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv
from homeassistant.core import callback
from .const import (
    DEFAULT_INSTANCE_NAME,
    DEFAULT_HOST,
    DEFAULT_TRACKED_DEVICES,
    DOMAIN,
)

class TPLinkEnterpriseRouterOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._config_entry = config_entry
        self._init_data = {}
        self._all_settings = {}

    async def async_step_init(self, user_input=None):
        data = self._config_entry.options or self._config_entry.data
        self._all_settings = dict(data)

        if user_input is not None:
            self._all_settings.update(user_input)
            
            # 如果不启用主机实体，则跳过设备选择步骤
            if not user_input.get("enable_host_entity", False):
                # 设置一个空的 tracked_devices，因为不会追踪任何设备
                self._all_settings["tracked_devices"] = ""
                
                # 保存所有设置
                data = self._config_entry.options or self._config_entry.data
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data={**data, **self._all_settings},
                    options={**data, **self._all_settings},
                )

                await self.hass.config_entries.async_reload(self._config_entry.entry_id)

                return self.async_create_entry(
                    title=self._all_settings["instance_name"], data=self._all_settings
                )
            
            # 进入设备选择步骤
            return await self.async_step_device_select()

        scheme = {
            vol.Required("instance_name", default=data.get("instance_name", DEFAULT_INSTANCE_NAME)): str,
            vol.Required("host", default=data.get("host", DEFAULT_HOST)): str,
            vol.Required("username", default=data.get("username", "")): str,
            vol.Required("password", default=data.get("password", "")): str,
            vol.Required("update_interval", default=data.get("update_interval", 30)): int,
            vol.Required("unique_id", default=data.get("unique_id", "")): str,
            vol.Required("enable_host_entity", default=data.get("enable_host_entity", True)): bool,
            vol.Required("unstable_check_count", default=data.get("unstable_check_count", 5)): int,
            vol.Required("unstable_check_time", default=data.get("unstable_check_time", 120)): int,
            vol.Required("enable_syslog_notify_event", default=data.get("enable_syslog_notify_event", False)): bool,
            vol.Required("enable_syslog_poll_event", default=data.get("enable_syslog_poll_event", False)): bool,
            vol.Required("syslog_event", default=data.get("syslog_event", "syslog_receiver_message")): str,
            vol.Required("enable_dedicated_event", default=data.get("enable_dedicated_event", False)): bool,
            vol.Required("enable_universal_event", default=data.get("enable_universal_event", False)): bool,
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(scheme))

    async def async_step_device_select(self, user_input=None):
        """处理设备选择步骤"""
        data = self._config_entry.options or self._config_entry.data
        
        # 获取协调器实例
        coordinator = self.hass.data[DOMAIN][self._config_entry.entry_id]
        
        # 获取所有设备列表
        devices = {}
        
        # 尝试从协调器中获取设备列表
        if coordinator:
            # 首先尝试从 coordinator.data 中获取
            if hasattr(coordinator, 'data') and coordinator.data and isinstance(coordinator.data, dict) and "hosts" in coordinator.data:
                for host in coordinator.data["hosts"]:
                    if "mac" in host and "hostname" in host:
                        mac = host["mac"]
                        name = host.get("hostname", "Unknown")
                        ip = host.get("ip", "")
                        devices[mac] = f"{name} ({mac}) - {ip}"
            
            # 如果 coordinator.data 中没有，尝试从 coordinator.status 中获取
            elif hasattr(coordinator, 'status') and coordinator.status and isinstance(coordinator.status, dict) and "hosts" in coordinator.status:
                for host in coordinator.status["hosts"]:
                    if "mac" in host and "hostname" in host:
                        mac = host["mac"]
                        name = host.get("hostname", "Unknown")
                        ip = host.get("ip", "")
                        devices[mac] = f"{name} ({mac}) - {ip}"
            
            # 如果还是没有，尝试强制更新协调器
            elif not devices:
                try:
                    # 尝试强制更新协调器
                    await coordinator.async_refresh()
                    
                    # 再次尝试从 coordinator.data 中获取
                    if hasattr(coordinator, 'data') and coordinator.data and isinstance(coordinator.data, dict) and "hosts" in coordinator.data:
                        for host in coordinator.data["hosts"]:
                            if "mac" in host and "hostname" in host:
                                mac = host["mac"]
                                name = host.get("hostname", "Unknown")
                                ip = host.get("ip", "")
                                devices[mac] = f"{name} ({mac}) - {ip}"
                    
                    # 如果 coordinator.data 中没有，尝试从 coordinator.status 中获取
                    elif hasattr(coordinator, 'status') and coordinator.status and isinstance(coordinator.status, dict) and "hosts" in coordinator.status:
                        for host in coordinator.status["hosts"]:
                            if "mac" in host and "hostname" in host:
                                mac = host["mac"]
                                name = host.get("hostname", "Unknown")
                                ip = host.get("ip", "")
                                devices[mac] = f"{name} ({mac}) - {ip}"
                except Exception as e:
                    _LOGGER = logging.getLogger(__name__)
                    _LOGGER.error(f"Error refreshing coordinator: {e}")
        
        # 如果没有设备，显示一个消息
        if not devices:
            devices = {"no_devices": "No devices found"}
        
        # 获取当前已选择的设备
        current_tracked_devices = data.get("tracked_devices", DEFAULT_TRACKED_DEVICES)
        default_devices = []
        
        # 如果当前设置是字符串格式，转换为列表
        if current_tracked_devices:
            default_devices = [mac.strip() for mac in current_tracked_devices.split(",") if mac.strip() in devices]
        
        if user_input is not None:
            # 将选择的设备转换为逗号分隔的字符串
            selected_devices = user_input.get("tracked_devices", [])
            tracked_devices_str = ",".join(selected_devices) if selected_devices else ""
            
            # 更新设置
            self._all_settings["tracked_devices"] = tracked_devices_str
            
            # 保存所有设置
            data = self._config_entry.options or self._config_entry.data
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data={**data, **self._all_settings},
                options={**data, **self._all_settings},
            )

            await self.hass.config_entries.async_reload(self._config_entry.entry_id)

            return self.async_create_entry(
                title=self._all_settings["instance_name"], data=self._all_settings
            )
        
        return self.async_show_form(
            step_id="device_select",
            data_schema=vol.Schema({
                vol.Optional(
                    "tracked_devices", 
                    default=default_devices
                ): cv.multi_select(devices),
            }),
            description_placeholders={
                "devices_count": str(len(devices)),
            },
        )