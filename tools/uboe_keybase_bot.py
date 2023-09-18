#!/usr/bin/env python3

###################################
# WHAT IS IN THIS EXAMPLE?
#
# This bot listens to two channels for a special text message. When
# it sees this message, it replies in the same channel with a response.
# This also shows sending and receiving unicode characters.
###################################

import asyncio
import logging as log
import os
import sys
# import coloredlogs

# import colored_traceback.auto
# import colored_traceback.always

import pykeybasebot.types.chat1 as chat1
from pykeybasebot import Bot

log.basicConfig(level=log.DEBUG)

class Handler:
    async def __call__(self, bot, event):
        if event.msg.content.type_name != chat1.MessageTypeStrings.TEXT.value:
            return
        if "🌴ping🌴" in event.msg.content.text.body :
            channel = event.msg.channel
            await bot.chat.send(channel, "🍹PONG!🍹")


#open the paperkey file from path given in argument
with open(sys.argv[1], 'r') as file:
    paperkey = file.read().replace('\n', '')

listen_options = {
    "filter-channels": [
        {'name' : 'printhive', 'public' : None, 'members_type' : 'team', 'topic_type' : 'chat', 'topic_name' : "printfarm"}
    ]
}

bot = Bot(
    username="uboe_bot", paperkey=paperkey, handler=Handler()
)

asyncio.run(bot.start(listen_options))


