import asyncio
import ipaddress
import json
import os
import uvicorn as uvicorn
from aiofile import async_open
from fastapi import FastAPI
from starlette.websockets import WebSocket, WebSocketDisconnect
from deploy_host.deployhost import ConnectionDeployServer
from deploy_host.deployhost import manager
import websoket_validate
import configparser
from datetime import datetime



app = FastAPI()
config_settings = configparser.ConfigParser()
config_settings.read("deploy_settings.ini")
logpath = config_settings["LOG"]["logpath"]
server_ip = tuple(map(ipaddress.ip_address, config_settings["SERVER_IP"]["ip"].replace(' ', '').split(',')))
deploy = ConnectionDeployServer(logpath, server_ip)

if os.path.isfile(logpath):
    pass
else:
    with open(logpath, 'a') as file:
        file.write('Start log\n')


async def write_log(text):
    async with async_open(logpath, 'a+') as afp:
        await afp.write(f'{datetime.now()}: {text} \n')


async def packages_deploy(data, websocket):
    data_keys = data["install_list"].strip().split()
    for packages in data_keys:
        await asyncio.create_task(deploy.deploy_packeges(packages, data, websocket))


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):

    await manager.connect(websocket)
    try:
        while True:
            print("LOOP")
            data = await websocket.receive_json()
            if await websoket_validate.validate_server_ip(data, websocket):
                if data["task"] == "check_password":
                    if await websoket_validate.check_data_password(data, websocket) is True:
                        await deploy.check_sudo_pass(data, websocket)
                if data["task"] == "deploy_server":
                    if data["password_status"] == True:
                        if data["dhcp"]["dhcp_status"] == True:
                            if await websoket_validate.check_install_data(data, websocket) is True:
                                if await websoket_validate.check_dhcp_data(data, websocket) is True:
                                    await deploy.create_host_config(data)
                                    await asyncio.gather(deploy.create_install_tasks(data, websocket),
                                                         deploy.git_load(data, websocket))
                                    await manager.send_personal_message(
                                        json.dumps({"task": "finish", "result": True, "status": "Instalation finished check wrong point and reboot server"}), websocket)
                        else:
                            if await websoket_validate.check_install_data(data, websocket):
                                await deploy.create_host_config(data)
                                await asyncio.gather(deploy.create_install_tasks(data, websocket), deploy.git_load(data, websocket))
                                await manager.send_personal_message(
                                    json.dumps({"task": "finish", "result": True,
                                                "status": "Instalation finished check wrong point and reboot server"}),
                                    websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await asyncio.create_subprocess_shell(f'echo `date` - disconnect {client_id} >> {logpath}')



if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", port=5000)