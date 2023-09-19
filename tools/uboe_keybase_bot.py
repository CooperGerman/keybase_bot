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
import subprocess
import sys, textwrap, re
# import coloredlogs

# import colored_traceback.auto
# import colored_traceback.always

from multiprocessing import Process,Pipe
import pykeybasebot.types.chat1 as chat1
from pykeybasebot import Bot

log.basicConfig(level=log.DEBUG)

class Handler:
    async def __call__(self, bot, event : chat1.Message):
        if event.msg.content.type_name != chat1.MessageTypeStrings.TEXT.value:
            return

        # list all
        if event.msg.sender.username == bot.username:
            return

        channel = event.msg.channel
        if re.match(r'^/uboe_bot', event.msg.content.text.body):
            # if "help" in event.msg.content.text.body :
            if event.msg.content.text.body == "/uboe_bot help":
                msg = textwrap.dedent("""
                    Hello there! I'm uboe_bot, a bot for print farm management.
                    I can help you with the following commands:
                        `help` - this help message
                        `status` - display the printer's status
                    More commands coming soon!
                """)
            #if event.msg.content.text.body == "/uboe_bot status" :
            elif event.msg.content.text.body == "/uboe_bot status" :
                msg = textwrap.dedent(f"""
                    {os.uname().nodename} is currently {os.getloadavg()[0]}% loaded.

                """)

            # if "🌴ping🌴" in event.msg.content.text.body :
            elif "🌴ping🌴" in event.msg.content.text.body :
                msg = "🍹PONG!🍹"
            else :
                msg = "Command not recognized. Try `/uboe_bot help`"

            await bot.chat.send(channel, msg)

#open the paperkey file from path given in argument
with open(sys.argv[1], 'r') as file:
    paperkey = file.read().replace('\n', '')

listen_options = {
    "filter-channels": [
        {'name' : 'printhive', 'public' : None, 'members_type' : 'team', 'topic_type' : 'chat', 'topic_name' : "printfarm"}
    ]
}


# what linux user is running this script
user = subprocess.run(['whoami'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip()
log.info(f"Running as user: {user}")

# if pidfile exists
if os.path.isfile('/run/user/1000/keybase/keybased.pid'):
    bot = Bot(
        username="uboe_bot", paperkey=paperkey, handler=Handler(), pid_file='/run/user/1000/keybase/keybased.pid'
    )
    log.info("PID file exists")
else:
    bot = Bot(
        username="uboe_bot", paperkey=paperkey, handler=Handler()
    )

def main(child_conn=None):
    if child_conn:
        msg = "Hello"
        child_conn.send(msg)
        child_conn.close()
    asyncio.run(bot.start(listen_options))

if __name__ == "__main__":
    main()



