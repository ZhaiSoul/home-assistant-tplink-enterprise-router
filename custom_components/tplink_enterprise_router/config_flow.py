import voluptuous as vol
import logging
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from .const import (
    DOMAIN,
    DEFAULT_INSTANCE_NAME,
    DEFAULT_HOST,
    DEFAULT_TRACKED_DEVICES,
)
from .client import TPLinkEnterpriseRouterClient


class TPLinkEnterpriseRouterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    _user_input = None
    _devices = {}
    _temp_client = None
    
    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            if not user_input.get("host"):
                errors["host"] = "host_required"
            if not user_input.get("username"):
                errors["username"] = "username_required"
            if not user_input.get("password"):
                errors["password"] = "password_required"

            if not errors:
                self._user_input = user_input
                
                # 如果不启用主机实体，则跳过设备选择步骤
                if not user_input.get("enable_host_entity", False):
                    # 设置一个空的 tracked_devices，因为不会追踪任何设备
                    user_input["tracked_devices"] = ""
                    return self.async_create_entry(
                        title=user_input["instance_name"],
                        data=user_input,
                    )
                
                # 创建临时客户端获取设备列表
                try:
                    self._temp_client = TPLinkEnterpriseRouterClient(
                        self.hass,
                        user_input["host"],
                        user_input["username"],
                        user_input["password"]
                    )
                    
                    # 获取设备列表
                    status = await self._temp_client.get_status()
                    
                    if status and "hosts" in status:
                        for host in status["hosts"]:
                            if "mac" in host and "hostname" in host:
                                mac = host["mac"]
                                name = host.get("hostname", "Unknown")
                                ip = host.get("ip", "")
                                self._devices[mac] = f"{name} ({mac}) - {ip}"
                except Exception as e:
                    _LOGGER = logging.getLogger(__name__)
                    _LOGGER.error(f"Error getting device list: {e}")
                
                # 进入设备选择步骤
                return await self.async_step_device_select()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("instance_name", default=DEFAULT_INSTANCE_NAME): str,
                vol.Required("host", default=DEFAULT_HOST): str,
                vol.Required("username"): str,
                vol.Required("password"): str,
                vol.Required("update_interval", default=30): int,
                vol.Optional("unique_id", default="default"): str,
                vol.Required("enable_host_entity", default=True): bool,
                vol.Required("unstable_check_count", default=5): int,
                vol.Required("unstable_check_time", default=120): int,
                vol.Required("enable_syslog_notify_event", default=False): bool,
                vol.Required("enable_syslog_poll_event", default=False): bool,
                vol.Required("syslog_event", default="syslog_receiver_message"): str,
                vol.Required("enable_dedicated_event", default=False): bool,
                vol.Required("enable_universal_event", default=True): bool,
            }),
            errors=errors
        )

    async def async_step_device_select(self, user_input=None):
        """处理设备选择步骤"""
        errors = {}
        
        # 如果没有设备，显示一个消息
        if not self._devices:
            self._devices = {"no_devices": "No devices found"}
        
        if user_input is not None:
            # 将选择的设备转换为逗号分隔的字符串
            tracked_devices = ",".join(user_input.get("tracked_devices", []))
            
            # 将选择的设备添加到用户输入中
            self._user_input["tracked_devices"] = tracked_devices
            
            # 创建配置条目
            return self.async_create_entry(
                title=self._user_input["instance_name"],
                data=self._user_input,
            )
        
        # 获取当前已选择的设备
        current_tracked_devices = DEFAULT_TRACKED_DEVICES.split(",") if DEFAULT_TRACKED_DEVICES else []
        
        # 如果只有一个设备且其键为 "no_devices"，则禁用多选
        is_multi_select = not (len(self._devices) == 1 and "no_devices" in self._devices)
        
        return self.async_show_form(
            step_id="device_select",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "tracked_devices",
                        default=current_tracked_devices,
                    ): cv.multi_select(self._devices) if is_multi_select else str,
                }
            ),
            errors=errors,
            description_placeholders={
                "note": "选择要追踪的设备。如果不选择任何设备，将追踪所有设备。"
            },
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        from .options_flow import TPLinkEnterpriseRouterOptionsFlowHandler
        return TPLinkEnterpriseRouterOptionsFlowHandler(config_entry)