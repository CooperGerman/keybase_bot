#!/usr/bin/bash
mkdir -p /home/$USER/keybase_bot/logs
source /home/$USER/keybase_bot/.venv/bin/activate
python /home/$USER/keybase_bot/tools/uboe_keybase_bot.py /home/$USER/.keybase_bot/paper_key --loglvl=debug
deactivate

