#!/bin/python3
# -*- coding: utf-8 -*-
'''
###############################################################################
##
## 88        88 88
## 88        88 88
## 88        88 88
## 88        88 88,dPPYba,   ,adPPYba,   ,adPPYba,
## 88        88 88P'    "8a a8"     "8a a8P_____88
## 88        88 88       d8 8b       d8 8PP"""""""
## Y8a.    .a8P 88b,   ,a8" "8a,   ,a8" "8b,   ,aa
##  `"Y8888Y"'  `"8Ybbd8"'   `"YbbdP"'   `"Ybbd8"'
##
###############################################################################
## © Copyright 2023 Uboe S.A.S
###############################################################################
This is the main program, it creates a KeybasBot instance and starts it.
Heavily inspired by :
    - https://github.com/Arksine/moontest/blob/master/scripts/unix_socket_test.py
    - https://github.com/keybase/pykeybasebot/blob/master/examples/1_pingpong.py
'''
from __future__ import annotations
import os
import sys
import argparse
import ast
import asyncio
import pathlib
import json
import shutil
import textwrap
import re
import requests
import datetime
from PIL import Image
import pykeybasebot.types.chat1 as chat1
from pykeybasebot import Bot

from typing import Any, Dict, List, Optional

this_dir = os.path.dirname(os.path.abspath(__file__))

SOCKET_LIMIT = 20 * 1024 * 1024
MENU = [
    "List API Request Presets",
    "Select API Request Preset",
    "Manual API Entry",
    "Start Notification View",
]
LISTEN_OPTIONS = {
    "filter-channels": [
        {'name' : 'printhive', 'public' : None, 'members_type' : 'team', 'topic_type' : 'chat', 'topic_name' : "printfarm"},
        {'name' : 'printhive', 'public' : None, 'members_type' : 'team', 'topic_type' : 'chat', 'topic_name' : os.uname().nodename}
    ]
}
ALLOWED_USERS = json.load(open(os.path.join(this_dir, '..', 'common', 'allowed_users.json'), 'r'))

class KeybaseBot:
    def __init__(
        self, sockpath: pathlib.Path, presets: List[Dict[str, Any]], paperkey: str, logger
    ) -> None:
        '''
        The class represents a Keybase bot that connects to Moonraker via a Unix Socket and to keybase via the keybase bot API.
        It is used to send messages to the keybase channel and to send commands or receive notifications from Moonraker.
        @param sockpath: Path to the Unix Socket
        @param presets: List of API presets to send to Moonraker
        @param paperkey: Keybase paperkey
        @param logger: Logger instance
        '''
        self.logger = logger
        # get paperkey from file
        with open(paperkey, 'r') as file:
            self.paperkey = file.read().replace('\n', '')

        # if pidfile exists use it to connect the bot
        self._loop = None
        if os.path.isfile('/run/user/1000/keybase/keybased.pid'):
            self.bot = Bot(
                username="uboe_bot", paperkey=self.paperkey, handler=self, pid_file='/run/user/1000/keybase/keybased.pid', loop=self._loop
            )
            self.logger.info("PID file exists")
        else:
            self.bot = Bot(
                username="uboe_bot", paperkey=self.paperkey, handler=self, loop=self._loop
            )
        self.printfarmchannel = chat1.ChatChannel(
            name=LISTEN_OPTIONS['filter-channels'][0]['name'],
            public=LISTEN_OPTIONS['filter-channels'][0]['public'],
            members_type=LISTEN_OPTIONS['filter-channels'][0]['members_type'],
            topic_type=LISTEN_OPTIONS['filter-channels'][0]['topic_type'],
            topic_name=LISTEN_OPTIONS['filter-channels'][0]['topic_name']
        )
        self.printerchannel = chat1.ChatChannel(
            name=LISTEN_OPTIONS['filter-channels'][1]['name'],
            public=LISTEN_OPTIONS['filter-channels'][1]['public'],
            members_type=LISTEN_OPTIONS['filter-channels'][1]['members_type'],
            topic_type=LISTEN_OPTIONS['filter-channels'][1]['topic_type'],
            topic_name=LISTEN_OPTIONS['filter-channels'][1]['topic_name']
        )
        self.hostname = os.uname().nodename
        self.sockpath = sockpath
        self.api_presets = presets
        self.pending_req: Dict[str, Any] = {}
        self.connected = False
        self.kb_fd = sys.stdin.fileno()
        self.out_fd = sys.stdout.fileno()
        os.set_blocking(self.kb_fd, False)
        os.set_blocking(self.out_fd, False)
        self.kb_buf = b""
        self.kb_fut: Optional[asyncio.Future[str]] = None
        self.pending_reqs: Dict[int, asyncio.Future[Dict[str, Any]]] = {}
        self.print_lock = asyncio.Lock()
        self.mode: int = 0
        self.need_print_help: bool = True
        self.print_notifications: bool = False
        self.manual_entry: Dict[str, Any] = {}
        self.max_method_len: int = max(
            [len(p.get("method", "")) for p in self.api_presets]
        )
        self.snap_file = os.path.join(this_dir, '..', 'tmp', 'snapshot.jpeg')
        self.header_message = textwrap.dedent(f"""
            * Hostname: `{self.hostname}` *
            """)
        self.footer_message = textwrap.dedent(f"""
            * ============================================= *
            """)

    async def __call__(self, bot, chat_event : chat1.Message ):
        '''
        Handler for keybase bot. It is called when a message is received on the keybase channel.
        @param bot: Keybase bot instance
        @param chat_event: Keybase chat event
        '''
        if chat_event.msg.content.type_name != chat1.MessageTypeStrings.TEXT.value:
            return

        # list all
        if chat_event.msg.sender.username == bot.username:
            return

        channel = chat_event.msg.channel
        chat_msg = chat_event.msg.content.text.body
        bot_command = re.match(r'(^/uboe_bot)', chat_msg)
        debug = False
        msg = "Command not recognized. Try `/uboe_bot help`"
        match = re.match(r'(^/uboe_bot)\s+(.*$)', chat_msg)
        if bot_command :
            file = None
            if re.match(r'(^/uboe_bot)\s+(debug)\s+(.*$)', chat_msg) :
                if chat_event.msg.sender.username in ALLOWED_USERS:
                    match = re.match(r'(^/uboe_bot)\s+debug\s+(.*$)', chat_msg)
                    debug = True
                else :
                    msg = "You are not allowed to enable debug mode"

            if match :
                if len(match.groups()) == 2 :
                    command = match.group(2)
                    # if "help" in command :
                    if command == "help":
                        msg = textwrap.dedent("""
                            Hello there! I'm uboe_bot, a bot for print farm management.
                            I can help you with the following commands:
                                `help` - this help message
                                `status` - display the printer's status
                                `snapshot` - display the printer's snapshot
                                `emergency_stop` - emergency stop
                                `camera id=<int> rotate=<int>` - configure camera
                                `debug` - enable debug mode (followed by the command you want to debug)
                                          Please run `/uboe_bot debug commands` for more info and available commands
                            More commands coming soon!
                        """)
                    #if command == "status" :
                    elif command == "status" :
                        msg = await self.kb_status_msg()
                        file = self.snap_file
                    #if command == "snapshot" :
                    elif command == "snapshot" :
                        msg = "Requested snapshot:"
                        await self.get_snapshot()
                        file = self.snap_file
                    # configure camera (/uboe_bot camera id=0 rotate=180)
                    elif re.match(r'(^camera)', command) :
                        # unpack command arguments without leading /uboe_bot camera
                        arguments = re.match(r'.*?id=(\d+)\s+rotate=(\d+)', command)
                        if arguments :
                            if len(arguments.groups()) == 2 :
                                id = arguments.group(1)
                                rotate = arguments.group(2)
                                # save configuration into a json file
                                if not os.path.exists(os.path.join(this_dir, '..', 'config')):
                                    os.makedirs(os.path.join(this_dir, '..', 'config'))
                                with open(os.path.join(this_dir, '..', 'config', 'camera.json'), 'w') as config_file:
                                    json.dump({'id': id, 'rotate': rotate}, config_file)
                                msg = "Camera settings updated"

                            else :
                                msg = "Malformed command received. Try `/uboe_bot help`"
                        else :
                            msg = "Malformed command received. Try `/uboe_bot help`"

                    elif command == "emergency_stop" :
                        msg = "Emergency stop requested"
                        self.manual_entry = {
                            "method": "printer.emergency_stop",
                            "params": {}
                        }
                        self.logger.debug(f"Sending : {self.manual_entry}")
                        ret = await self._send_manual_request()
                        self.logger.debug(f"Response: {ret}")
                        self.manual_entry = {}

                    # if "🌴ping🌴" == command :
                    elif "🌴ping🌴" == command :
                        msg = "🍹PONG!🍹"
                    else :
                        if debug :
                            if command == "moonraker" :
                                # check if socket is connected
                                if self.connected :
                                    msg = "Moonraker is connected"
                                else :
                                    msg = "Moonraker is not connected"
                            elif command == "reconnect_moonraker" :
                                # check if socket is connected
                                if self.connected :
                                    msg = "Moonraker is already connected"
                                else :
                                    await self._connect()
                                    msg = "Moonraker reconnected"
                            elif command == "emulate_job" :
                                message = f"Emulated job started"
                                self._loop.create_task(self.pending_status_message(message))
                            elif command == "commands" : # list all commands
                                msg = textwrap.dedent("""
                                    Available commands:
                                        `moonraker` - check if moonraker is connected
                                        `reconnect_moonraker` - reconnect to moonraker
                                        `emulate_job` - emulate a job
                                        `commands` - list all debug commands
                                """)

                else :
                    msg = "Malformed command received. Try `/uboe_bot help`"
            else :
                msg = "Not command received. Try `/uboe_bot help`"

            if not file:
                await bot.chat.send(channel, self.header_message + msg + self.footer_message)
            else :
                if not os.path.exists(file):
                    await bot.chat.send(channel, self.header_message + msg + self.footer_message)
                else :
                    await bot.chat.attach(channel, file, self.header_message + msg + self.footer_message)

    async def _process_stream(
            self, reader: asyncio.StreamReader
        ) -> None:
        '''
        Process request and notifications from Moonraker
        @param reader: Asyncio stream reader

        When status changes, Moonraker sends a notification to the Unix Socket.
        '''
        errors_remaining: int = 10
        while not reader.at_eof():
            try:
                data = await reader.readuntil(b'\x03')
                decoded = data[:-1].decode(encoding="utf-8")
                item: Dict[str, Any] = json.loads(decoded)
            except (ConnectionError, asyncio.IncompleteReadError):
                break
            except asyncio.CancelledError:
                raise
            except Exception:
                errors_remaining -= 1
                if not errors_remaining or not self.connected:
                    break
                continue
            errors_remaining = 10
            if "id" in item:
                fut = self.pending_reqs.pop(item["id"], None)
                if fut is not None:
                    fut.set_result(item)
            elif self.print_notifications:
                self._loop.create_task(self.print(f"Notification: {item}\n"))
            # CANCELLED: {'jsonrpc': '2.0', 'method': 'notify_history_changed', 'params': [{'action': 'finished', 'job': {'end_time': 1695313459.7578163, 'filament_used': 0.0, 'filename': 'ROY_cover_PLA_1h26m.gcode', 'metadata': {'size': 2417349, 'modified': 1695304875.0769384, 'uuid': '2488b052-ad04-4de3-8158-16acd85f273f', 'slicer': 'OrcaSlicer', 'slicer_version': '1.7.0', 'gcode_start_byte': 24778, 'gcode_end_byte': 2402984, 'layer_count': 10, 'object_height': 3.0, 'estimated_time': 5132, 'nozzle_diameter': 0.4, 'layer_height': 0.3, 'first_layer_height': 0.3, 'first_layer_extr_temp': 220.0, 'first_layer_bed_temp': 60.0, 'chamber_temp': 0.0, 'filament_name': 'Rosa 3D PLA Silk Rainbow', 'filament_type': 'PLA', 'filament_used': '25.59', 'filament_total': 8509.96, 'filament_weight_total': 25.59, 'thumbnails': [{'width': 32, 'height': 24, 'size': 707, 'relative_path': '.thumbs/ROY_cover_PLA_1h26m-32x32.png'}, {'width': 160, 'height': 120, 'size': 2347, 'relative_path': '.thumbs/ROY_cover_PLA_1h26m-160x120.png'}]}, 'print_duration': 0.0, 'status': 'cancelled', 'start_time': 1695313285.310055, 'total_duration': 174.37510105301044, 'job_id': '00000F', 'exists': True}}]}
            # COMPLETED: {'jsonrpc': '2.0', 'method': 'notify_history_changed', 'params': [{'action': 'finished', 'job': {'end_time': 1695312127.3214107, 'filament_used': 8545.623679997632, 'filename': 'ROY_cover_PLA_1h26m.gcode', 'metadata': {'size': 2417349, 'modified': 1695304875.0769384, 'uuid': '2488b052-ad04-4de3-8158-16acd85f273f', 'slicer': 'OrcaSlicer', 'slicer_version': '1.7.0', 'gcode_start_byte': 24778, 'gcode_end_byte': 2402984, 'layer_count': 10, 'object_height': 3.0, 'estimated_time': 5132, 'nozzle_diameter': 0.4, 'layer_height': 0.3, 'first_layer_height': 0.3, 'first_layer_extr_temp': 220.0, 'first_layer_bed_temp': 60.0, 'chamber_temp': 0.0, 'filament_name': 'Rosa 3D PLA Silk Rainbow', 'filament_type': 'PLA', 'filament_used': '25.59', 'filament_total': 8509.96, 'filament_weight_total': 25.59, 'thumbnails': [{'width': 32, 'height': 24, 'size': 707, 'relative_path': '.thumbs/ROY_cover_PLA_1h26m-32x32.png'}, {'width': 160, 'height': 120, 'size': 2347, 'relative_path': '.thumbs/ROY_cover_PLA_1h26m-160x120.png'}]}, 'print_duration': 6051.890782442992, 'status': 'completed', 'start_time': 1695305884.7087114, 'total_duration': 6242.467836786003, 'job_id': '00000E', 'exists': True}}]}
            # START: {'jsonrpc': '2.0', 'method': 'notify_history_changed', 'params': [{'action': 'added', 'job': {'end_time': None, 'filament_used': 0.0, 'filename': 'ROY_cover_PLA_1h26m.gcode', 'metadata': {'size': 2417349, 'modified': 1695304875.0769384, 'uuid': '2488b052-ad04-4de3-8158-16acd85f273f', 'slicer': 'OrcaSlicer', 'slicer_version': '1.7.0', 'gcode_start_byte': 24778, 'gcode_end_byte': 2402984, 'layer_count': 10, 'object_height': 3.0, 'estimated_time': 5132, 'nozzle_diameter': 0.4, 'layer_height': 0.3, 'first_layer_height': 0.3, 'first_layer_extr_temp': 220.0, 'first_layer_bed_temp': 60.0, 'chamber_temp': 0.0, 'filament_name': 'Rosa 3D PLA Silk Rainbow', 'filament_type': 'PLA', 'filament_used': '25.59', 'filament_total': 8509.96, 'filament_weight_total': 25.59, 'thumbnails': [{'width': 32, 'height': 24, 'size': 707, 'relative_path': '.thumbs/ROY_cover_PLA_1h26m-32x32.png'}, {'width': 160, 'height': 120, 'size': 2347, 'relative_path': '.thumbs/ROY_cover_PLA_1h26m-160x120.png'}]}, 'print_duration': 0.0, 'status': 'in_progress', 'start_time': 1695313479.608397, 'total_duration': 0.049926147010410205, 'job_id': '000010', 'exists': True}}]}
            message = None
            to_printfarm = False
            # check the status of the job
            if 'method' in item and item['method'] in  ['notify_history_changed', 'notify_check_failure'] :
                self.logger.debug(f"Notification: {item}\n")

            if 'method' in item and item['method'] == 'notify_history_changed' :

                if item['params'][0]['action'] == 'finished' and item['params'][0]['job']['status'] == 'completed':
                    message = f"Job {item['params'][0]['job']['filename']} completed"
                    # remove thumbnail files
                    if os.path.exists(os.path.join(this_dir, '..', 'tmp', 'thumbail_*.png')):
                        shutil.rmtree(os.path.join(this_dir, '..', 'tmp', 'thumbail_*.png'))

                # job cancelled
                elif item['params'][0]['action'] == 'finished' and item['params'][0]['job']['status'] == 'cancelled':
                    message = f"Job {item['params'][0]['job']['filename']} cancelled"
                    # remove thumbnail files
                    if os.path.exists(os.path.join(this_dir, '..', 'tmp', 'thumbail_*.png')):
                        shutil.rmtree(os.path.join(this_dir, '..', 'tmp', 'thumbail_*.png'))

                # job paused
                elif item['params'][0]['action'] == 'finished' and item['params'][0]['job']['status'] == 'paused':
                    message = f"Job {item['params'][0]['job']['filename']} paused"
                # job started
                elif item['params'][0]['action'] == 'added' and item['params'][0]['job']['status'] == 'in_progress':
                    to_printfarm = True
                    message = f"Job {item['params'][0]['job']['filename']} started"
                    # save the thumbnails
                    if not os.path.exists(os.path.join(this_dir, '..', 'tmp')):
                        os.makedirs(os.path.join(this_dir, '..', 'tmp'))
                    for i, thumbnail in enumerate(item['params'][0]['job']['metadata']['thumbnails']) :
                        url = f'http://{self.hostname}/server/files/gcodes/{thumbnail["relative_path"]}'
                        self.logger.debug(f"Downloading thumbnail from {url}")
                        res = requests.get(url, stream = True)
                        self.logger.debug(f"Response: {res}")
                        if res.status_code == 200:
                            with open(os.path.join(this_dir, '..', 'tmp', f'thumbnail_{i}.png'),'wb') as f:
                                shutil.copyfileobj(res.raw, f)
                        else:
                            self.logger.info('Thumbnail Couldn\'t be retrieved')
                            message += f"\nThumbnail Couldn\'t be retrieved"

            if 'method' in item and item['method'] == 'notify_check_failure' :
                message = f"Check filament failure: \n{item['params'][0]['message']}"

            # if message is not None send it to the keybase channel
            if message :
                self._loop.create_task(self.pending_status_message(message), to_printfarm)

        self.logger.info("Unix Socket Disconnection from _process_stream()")
        await self.close()

    def _make_rpc_msg(self, method: str, **kwargs) -> Dict[str, Any]:

        msg = {"jsonrpc": "2.0", "method": method}
        uid = id(msg)
        msg["id"] = uid
        self.pending_req = msg
        if kwargs:
            msg["params"] = kwargs
        return msg

    async def _send_manual_request(self) -> Dict[str, Any]:
        '''
        Send a manual request to Moonraker.
        @return: Response from Moonraker

        Send the content of self.manual_entry to Moonraker.
        '''
        if not self.manual_entry:
            return
        params = self.manual_entry.get("params")
        method = self.manual_entry["method"]
        message = self._make_rpc_msg(method, **params)
        fut = self._loop.create_future()
        self.pending_reqs[message["id"]] = fut
        await self._write_message(message)
        return await fut

    async def _write_message(self, message: Dict[str, Any]) -> None:
        '''
        Write a message to the Unix Socket
        @param message: Message to send
        '''
        data = json.dumps(message).encode() + b"\x03"
        try:
            self.writer.write(data)
            await self.writer.drain()
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.close()

    async def pending_status_message(self, message, to_printfarm = False):
        '''
        Send a status message to the keybase channel with an attached snapshot
        @param message: Message to send
        '''
        self.logger.info(f"Sending message: {message}")
        await self.get_snapshot()
        # if there is a thumbnail file attach it to the message
        if os.path.exists(os.path.join(this_dir, '..', 'tmp', 'thumbnail_0.png')):
            await self.bot.chat.attach(self.printfarmchannel , os.path.join(this_dir, '..', 'tmp', 'thumbnail_0.png'), self.header_message + message + self.footer_message)
        else :
            await self.bot.chat.attach(self.printfarmchannel , os.path.join(this_dir, '..', 'common', 'no_image.png'), self.header_message + message + '\n(no thumbnail found)' + self.footer_message)
        await self.bot.chat.attach(self.printerchannel , self.snap_file, self.header_message + message + self.footer_message)

    async def kb_status_msg(self):
        '''
        Send a status message to the keybase channel with an attached snapshot
        @param message: Message to send
        '''
        status = await self.get_printer_status()
        filament = await self.get_filament_info()
        # Status: {'jsonrpc': '2.0', 'result': {'eventtime': 267760.750332633, 'status': {'print_stats': {'filename': 'cable_tie_PLA_7m50s.gcode', 'total_duration': 281.22244369098917, 'print_duration': 0.0, 'filament_used': 0.0, 'state': 'paused', 'message': '', 'info': {'total_layer': 9, 'current_layer': 0}}}}, 'id': 140316437579168}
        # convert duration in seconds to HH:MM:SS
        def convert(seconds):
            seconds = seconds % (24 * 3600)
            hour = seconds // 3600
            seconds %= 3600
            minutes = seconds // 60
            seconds %= 60
            return "%d:%02d:%02d" % (hour, minutes, seconds)

        state = status['result']['status']['print_stats']['state'] if 'state' in status['result']['status']['print_stats'] else 'unknown'
        progression = int(status['result']['status']['display_status']['progress']*100) if 'progress' in status['result']['status']['display_status'] else 'unknown'
        total_layers = status['result']['status']['print_stats']['info']['total_layer'] if 'info' in status['result']['status']['print_stats'] and 'total_layer' in status['result']['status']['print_stats']['info'] else 'unknown'
        current_layer = status['result']['status']['print_stats']['info']['current_layer'] if 'info' in status['result']['status']['print_stats'] and 'current_layer' in status['result']['status']['print_stats']['info'] else 'unknown'

        used_filament_mm = status['result']['status']['print_stats']['filament_used'] if 'filament_used' in status['result']['status']['print_stats'] else 'unknown'
        if 'result' in filament :
            density = float(filament['result']['filament']['density']) if 'filament' in filament['result'] and 'density' in filament['result']['filament'] else 'unknown' # in g/cm3
            diameter = float(filament['result']['filament']['diameter']) if 'filament' in filament['result'] and 'diameter' in filament['result']['filament'] else 'unknown' # in mm
        if used_filament_mm != 'unknown' and density != 'unknown':
            used_filament_g = round(used_filament_mm * (diameter/2)**2 * 3.14 * density / 1000, 2)
        else :
            used_filament_g = 'unknown'

        total_duration = convert(status['result']['status']['print_stats']['total_duration']) if 'total_duration' in status['result']['status']['print_stats'] else 'unknown'
        print_duration = convert(status['result']['status']['print_stats']['print_duration']) if 'print_duration' in status['result']['status']['print_stats'] else 'unknown'

        # calculate ETA (datetime at which the print will be finished or finished)
        if not progression == 'unknown' and progression != 100 :
            eta = round((100 - progression) * float(status['result']['status']['print_stats']['total_duration']) / progression, 2)
            eta = convert(eta)
            # add ETA to current time
            eta = (datetime.datetime.now() + datetime.timedelta(hours=int(eta.split(':')[0]), minutes=int(eta.split(':')[1]), seconds=int(eta.split(':')[2]))).strftime("%H:%M:%S")

        else :
            eta = 'unknown'

        msg = textwrap.dedent(f"""
            >`Filename       :` {status['result']['status']['print_stats']['filename'] if 'filename' in status['result']['status']['print_stats'] else 'unknown' }
            >`State          :` {state} ({progression}%)
            >`ETA            :` {eta}
            >`Message        :` {status['result']['status']['print_stats']['message'] if 'message' in status['result']['status']['print_stats'] else 'unknown' }
            >`Total duration :` {total_duration}
            >`Print duration :` {print_duration}
            >`Filament used  :` {int(used_filament_mm / 100) if used_filament_mm != "unknown" else "unknown"} m / {used_filament_g} g
            >`Current layer  :` {current_layer} / {total_layers}
        """)
        await self.get_snapshot()
        return msg

    async def run_bot(self):
        '''
        Start the keybase bot
        '''
        asyncio.run(await self.bot.start(listen_options=LISTEN_OPTIONS))

    async def run_moonraker(self) -> None:
        '''
        Start the connection to Moonraker
        '''
        await self._connect()

    async def _connect(self) -> None:
        '''
        Connect to Moonraker
        '''
        print(f"Connecting to Moonraker at {self.sockpath}")
        while True:
            try:
                reader, writer = await asyncio.open_unix_connection(
                    self.sockpath, limit=SOCKET_LIMIT
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(1.)
                continue
            break
        self.writer = writer
        self._loop.create_task(self._process_stream(reader))
        self.connected = True
        self.logger.info("Connected to Moonraker")
        self.manual_entry = {
            "method": "server.connection.identify",
            "params": {
                "client_name": "Unix Socket Test",
                "version": "0.0.1",
                "type": "other",
                "url": "https://github.com/Arksine/moontest"
            }
        }
        ret = await self._send_manual_request()
        self.manual_entry = {}
        self.logger.info(f"Client Identified With Moonraker: {ret}")

    async def get_filament_info(self) -> Dict[str, Any]:
        '''
        Get the filament info from Moonraker
        @return: Response from Moonraker
        '''
        self.manual_entry = {
                    "method": "filament.info",
                    "params": {}
                }
        self.logger.debug(f"Sending : {self.manual_entry}")
        ret = await self._send_manual_request()
        self.logger.debug(f"Response: {ret}")
        self.manual_entry = {}
        return ret

    async def get_printer_status(self) -> Dict[str, Any]:
        '''
        Get the status of the printer
        @return: Response from Moonraker
        '''
        # Sending: {'jsonrpc': '2.0', 'method': 'printer.objects.list', 'id': 139689691991728}
        # Response: {'jsonrpc': '2.0', 'result': {'objects': ['webhooks', 'configfile', 'mcu', 'gcode_move', 'print_stats', 'virtual_sdcard', 'pause_resume', 'display_status', 'gcode_macro CANCEL_PRINT', ..., 'motion_report', 'query_endstops', 'system_stats', 'manual_probe', 'toolhead', 'extruder']}, 'id': 139689691991728}
        self.manual_entry = {
                    "method": "printer.objects.query",
                    "params": {'objects' : {'print_stats' : None, 'display_status' : None}}
                }
        self.logger.debug(f"Sending : {self.manual_entry}")
        ret = await self._send_manual_request()
        self.logger.debug(f"Response: {ret}")
        self.manual_entry = {}
        return ret

    async def get_snapshot(self) -> None:
        '''
        Get the snapshot from the printer
        '''
        self.logger.info(f"Fetching url for snapshot")
        url = await self.get_snapchot_url()
        if not url :
            self.logger.info(f"Snapshot url not found")
            return
        snapchot_url = f'http://{self.hostname}'+url
        # download image file from snaphot_url and embed into message
        self.logger.info(f"Downloading snapshot from {snapchot_url}")
        res = requests.get(snapchot_url, stream = True)
        self.logger.debug(f"Response: {res}")
        if res.status_code == 200:
            if not os.path.exists(os.path.join(this_dir, '..', 'tmp')):
                os.makedirs(os.path.join(this_dir, '..', 'tmp'))
            with open(self.snap_file,'wb') as f:
                shutil.copyfileobj(res.raw, f)

            if os.path.exists(os.path.join(this_dir, '..', 'config', 'camera.json')):
                with open(os.path.join(this_dir, '..', 'config', 'camera.json'), 'r') as file:
                    camera = json.load(file)
                if 'rotate' in camera :
                    shutil.copyfileobj(res.raw, f)
                    img = Image.open(self.snap_file)
                    img = img.rotate(int(camera['rotate']))
                    img.save(self.snap_file)
            self.logger.info('Image sucessfully Downloaded: snapshot.jpeg')
        else:
            self.logger.info('Image Couldn\'t be retrieved')

    async def get_snapchot_url(self) -> str:
        '''
        Get the snapshot url from Moonraker
        @return: Response from Moonraker
        '''
        self.manual_entry = {
                    "method": "server.webcams.list",
                    "params": {}
                }
        self.logger.debug(f"Sending : {self.manual_entry}")
        ret = await self._send_manual_request()
        self.logger.debug(f"Response: {ret}")
        #if camera.json exists get id
        if os.path.exists(os.path.join(this_dir, '..', 'config', 'camera.json')):
            with open(os.path.join(this_dir, '..', 'config', 'camera.json'), 'r') as file:
                camera = json.load(file)
            if 'id' in camera :
                id = int(camera['id'])
            else :
                id = 0
        else :
            id = 0
        if ret['result']['webcams'] :
            snapchot_url = ret['result']['webcams'][id]['snapshot_url']
        else :
            snapchot_url = None
        self.manual_entry = {}
        return snapchot_url

    async def close(self):
        '''
        Close the connection to Moonraker
        '''
        if not self.connected:
            return
        self.connected = False
        self.writer.close()
        await self.writer.wait_closed()
        # exit script as the service will be relaunched automatically
        sys.exit(0)

    def run(self):
        '''
        Main loop of the bot. It starts the keybase bot and the moonraker connection.
        '''
        self._loop = asyncio.get_event_loop()
        self._loop.create_task(self.run_bot())
        self._loop.create_task(self.run_moonraker())
        self._loop.run_forever()