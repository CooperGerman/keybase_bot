#! /usr/bin/python3
# Unix Domain Socket Connection Test for Moonraker
#
# Copyright (C) 2022 Eric Callahan <arksine.code@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license
from __future__ import annotations
import os
import sys
import argparse
import ast
import asyncio
import pathlib
import json
import logging
import textwrap
import re

import pykeybasebot.types.chat1 as chat1
from pykeybasebot import Bot

from typing import Any, Dict, List, Optional

SOCKET_LIMIT = 20 * 1024 * 1024
MENU = [
    "List API Request Presets",
    "Select API Request Preset",
    "Manual API Entry",
    "Start Notification View",
]
LISTEN_OPTIONS = {
    "filter-channels": [
        {'name' : 'printhive', 'public' : None, 'members_type' : 'team', 'topic_type' : 'chat', 'topic_name' : "printfarm"}
    ]
}

class KeybaseBot:
    def __init__(
        self, sockpath: pathlib.Path, presets: List[Dict[str, Any]], paperkey: str, logger
    ) -> None:
        self.logger = logger
        # get paperkey from file
        with open(paperkey, 'r') as file:
            self.paperkey = file.read().replace('\n', '')

        # if pidfile exists
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
        self.channel = chat1.ChatChannel(
            name=LISTEN_OPTIONS['filter-channels'][0]['name'],
            public=LISTEN_OPTIONS['filter-channels'][0]['public'],
            members_type=LISTEN_OPTIONS['filter-channels'][0]['members_type'],
            topic_type=LISTEN_OPTIONS['filter-channels'][0]['topic_type'],
            topic_name=LISTEN_OPTIONS['filter-channels'][0]['topic_name']
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
        self.header_message = textwrap.dedent(f"""
            Keybase Bot for Moonraker
            =========================
            Hostname: {self.hostname}
            """)

    async def __call__(self, bot, chat_event : chat1.Message ):
        if chat_event.msg.content.type_name != chat1.MessageTypeStrings.TEXT.value:
            return

        # list all
        if chat_event.msg.sender.username == bot.username:
            return

        channel = chat_event.msg.channel
        if re.match(r'^/uboe_bot', chat_event.msg.content.text.body):
            # if "help" in chat_event.msg.content.text.body :
            if chat_event.msg.content.text.body == "/uboe_bot help":
                msg = textwrap.dedent("""
                    Hello there! I'm uboe_bot, a bot for print farm management.
                    I can help you with the following commands:
                        `help` - this help message
                        `status` - display the printer's status
                    More commands coming soon!
                """)
            #if chat_event.msg.content.text.body == "/uboe_bot status" :
            elif chat_event.msg.content.text.body == "/uboe_bot status" :
                msg = textwrap.dedent(f"""
                    {os.uname().nodename} is currently {os.getloadavg()[0]}% loaded.

                """)

            # if "🌴ping🌴" in chat_event.msg.content.text.body :
            elif "🌴ping🌴" in chat_event.msg.content.text.body :
                msg = "🍹PONG!🍹"
            else :
                msg = "Command not recognized. Try `/uboe_bot help`"

            await bot.chat.send(channel, msg)

    def run(self):
        self._loop = asyncio.get_event_loop()
        self._loop.create_task(self.run_bot())
        self._loop.create_task(self.run_moonraker())
        self._loop.run_forever()

    async def run_bot(self):
        asyncio.run(await self.bot.start(listen_options=LISTEN_OPTIONS))

    async def run_moonraker(self) -> None:
        await self._connect()

    async def _mode_menu(self) -> None:
        req = await self.input("Menu Index (? for Help): ")
        if req == "1":
            await self._print_presets()
        elif req == "2":
            self.mode = 1
        elif req == "3":
            self.manual_entry = {}
            self.mode = 2
        elif req == "4":
            self.mode = 5
        else:
            if req != "?":
                await self.print(f"Invalid Entry: {req}")
            await self._print_help()

    async def _mode_select_preset(self) -> None:
        req = await self.input("Preset Index (Press Enter to return to main menu): ")
        if not req:
            self.mode = 0
            self.need_print_help = True
            return
        if not req.isdigit():
            await self.print(f"Error: invalid selection {req}")
            return
        ret = await self._send_preset(int(req) - 1)
        if ret:
            await self.print(f"Response: {ret}\n")

    async def _mode_manual_entry(self) -> None:
        if self.mode == 2:
            req = await self.input("Method Name (Press Enter to return to main menu): ")
            if not req:
                self.mode = 0
                self.need_print_help = True
                self.manual_entry = {}
                return
            self.manual_entry["method"] = req
            self.mode = 3
        elif self.mode == 3:
            if "params" not in self.manual_entry:
                self.manual_entry["params"] = {}
            req = await self.input("Parameter Name (Press Enter to send request): ")
            if not req:
                # send request and print response
                ret = await self._send_manual_request()
                await self.print(f"Response: {ret}\n")
                self.manual_entry = {}
                self.mode = 2
                return
            self.manual_entry["params"][req] = None
            self.mode = 4
        elif self.mode == 4:
            params: Dict[str, Any] = self.manual_entry.get("params", {})
            if not params:
                self.mode = 3
                return
            last_key = list(params.keys())[-1]
            req = await self.input(f"Parameter '{last_key}' Value: ")
            if not req:
                await self.print(f"No value selected, removing parameter {last_key}")
                params.pop(last_key, None)
            else:
                try:
                    val = ast.literal_eval(req)
                except Exception as e:
                    await self.print(f"Error: invalid value {req}, raised {e}")
                    return
                params[last_key] = val
            self.mode = 3

    async def _mode_watch_notify(self) -> None:
        await self.print("Watching notifications, Press Enter to stop")
        await asyncio.sleep(1.)
        self.print_notifications = True
        ret = await self.input()
        self.print_notifications = False
        self.mode = 0
        self.need_print_help = True

    async def _print_help(self) -> None:
        msg = "\nMain Menu:\nIndex     Description"
        for idx, desc in enumerate(MENU):
            msg += f"\n{idx + 1:<10}{desc}"
        msg += (
            "\n?         Help (show this message)"
            "\nCTRL+C    Quit this application\n"
        )
        await self.print(msg)

    async def _print_presets(self) -> None:
        msg = (
            "\nAvailable API Presets\nIndex   "
            f"{'Method':<{self.max_method_len}}Params"
        )
        for idx, preset in enumerate(self.api_presets):
            method = preset.get("method", "invalid")
            params = preset.get("params", "")
            msg += f"\n{idx + 1:<10}{method:<{self.max_method_len}}{params}"
        await self.print(msg + "\n")

    async def _connect(self) -> None:
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
        await self.print("Connected to Moonraker")
        self.manual_entry = {
            "method": "server.connection.identify",
            "params": {
                "client_name": "Unix Socket Test",
                "version": "0.0.1",
                "type": "other",
                "url": "https://github.com/Arksine/moontest"
            }
        }
        ret = await self._send_manual_request(False)
        self.manual_entry = {}
        await self.print(f"Client Identified With Moonraker: {ret}")

    async def _process_stream(
        self, reader: asyncio.StreamReader
    ) -> None:
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
            # check the status of the job
            if 'method' in item and item['method'] != 'notify_proc_stat_update' :
                self.logger.debug(f"Notification: {item}\n")

            # job completed
            if 'method' in item and 'params' in item and 'action' in item['params'][0] and 'job' in item['params'][0] and 'status' in item['params'][0]['job']:
                if item['method'] == 'notify_history_changed' and item['params'][0]['action'] == 'finished' and item['params'][0]['job']['status'] == 'completed':
                    message = f"Job {item['params'][0]['job']['filename']} completed"
                    await self.bot.chat.send(self.channel, message)
                    self.logger.info(message)
                # job cancelled
                elif item['method'] == 'notify_history_changed' and item['params'][0]['action'] == 'finished' and item['params'][0]['job']['status'] == 'cancelled':
                    message = f"Job {item['params'][0]['job']['filename']} cancelled"
                    await self.bot.chat.send(self.channel, message)
                    self.logger.info(message)
                # job paused
                elif item['method'] == 'notify_history_changed' and item['params'][0]['action'] == 'finished' and item['params'][0]['job']['status'] == 'paused':
                    message = f"Job {item['params'][0]['job']['filename']} paused"
                    await self.bot.chat.send(self.channel, message)
                    self.logger.info(message)
                # job started
                elif item['method'] == 'notify_history_changed' and item['params'][0]['action'] == 'added' and item['params'][0]['job']['status'] == 'in_progress':
                    message = f"Machine {self.hostname} ==> Job {item['params'][0]['job']['filename']} started"
                    await self.bot.chat.send(self.channel, message)
                    self.logger.info(message)

        await self.print("Unix Socket Disconnection from _process_stream()")
        await self.close()

    def _make_rpc_msg(self, method: str, **kwargs) -> Dict[str, Any]:
        msg = {"jsonrpc": "2.0", "method": method}
        uid = id(msg)
        msg["id"] = uid
        self.pending_req = msg
        if kwargs:
            msg["params"] = kwargs
        return msg

    async def _send_manual_request(
        self, echo_request: bool = True
    ) -> Dict[str, Any]:
        if not self.manual_entry:
            return
        params = self.manual_entry.get("params")
        method = self.manual_entry["method"]
        message = self._make_rpc_msg(method, **params)
        fut = self._loop.create_future()
        self.pending_reqs[message["id"]] = fut
        if echo_request:
            await self.print(f"Sending: {message}")
        await self._write_message(message)
        return await fut

    async def _send_preset(self, index: int) -> Dict[str, Any]:
        if index < 0 or index >= len(self.api_presets):
            await self.print(f"Error: Preset index {index} out of range.")
            return {}
        preset = self.api_presets[index]
        if "method" not in self.api_presets[index]:
            await self.print(f"Error: Invalid Preset {preset}")
            return
        params: Dict[str, Any] = preset.get("params", {})
        if not isinstance(params, dict):
            params = {}
        message = self._make_rpc_msg(preset["method"], **params)
        fut = self._loop.create_future()
        self.pending_reqs[message["id"]] = fut
        await self.print(f"Sending: {message}")
        await self._write_message(message)
        return await fut

    async def _write_message(self, message: Dict[str, Any]) -> None:
        data = json.dumps(message).encode() + b"\x03"
        try:
            self.writer.write(data)
            await self.writer.drain()
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.close()

    async def input(self, prompt: str = "") -> str:
        if prompt:
            await self.print(prompt, is_line=False)
        self.kb_fut = self._loop.create_future()
        ret = await self.kb_fut
        self.kb_fut = None
        return ret

    async def print(self, message: str, is_line: bool = True) -> None:
        async with self.print_lock:
            if is_line:
                message += "\n"
            while message:
                fut = self._loop.create_future()
                self._loop.add_writer(self.out_fd, self._req_stdout, fut)
                await fut
                ret = sys.stdout.write(message)
                message = message[ret:]
            sys.stdout.flush()

    def _req_stdout(self, fut: asyncio.Future) -> None:
        fut.set_result(None)
        self._loop.remove_writer(self.out_fd)

    def _process_keyboard(self) -> None:
        data = os.read(self.kb_fd, 4096)
        parts = data.split(b"\n", 1)
        parts[0] = self.kb_buf + parts[0]
        self.kb_buf = parts.pop()
        if parts and self.kb_fut is not None:
            self.kb_fut.set_result(parts[0].decode())

    async def close(self):
        if not self.connected:
            return
        self.connected = False
        self.writer.close()
        await self.writer.wait_closed()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Unix Socket Test Utility")
    parser.add_argument(
        "-s", "--socketfile", default="~/printer_data/comms/moonraker.sock",
        metavar='<socketfile>',
        help="Path to Moonraker Unix Domain Socket"
    )
    parser.add_argument(
        "-p", "--presets", default=None, metavar='<presetfile>',
        help="Path to API Presets Json File"
    )
    args = parser.parse_args()
    sockpath = pathlib.Path(args.socketfile).expanduser().resolve()
    pfile: Optional[str] = args.presets
    if pfile is None:
        parent = pathlib.Path(__file__).parent
        presetpath = parent.joinpath("unix_api_presets.json")
    else:
        presetpath = pathlib.Path(args.presets).expanduser().resolve()
    presets: List[Dict[str, Any]] = []
    if presetpath.exists():
        try:
            presets = json.loads(presetpath.read_text())
        except Exception:
            print(f"Failed to load API Presets from file {presetpath}")
        else:
            if not isinstance(presets, list):
                print(f"Invalid JSON object in preset file {presetpath}")
                presets = []
    conn = KeybaseBot(sockpath, presets)
    try:
        asyncio.run(conn.run())
    except KeyboardInterrupt:
        print("\n")
        pass