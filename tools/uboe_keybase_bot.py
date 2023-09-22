#!/bin/python3.7
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
This is the main program, it fetches all spoolman filaments and generates a user
profile folder for OrcaSliccer to point to when it starts.
'''
import json, asyncio
import logging as log
import os
import subprocess
import sys, textwrap, re
import coloredlogs

import colored_traceback.auto
import colored_traceback.always

import argparse

from moonraker_connection import KeybaseBot
this_dir = os.path.dirname(os.path.abspath(__file__))

log.basicConfig(level=log.DEBUG)


def main():
    banner = '''###############################################################################
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
'''
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        prog='main.py',
        description=banner,
        epilog='''This is the main program, it fetches all spoolman filaments and generates a user
        profile folder for OrcaSliccer to point to when it starts.'''
    )
    parser.add_argument(
        'paperkey',
        type=str,
        help='Keybase paperkey'
    )
    parser.add_argument(
        '--loglvl',
        type=str,
        default='info',
        choices=['debug', 'info', 'warning', 'error', 'critical', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Logging level'
    )
    loglvl = getattr(log, parser.parse_args().loglvl.upper())
    args = parser.parse_args()
    # configure logging with colored output
    # Create a logger object.
    logger = log.getLogger(__name__)

    # By default the install() function installs a handler on the root logger,
    # this means that log messages from your code and log messages from the
    # libraries that you use will all show up on the terminal.
    coloredlogs.install(level=args.loglvl)

    # If you don't want to see log messages from libraries, you can pass a
    # specific logger object to the install() function. In this case only log
    # messages originating from that logger will show up on the terminal.
    coloredlogs.install(level=args.loglvl, logger=logger)

    print(banner)

    # set the logger up to log into a file aswell as the console
    # create a file handler
    handler = log.FileHandler(os.path.join(this_dir, '..', 'logs','keybase_bot.log'))
    handler.setLevel(loglvl)
    # create a logging format
    formatter = log.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    # add the handlers to the logger
    logger.addHandler(handler)
    # log the start of the program

    logger.info('Starting KeybaseBot.py')

    # display a recap of the arguments
    logger.info('='*80)
    logger.info('Called with the following arguments:')
    for arg in vars(args):
        logger.info('	{}: {}'.format(arg, getattr(args, arg)))
    logger.warning('Working on branch {}'.format(os.popen('git rev-parse --abbrev-ref HEAD').read().strip()))
    logger.info('='*80)
    # what linux user is running this script
    user = subprocess.run(['whoami'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip()
    log.info(f"Running as user: {user}")
    # load api_presets.json from ../common/api_presets.json
    with open('/home/uboe/keybase_bot/common/api_presets.json', 'r') as file:
        api_presets = json.load(file)
    # create a moonraker connection
    kbBot = KeybaseBot(sockpath='/home/uboe/printer_data/comms/moonraker.sock', presets=api_presets, paperkey=args.paperkey ,logger=logger)
    # connect to moonraker
    kbBot.run()

if __name__ == "__main__":
    main()
