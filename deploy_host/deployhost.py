import asyncio
import aiofiles
import configparser
import json
import logging
import paramiko
from typing import List
from starlette.websockets import WebSocket


class ConnectManager:
    def __init__(self):
        self.active_connection: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        print("ACCEPT connection")
        self.active_connection.append(websocket)

    def disconnect(self, websocket: WebSocket):
        print("Disconnect connection")
        self.active_connection.remove(websocket)

    async def send_personal_message(self, message, websocket: WebSocket):
        print("send message")
        await websocket.send_text(message)

    async def broadcast(self, message):
        for connection in self.active_connection:
            await connection.receive_json(message)


manager = ConnectManager()
store_dict = {}


class ConnectionDeployServer():

    def __init__(self, logpath, server_ip):
        self.logpath = logpath
        self.server_ip = server_ip

    async def create_host_config(self, data):
        task = "config"
        print("start config")
        file = f'/tmp/{data["host_data"]["client_ip"]}_{data["host_data"]["hotel_id"]}_{task}'
        async with aiofiles.open(file, 'w') as file:
            await file.write(f'{data["host_data"]["client_ip"]}'
                             f' ansible_user={data["host_data"]["client_login"]}'
                             f' ansible_host={data["host_data"]["client_ip"]}'
                             f' ansible_port={data["host_data"]["client_port"]}'
                             f' ansible_password={data["host_data"]["client_password"]}'
                             f' ansible_become_pass={data["host_data"]["client_sudo_password"]}'
                             f' ansible_connection=paramiko ansible_python_interpreter=/usr/bin/python3')

        logging.info('Client host inventory create')
        store_dict[f'{data["host_data"]["client_ip"]}'] = file

    async def check_sudo_pass(self, data, websocket):
        """ check sudo passwords for access server """
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(data["host_data"]["client_ip"],
                        port=int(data["host_data"]["client_port"]),
                        timeout=10,
                        username=data["host_data"]["client_login"],
                        password=data["host_data"]["client_password"])
            stdin, stdout, stderr = ssh.exec_command("sudo -l", get_pty=True, timeout=8)
            stdin.write(data["host_data"]["client_sudo_password"] + '\n')
            stdin.flush()
            stdout = stdout.read()
            stdout = stdout.decode("utf-8")
            if '(ALL : ALL) ALL' in stdout:
                stdin, stdout, stderr = ssh.exec_command("ls /sys/class/net/", get_pty=True, timeout=8)
                stdout = stdout.read()
                stdout = stdout.decode("UTF-8").replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')
                int_data = stdout.split(' ')
                int_data = list(filter(None, int_data))
                await manager.send_personal_message(
                    json.dumps({"task": "check_password", "result": True, "status": "correct", "interfaces": int_data}),
                    websocket)
                await self.create_host_config(data)
            else:
                await manager.send_personal_message(
                    json.dumps({'task': "check_password", "result": False, "status": "incorrect", "interfaces": ""}),
                    websocket)
        except Exception as error:
            await asyncio.create_subprocess_shell(f'echo `date` - {data["host_data"]["client_ip"]} {error} >> {self.logpath}')
            errors = [{"loc": "no connect", "msg": str(error), "type": "connection_error"}]
            await manager.send_personal_message(
                json.dumps({'task': "Alert", "result": False, "status": errors, "interfaces": ""}), websocket)

    async def create_install_tasks(self, data, websocket):
        data_keys = data["install_list"].strip().split()
        for packages in data_keys:
            await asyncio.create_task(self.deploy_packeges(packages, data, websocket))

        if data["dhcp"]["dhcp_status"] == True:
            await asyncio.create_task(self.dhcp_deploy(data, websocket))
        await asyncio.create_task(self.nginx_deploy(data, websocket))
        await asyncio.create_task(self.crontab_deploy(data, websocket))
        await asyncio.create_task(self.systemctl_deploy(data, websocket))
        await asyncio.create_task(self.rclocal_deploy(data, websocket))
        await asyncio.create_task(self.add_backrsync(data, websocket))
        await asyncio.create_task(self.hostname_change(data, websocket))

    async def worker_and_messages(self, *args):
        ok_count, task, websocket, file, temp_host, data = args
        try:
            if task != "finish":
                start_playbook = await asyncio.create_subprocess_shell(
                    f'ansible-playbook {file.name} -i {temp_host.name}',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await start_playbook.communicate()
                stdout = stdout.decode("utf-8")
                print('STDOUT - ', stdout)
                if ok_count in stdout:
                    await asyncio.create_subprocess_shell(f'echo `date` - HotelID:{data["host_data"]["hotel_id"]} {task} completed >> {self.logpath}')
                    await asyncio.create_subprocess_shell(f'rm {file.name}')
                    await manager.send_personal_message(
                        json.dumps({'task': task, 'result': True, 'status': 'completed'}), websocket)
                else:
                    await asyncio.create_subprocess_shell(f'echo `date` - HotelID:{data["host_data"]["hotel_id"]} {task} failed >> {self.logpath}')
                    await asyncio.create_subprocess_shell(f'rm {file.name}')
                    await manager.send_personal_message(json.dumps({'task': task, 'result': False, 'status': 'broked'}),
                                                        websocket)
            else:
                await manager.send_personal_message(
                    json.dumps({'task': "finish", 'result': True, 'status': 'completed'}), websocket)
        except Exception as error:
            await asyncio.create_subprocess_shell(f'echo `date` - {str(data["host_data"]["hotel_id"]) + str(task) + str(error)} >> {self.logpath}')

    async def deploy_packeges(self, *args):
        task, data, websocket = args
        try:

            temp_host = store_dict[f'{data["host_data"]["client_ip"]}']
            """ Create config host file for using with playbook """
            await manager.send_personal_message(json.dumps({'task': f"{task}", 'result': True, 'status': 'processing'}),
                                                websocket)

            file = f'/tmp/{data["host_data"]["client_ip"]}_{data["host_data"]["hotel_id"]}_{task}'
            async with aiofiles.open(file, 'w') as file:
                await file.write(
                    f'---\n'
                    f'- hosts: all\n'
                    f'  gather_facts: no\n'
                    f'  tasks:\n'
                    f'  - name: install {task}\n'
                    f'    become: yes\n'
                    f'    apt: name={task}')
            await self.worker_and_messages("ok=1", task, websocket, file, temp_host, data)
        except Exception as error:
            await asyncio.create_subprocess_shell(f'echo `date` - {str(data["host_data"]["hotel_id"]) + str(task) + str(error)} >> {self.logpath}')

    async def dhcp_deploy(self, data, websocket):
        task = 'dhcp'
        temp_host = store_dict[f'{data["host_data"]["client_ip"]}']
        try:
            """get data from front and copy config dhcp to server"""
            await self.deploy_packeges("isc-dhcp-server", data, websocket)
            file_config = f'/tmp/{data["host_data"]["client_ip"]}_{data["host_data"]["hotel_id"]}_{task}_config'
            file = f'/tmp/{data["host_data"]["client_ip"]}_{data["host_data"]["hotel_id"]}_{task}'
            async with aiofiles.open(file_config, 'w') as file_config:
                await file_config.write(f'subnet {data["dhcp"]["dhcp_network"]};\n'
                                        f' netmask {data["dhcp"]["dhcp_mask"]};\n'
                                        f' range {data["dhcp"]["dhcp_range_start"]} {data["dhcp"]["dhcp_range_end"]};\n'
                                        f' option domain-name-servers {data["dhcp"]["dhcp_dns"]};\n'
                                        f' option domain-name {data["dhcp"]["domain_name"]};\n'
                                        f' option subnet-mask  {data["dhcp"]["dhcp_mask"]};\n'
                                        f' option routers  {data["dhcp"]["dhcp_gateway"]};\n'
                                        f' option broadcast-address {data["dhcp"]["dhcp_broadcast"]};\n'
                                        f' default-lease-time 600;\n'
                                        f' max-lease-time 7200;')
            async with aiofiles.open(file, 'w') as file:
                await file.write(
                    f'---\n- hosts: all\n'
                    f'  gather_facts: no\n'
                    f'  tasks:\n  - name: copy\n'
                    f'    become: yes\n    copy:\n'
                    f'       src: {file_config.name}\n'
                    f'       dest: /etc/dhcp/dhcpd.conf\n'
                    f'       owner: root\n'
                    f'       group: root\n'
                    f'  - name: added dhcp interface\n'
                    f'    become: yes\n'
                    f'    lineinfile:\n'
                    f'       path: /etc/default/isc-dhcp-server\n'
                    f'       regexp: INTERFACESv4=""\n'
                    f'       line: INTERFACESv4={data["dhcp"]["dhcp_interface"]}')
        except Exception as error:
            await asyncio.create_subprocess_shell(f'echo `date` - {str(data["host_data"]["hotel_id"]) + str(task) + str(error)} >> {self.logpath}')

        await self.worker_and_messages("ok=2", task, websocket, file, temp_host, data)
        await asyncio.create_subprocess_shell(f'rm {file_config.name}')

    async def nginx_deploy(self, data, websocket):
        """copy nginx config to server"""
        task = 'nginx_config'
        try:

            await manager.send_personal_message(json.dumps({'task': f"{task}", 'result': True, 'status': 'processing'}),
                                                websocket)
            temp_host = store_dict[f'{data["host_data"]["client_ip"]}']
            temp_host.seek(0)
            dest = '/etc/nginx/sites-available/default'
            file = f'/tmp/{data["host_data"]["client_ip"]}_{data["host_data"]["hotel_id"]}_{task}'
            async with aiofiles.open(file, 'w') as file:
                await file.write('server {\n'
                                 '        listen 80 default_server;\n'
                                 '        root /home/' + data["host_data"]["client_login"] + '/app;\n'
                                                                                             '        index index.html index.htm index.nginx-debian.html;\n'
                                                                                             '        server_name _;\n'
                                                                                             '        location / {\n'
                                                                                             '                try_files $uri $uri/ =404;\n'
                                                                                             '        }\n}')

            nginx_file = f'/tmp/{data["host_data"]["client_ip"]}_{data["host_data"]["hotel_id"]}_{task}'
            async with aiofiles.open(nginx_file, 'w') as nginx_file:
                await nginx_file.write('---\n- hosts: all\n'
                                       '  gather_facts: no\n'
                                       '  tasks:\n'
                                       '  - name: copy\n'
                                       '    become: yes\n'
                                       '    copy:\n'
                                       '       src: ' + file.name + '\n'
                                                                    '       dest: ' + dest + '\n'
                                                                                             '       owner: root\n'
                                                                                             '       group: root\n'
                                                                                             '       mode: "0755"\n')
            await self.worker_and_messages("ok=1", task, websocket, nginx_file, temp_host, data)
        except Exception as error:
            print(error, type(error))
            await asyncio.create_subprocess_shell(f'echo `date` - {str(data["host_data"]["hotel_id"]) + str(task) + str(error)} >> {self.logpath}')

    async def crontab_deploy(self, data, websocket):
        """ add to crontab script"""
        task = "crontab"
        try:

            await manager.send_personal_message(json.dumps({'task': f"{task}", 'result': True, 'status': 'processing'}),
                                                websocket)
            temp_host = store_dict[f'{data["host_data"]["client_ip"]}']
            file = f'/tmp/{data["host_data"]["client_ip"]}_{data["host_data"]["hotel_id"]}_{task}'
            async with aiofiles.open(file, 'w') as file:
                await file.write('---\n'
                                 '- hosts: all\n'
                                 '  tasks:\n'
                                 '  - cron:\n'
                                 '      name: app_syn\n'
                                 '      user: ' + data["host_data"]["client_login"] + '\n'
                                                                                      '      minute: "*/10"\n'
                                                                                      '      hour: "*"\n'
                                                                                      '      job: "/home/' +
                                 data["host_data"]["client_login"] + '/app/utils/download.sh -h ' +
                                 data["host_data"][
                                     "hotel_id"] + ' > /dev/null"\n'
                                                   '  - name: Create log app_sync\n'
                                                   '    become: true\n'
                                                   '    shell:\n'
                                                   '      cmd: echo "start" >> /var/log/app_sync.log\n'
                                                   '  - name: Access to app_sync.log\n'
                                                   '    become: true\n'
                                                   '    file:\n'
                                                   '      path: /var/log/app_sync.log\n'
                                                   '      owner: ' + data["host_data"]["client_login"] + '\n'
                                                                                                         '      group: ' +
                                 data["host_data"]["client_login"] + '\n'
                                                                     '      mode: "775"\n'
                                                                     '  - name: create app_sync file\n'
                                                                     '    become: true\n'
                                                                     '    file:\n'
                                                                     '         path: "/etc/logrotate.d/app_sync"\n'
                                                                     '         state: touch\n'
                                                                     '         owner: ' + data["host_data"][
                                     "client_login"] + '\n'
                                                       '         group: ' + data["host_data"]["client_login"] + '\n'
                                                                                                                f'         mode: "775"\n'
                                                                                                                f'- '
                                                                                                                f'name: copy conf to Logrotate to server\n '
                                                                                                                f'become: yes\n '
                                                                                                                f'    blockinfile:\n'
                                                                                                                f'path'
                                                                                                                f': '
                                                                                                                f'/etc/logrotate.d/app_sync\n '
                                                                                                                f'        block: |\n'
                                                                                                                f'                        /var/log/app_sync.log \n '
                                                                                                                f'                        weekly\n '
                                                                                                                f'                        missingok\n'
                                                                                                                f'                        rotate 8\n'
                                                                                                                f'                        compress\n'
                                                                                                                f'                        delaycompress\n'
                                                                                                                f'                        create 640  {data["client_login"]} {data["client_login"]} \n'
                                                                                                                '                        }')

            await self.worker_and_messages("ok=6", task, websocket, file, temp_host, data)
        except Exception as error:
            await asyncio.create_subprocess_shell(f'echo `date` - {str(data["host_data"]["hotel_id"]) + str(task) + str(error)} >> {self.logpath}')

    async def systemctl_deploy(self, data, websocket):
        """add configuration sysctl on server"""
        try:
            task = "systemctl"
            await manager.send_personal_message(json.dumps({'task': f"{task}", 'result': True, 'status': 'processing'}),
                                                websocket)
            temp_host = store_dict[f'{data["host_data"]["client_ip"]}']
            file = f'/tmp/{data["host_data"]["client_ip"]}_{data["host_data"]["hotel_id"]}_{task}'
            async with aiofiles.open(file, 'w') as file:
                await file.write('---\n- hosts: all\n'
                                 '  gather_facts: no\n'
                                 '  tasks:\n'
                                 '  - name: add ti sysctl.conf\n'
                                 '    become: yes\n'
                                 '    blockinfile:\n'
                                 '        path: /etc/sysctl.conf\n'
                                 '        block: |\n'
                                 '                net.ipv4.ip_forward=1\n'
                                 '                net.ipv4.conf.all.rp_filter=0\n'
                                 '                net.ipv4.conf.default.rp_filter=0\n'
                                 '                net.ipv4.conf.all.mc_forwarding=1\n'
                                 '                net.ipv4.conf.default.mc_forwarding=1')
            await self.worker_and_messages("ok=1", task, websocket, file, temp_host, data)
        except Exception as error:
            await asyncio.create_subprocess_shell(f'echo `date` - {error} >> {self.logpath}')

    async def rclocal_deploy(self, data, websocket):
        """ add to server service rc.local and config"""
        task = "rc_local"
        try:

            await manager.send_personal_message(json.dumps({'task': f"{task}", 'result': True, 'status': 'processing'}),
                                                websocket)
            if not data["dhcp"]["dhcp_status"]:
                multicast_interface = data["host_data"]["uplink_interface"]
            else:
                multicast_interface = data["dhcp"]["dhcp_interface"]
            temp_host = store_dict[f'{data["host_data"]["client_ip"]}']
            file = f'/tmp/{data["host_data"]["client_ip"]}_{data["host_data"]["hotel_id"]}_{task}'
            async with aiofiles.open(file, 'w') as file:
                await file.write(f'---\n'
                                 f'- hosts: all\n'
                                 f'  gather_facts: no\n'
                                 f'  tasks:\n'
                                 f'  - name: create rc.local\n'
                                 f'    become: true\n'
                                 f'    file:\n'
                                 f'         path: /etc/rc.local\n'
                                 f'         state: touch\n'
                                 f'         owner: root\n'
                                 f'         group: root\n'
                                 f'         mode: 0755\n'
                                 f'  - name: add rc.local to service\n'
                                 f'    become: yes\n'
                                 f'    blockinfile:\n'
                                 f'        path: /etc/rc.local\n'
                                 f'        marker: ""\n'
                                 f'        block: |\n'
                                 f'                #!/bin/bash\n'
                                 f'                /etc/init.d/pms start\n'
                                 f'                route add -net 224.0.0.0/4 dev {multicast_interface}\n'
                                 f'                iptables -w --table nat -A POSTROUTING -o {data["host_data"]["uplink_interface"]} -j MASQUERADE\n'
                                 f'                exit 0\n'
                                 f'  - name: create rc.local service file\n'
                                 f'    become: true\n'
                                 f'    file:\n'
                                 f'         path: /etc/systemd/system/rc-local.service\n'
                                 f'         state: touch\n'
                                 f'         owner: root\n'
                                 f'         group: root\n'
                                 f'         mode: 0755\n'
                                 f'  - name: add file to system\n'
                                 f'    become: yes\n'
                                 f'    blockinfile:\n'
                                 f'        path: /etc/systemd/system/rc-local.service\n'
                                 f'        marker: ""\n'
                                 f'        block: |\n'
                                 f'                [Unit]\n'
                                 f'                 Description=/etc/rc.local Compatibility\n'
                                 f'                 ConditionPathExists=/etc/rc.local\n'
                                 f'                [Service]\n'
                                 f'                 Type=forking\n'
                                 f'                 ExecStart=/etc/rc.local start\n'
                                 f'                 TimeoutSec=0\n'
                                 f'                 StandardOutput=tty\n'
                                 f'                 RemainAfterExit=yes\n'
                                 f'                [Install]\n'
                                 f'                 WantedBy=multi-user.target\n'
                                 f'  - name: enable rclocal\n'
                                 f'    become: yes\n'
                                 f'    shell: systemctl enable rc-local\n'
                                 f'  - name: Remove blank lines blockinfile put in\n'
                                 f'    become: yes\n'
                                 f'    lineinfile :\n'
                                 f'        path: /etc/rc.local\n'
                                 f'        state: absent\n'
                                 f'        regexp: "^$"\n'
                                 f'  - name: Remove blank lines blockinfile put in\n'
                                 f'    become: yes\n'
                                 f'    lineinfile :\n'
                                 f'        path: /etc/systemd/system/rc-local.service\n'
                                 f'        state: absent\n'
                                 f'        regexp: "^$"')
            await self.worker_and_messages("ok=7", task, websocket, file, temp_host, data)
        except Exception as error:
            await asyncio.create_subprocess_shell(f'echo `date` - {str(data["host_data"]["hotel_id"]) + str(task) + str(error)} >> {self.logpath}')

    async def add_backrsync(self, data, websocket):
        task = "backup_rsync"
        try:
            await manager.send_personal_message(json.dumps({'task': f"{task}", 'result': True, 'status': 'processing'}),
                                                websocket)
            config_settings = configparser.ConfigParser()
            config_settings.read("deploy_settings.ini")
            pubkey = config_settings["Config"]["path_hotbackup_key"]
            backupfiles = config_settings["Config"]["backup_client_files"]
            file = f'/tmp/{data["host_data"]["client_ip"]}_{data["host_data"]["hotel_id"]}_{task}'
            temp_host = store_dict[f'{data["host_data"]["client_ip"]}']
            async with aiofiles.open(file, 'w') as file:
                await file.write('---\n'
                                 '- hosts: all\n'
                                 '  tasks:\n'
                                 '  - cron:\n'
                                 '      name: Backtask\n'
                                 '      user: ' + data["host_data"]["client_login"] + '\n'
                                                                                      '      minute: "0"\n'
                                                                                      '      hour: "0"\n'
                                                                                      '      day: "23"\n'
                                                                                      '      job: "/home/' +
                                 data["host_data"]["client_login"] + '/backup_rsync/start.sh"\n'
                                                                     '  - name: Add the user hotbackup\n'
                                                                     '    become: yes\n'
                                                                     '    user:\n'
                                                                     '      name: hotbackup\n'
                                                                     '      shell: /bin/bash\n'
                                                                     '      append: yes\n'
                                                                     '  - name: make direcotry\n'
                                                                     '    become: yes\n'
                                                                     '    file:\n'
                                                                     '      path: "/home/hotbackup/.ssh"\n'
                                                                     '      state: directory\n'
                                                                     '  - name: create empty file\n'
                                                                     '    become: yes\n'
                                                                     '    file:\n'
                                                                     '      path: "/home/hotbackup/.ssh/authorized_keys"\n'
                                                                     '      state: touch\n'
                                                                     '  - name: put pubkey\n'
                                                                     '    become: yes\n'
                                                                     '    copy:\n'
                                                                     '      src: ' + pubkey + '\n'
                                                                                              '      dest: /home/hotbackup/.ssh/authorized_keys\n'
                                                                                              '      owner: hotbackup\n'
                                                                                              '      group: hotbackup\n'
                                                                                              '      mode: 0600\n'
                                                                                              '  - name: copy backuper\n'
                                                                                              '    become: yes\n'
                                                                                              '    copy:\n'
                                                                                              '      src: ' + backupfiles + '\n'
                                                                                                                            '      dest: /home/' +
                                 data["host_data"]["client_login"] + '/backup_rsync\n'
                                                                     '      owner: hotbackup\n'
                                                                     '      group: hotbackup\n'
                                                                     '      mode: 0755')
            await self.worker_and_messages("ok=7", task, websocket, file, temp_host, data)
        except Exception as error:
            await asyncio.create_subprocess_shell(f'echo `date` - {str(data["host_data"]["hotel_id"]) + str(task) + str(error)} >> {self.logpath}')

    async def hostname_change(self, data, websocket):
        task = 'change_hostname'
        try:
            temp_host = store_dict[f'{data["host_data"]["client_ip"]}']
            await manager.send_personal_message(json.dumps({'task': f"{task}", 'result': True, 'status': 'processing'}),
                                                websocket)
            if data["host_data"]["hostname"].strip() != "":
                file = f'/tmp/{data["host_data"]["client_ip"]}_{data["host_data"]["hotel_id"]}_hostname'
                print('THIS is hostname', data["host_data"]["hostname"])
                async with aiofiles.open(file, 'w') as file:
                    await file.write(f'---\n- hosts: all\n'
                                     f'  gather_facts: no\n'
                                     f'  tasks:\n'
                                     f'  - name: /etс/cloud/cloud.cfg\n'
                                     f'    become: yes\n'
                                     f'    lineinfile:\n'
                                     f'        path: /etc/cloud/cloud.cfg\n'
                                     f'        regexp: "preserve_hostname:"\n'
                                     f'        line: "preserve_hostname: true"\n'
                                     f'  - name: change hostname\n'
                                     f'    become: yes\n'
                                     f'    shell: sudo hostnamectl set-hostname {data["host_data"]["hostname"]}')
                await self.worker_and_messages("ok=2", task, websocket, file, temp_host, data)
        except Exception as error:
            await asyncio.create_subprocess_shell(f'echo `date` - {str(data["host_data"]["hotel_id"]) + str(task) + str(error)} >> {self.logpath}')

    async def git_load(self, data, websocket):
        """ Download from bitbuchet """
        try:
            config = configparser.ConfigParser()
            config.read("deploy_settings.ini")
            task = "tv"
            temp_host = store_dict[f'{data["host_data"]["client_ip"]}']
            file = f'/tmp/{data["host_data"]["client_ip"]}_{data["host_data"]["hotel_id"]}_tv'
            if "tv" in data["git"]:
                await manager.send_personal_message(json.dumps({'task': f"{task}", 'result': True, 'status': 'processing'}),
                                                    websocket)
                async with aiofiles.open(file, 'w') as file:
                    await file.write(f'---\n'
                                     f'- hosts: all\n'
                                     f'  gather_facts: no\n'
                                     f'  tasks:\n'
                                     f'  - name: install appTV\n'
                                     f'    git:\n'
                                     f'      repo: "https://{config["GIT"]["git_login"]}:{config["GIT"]["git_password"]}@bitbucket.org/{data["git_login"]}/tv.git"\n'
                                     f'      dest: /home/{data["host_data"]["client_login"]}/app\n'
                                     f'      version: develop\n'
                                     f'  - name: create directory c\n'
                                     f'    file:\n'
                                     f'       path: /home/{data["host_data"]["client_login"]}/{data["client_login"]}/c\n'
                                     f'       state: directory\n'
                                     f'  - name: Copy config.js\n'
                                     f'    shell:\n'
                                     f'       cmd: cp /home/{data["host_data"]["client_login"]}/{data["client_login"]}/tv/config_def.js /home/{data["host_data"]["client_login"]}/app/tv/config.js')
                await self.worker_and_messages("ok=3", task, websocket, file, temp_host, data)
            if 'pms' in data["git"]:
                task = "pms"
                await manager.send_personal_message(json.dumps({'task': f"{task}", 'result': True, 'status': 'processing'}),
                                                    websocket)
                file = f'{data["host_data"]["client_ip"]}_{data["host_data"]["hotel_id"]}_pms'
                async with aiofiles.open(file, 'w') as file:
                    await file.write(f'---\n'
                                     f'- hosts: all\n'
                                     f'  gather_facts: no\n'
                                     f'  tasks:\n'
                                     f'  - name: install pms\n'
                                     f'    git:\n'
                                     f'      repo: "https://{config["GIT"]["git_login"]}:{config["GIT"]["git_password"]}@bitbucket.org/{data["git_login"]}/pms.git"\n'
                                     f'      dest: /home/{data["host_data"]["client_login"]}/pms\n'
                                     f'  - name: Install pms\n'
                                     f'    become: yes\n'
                                     f'    command: python3 setup.py install --force\n'
                                     f'    args:\n'
                                     f'       chdir: /home/{data["host_data"]["client_login"]}/pms/\n'
                                     f'  - name: added hotel number to pms\n'
                                     f'    become: yes\n'
                                     f'    lineinfile:\n'
                                     f'        path: /etc/pms.cfg\n'
                                     f'        regexp: "^hotel_id = "\n'
                                     f'        line: "hotel_id = {data["host_data"]["hotel_id"]}"')
                await self.worker_and_messages("ok=3", task, websocket, file, temp_host, data)
        except Exception as error:
            await asyncio.create_subprocess_shell(f'echo `date` - GIT {error} >> {self.logpath}')
