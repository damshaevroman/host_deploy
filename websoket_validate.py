import ipaddress
import json
from pydantic import BaseModel, ValidationError, validator
from main import deploy
from deploy_host.deployhost import manager


class CheckPasswordValidator(BaseModel):
    login: str
    ip_address: ipaddress.IPv4Address
    port: int
    password: str
    sudo_password: str

    @validator('login')
    def check_login(cls, v):
        if v == '' or v is None:
            raise ValueError("login field cannot be empty")
        return v

    @validator('password')
    def check_password(cls, v):
        if v == '' or v is None:
            raise ValueError("password field cannot be empty")
        return v

    @validator('sudo_password')
    def check_sudo_password(cls, v):
        if v == '' or v is None:
            raise ValueError("sudo password field cannot be empty")
        return v

    @validator('ip_address')
    def check_ip_address(cls, v):
        if v == '' or v is None:
            raise ValueError('ip address field - cannot be empty')
        if not ipaddress.ip_address(v):
            raise ValueError('ip field should be IPv4')
        return v

    @validator('port')
    def check_port(cls, v):
        if v == '' or v is None:
            raise ValueError('port field - cannot be empty')
        if not isinstance(v, int):
            raise ValueError('port field - should integer')
        return v


async def check_data_password(data, websocket):
    try:
        CheckPasswordValidator(
            login=data["host_data"]["client_login"].strip(),
            ip_address=data["host_data"]["client_ip"].strip(),
            port=data["host_data"]["client_port"].strip(),
            password=data["host_data"]["client_password"].strip(),
            sudo_password=data["host_data"]["client_sudo_password"].strip()
        )
        return True
    except ValidationError as error:
        error = json.loads(error.json())
        await manager.send_personal_message(json.dumps({"task": "Alert", "result": True, "status": error}), websocket)


class InstallDataValidator(CheckPasswordValidator):
    hostname: str
    hotel_id: str
    uplink_interface: str

    @validator('hostname')
    def check_hostname(cls, v):
        if v == '' or v is None:
            raise ValueError("hostname field cannot be empty")
        return v

    @validator('hotel_id')
    def check_hotel_id(cls, v):
        if v == '' or v is None:
            raise ValueError("hostname field cannot be empty")
        return v

    @validator('uplink_interface')
    def check_uplink_interface(cls, v):
        if v == '' or v is None:
            raise ValueError("choose uplink interface interface")
        return v


async def check_install_data(data, websocket):
    try:
        InstallDataValidator(
            login=data["host_data"]["client_login"].strip(),
            ip_address=data["host_data"]["client_ip"].strip(),
            port=data["host_data"]["client_port"].strip(),
            password=data["host_data"]["client_password"].strip(),
            sudo_password=data["host_data"]["client_sudo_password"].strip(),
            hostname=data["host_data"]["hostname"].strip(),
            hotel_id=data["host_data"]["hotel_id"].strip(),
            uplink_interface=data["host_data"]["uplink_interface"].strip()
        )
        return True
    except ValidationError as error:
        error = json.loads(error.json())
        await manager.send_personal_message(json.dumps({"task": "Alert", "result": True, "status": error}), websocket)
#
#
class DhcpDataValidator(BaseModel):
    dhcp_network: ipaddress.IPv4Address
    dhcp_mask: ipaddress.IPv4Address
    dhcp_range_start: ipaddress.IPv4Address
    dhcp_range_end: ipaddress.IPv4Address
    dhcp_dns: ipaddress.IPv4Address
    domain_name: str
    dhcp_gateway: ipaddress.IPv4Address
    dhcp_broadcast: ipaddress.IPv4Address
    dhcp_eth: str

    @validator('dhcp_network')
    def check_dhcp_network(cls, v):
        if v == '' or v is None:
            raise ValueError('dhcp_network address field - cannot be empty')
        if not ipaddress.ip_address(v):
            raise ValueError('dhcp_network field should be IPv4')
        return v

    @validator('dhcp_range_start')
    def check_dhcp_range_start(cls, v):
        if v == '' or v is None:
            raise ValueError('dhcp_range_start address field - cannot be empty')
        if not ipaddress.ip_address(v):
            raise ValueError('dhcp_range_start field should be IPv4')
        return v

    @validator('dhcp_range_end')
    def check_dhcp_range_end(cls, v):
        if v == '' or v is None:
            raise ValueError('dhcp_range_end address field - cannot be empty')
        if not ipaddress.ip_address(v):
            raise ValueError('dhcp_range_end field should be IPv4')
        return v

    @validator('dhcp_dns')
    def check_dhcp_dns(cls, v):
        if v == '' or v is None:
            raise ValueError('dhcp_dns address field - cannot be empty')
        if not ipaddress.ip_address(v):
            raise ValueError('dhcp_dns field should be IPv4')
        return v

    @validator('domain_name')
    def check_domain_name(cls, v):
        if v == '' or v is None:
            raise ValueError('domain_name field - cannot be empty')
        return v

    @validator('dhcp_mask')
    def check_dhcp_mask(cls, v):
        if v == '' or v is None:
            raise ValueError('dhcp_mask address field - cannot be empty')
        if not ipaddress.ip_address(v):
            raise ValueError('dhcp_mask field should be IPv4')
        return v

    @validator('dhcp_gateway')
    def check_dhcp_gateway(cls, v):
        if v == '' or v is None:
            raise ValueError('dhcp_gateway address field - cannot be empty')
        if not ipaddress.ip_address(v):
            raise ValueError('dhcp_gateway field should be IPv4')
        return v

    @validator('dhcp_broadcast')
    def check_dhcp_broadcast(cls, v):
        if v == '' or v is None:
            raise ValueError('dhcp_broadcast address field - cannot be empty')
        if not ipaddress.ip_address(v):
            raise ValueError('dhcp_broadcast field should be IPv4')
        return v

    @validator('dhcp_eth')
    def check_dhcp_eth(cls, v):
        if v == '' or v is None:
            raise ValueError('choose dhcp interface')
        return v


async def check_dhcp_data(data, websocket):
    try:
        DhcpDataValidator(
            dhcp_network=data["dhcp"]["dhcp_network"].strip(),
            dhcp_mask=data["dhcp"]["dhcp_mask"].strip(),
            dhcp_range_start=data["dhcp"]["dhcp_range_start"].strip(),
            dhcp_range_end=data["dhcp"]["dhcp_range_end"].strip(),
            dhcp_dns=data["dhcp"]["dhcp_dns"].strip(),
            domain_name=data["dhcp"]["domain_name"].strip(),
            dhcp_gateway=data["dhcp"]["dhcp_gateway"].strip(),
            dhcp_broadcast=data["dhcp"]["dhcp_broadcast"].strip(),
            dhcp_eth=data["dhcp"]["dhcp_interface"].strip()
        )
        return True
    except ValidationError as error:
        error = json.loads(error.json())
        await manager.send_personal_message(json.dumps({"task": "Alert", "result": True, "status": error}),
                                            websocket)





class ServerIpValidator(BaseModel):
    ip_server: ipaddress.IPv4Address

    @validator('ip_server')
    def check_server_ip(cls, v):
        if v in deploy.server_ip:
            raise ValueError('Это ip адрес vpn сервера!!!')
        return v


async def validate_server_ip(data, websocket):
    try:
        ServerIpValidator(ip_server=data["host_data"]["client_ip"].strip())
        return True
    except ValidationError as error:
        error = json.loads(error.json())
        await manager.send_personal_message(json.dumps({"task": "Alert", "result": True, "status": error}), websocket)
