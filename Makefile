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
## File:        Makefile
## Author(s):   Y.L.P.
## Description: Automation
###############################################################################

SHELL=bash -e
default: all

all : install

install : check_bins env setup service

setup: venv paperkey channel

paperkey: /home/$(USER)/.keybase_bot/paper_key
/home/$(USER)/.keybase_bot/paper_key:
	mkdir -p /home/$(USER)/.keybase_bot
	$(info Generating paperkey)
	keybase config set -b pinentry.disabled true
	keybase login uboe_bot
	keybase paperkey > /home/$(USER)/.keybase_bot/paper_key
	sed -n '4p' -i /home/$(USER)/.keybase_bot/paper_key
	sed 's/^[ \t]*//' -i /home/$(USER)/.keybase_bot/paper_key
	sed -n '1p' -i /home/$(USER)/.keybase_bot/paper_key
	$(info Done)

channel: /home/$(USER)/.keybase_bot/printer_channel.json
/home/$(USER)/.keybase_bot/printer_channel.json:
	$(info creating printer dedicated channel)
	keybase oneshot -u=uboe_bot --paperkey="$(cat ~/.keybase_bot/paper_key)"
	keybase chat create-channel printhive $(hostname)

service:
	$(info Setting up service)
	systemctl --user daemon-reload
	systemctl --user enable /home/$(USER)/keybase_bot/scripts/uboe_keybase_bot.service
	systemctl --user start uboe_keybase_bot.service
	$(info Done)

venv: get_requirements
	echo "Setting up environment" ; \
	mkdir -p .venv ; \
	python3.7 -m venv .venv ; \
	source .venv/bin/activate ; \
	echo "Installing python dependencies" ; \
	pip install -r tools/requirements.txt ; \
	pip install --upgrade pip ; \
	echo "Done initializing virtual environment"

get_requirements:
	pipreqs --force --savepath tools/requirements.txt ./tools

REQUIRED_BINS := pip python3.7 pipreqs
check_bins:
	$(info Looking for binaries: `$(REQUIRED_BINS)` in PATH)
	$(foreach bin,$(REQUIRED_BINS),\
		$(if $(shell command -v $(bin) 2> /dev/null),\
			$(info Found `$(bin)`),\
			$(info Error: Please install `$(bin)` or add it to PATH if already installed)))
env:
	mkdir -p ./work
	mkdir -p ./result
	mkdir -p ./logs
	mkdir -p ./tmp

clean:
	rm -rf ./work
	rm -f ./result

super_clean: clean
	rm -rf ./env

# ./pip.sh check requirements.txt
help :
	@echo "make help                : prints this help"
	@echo "make install             : installs the bot"
	@echo "make setup               : sets up the bot"
	@echo "make service             : sets up the service"
	@echo "make venv                : sets up the virtual environment"
	@echo "make get_requirements    : gets the requirements"
	@echo "make check_bins          : checks the binaries"
	@echo "make env                 : sets up the environment"
	@echo "make clean               : cleans the environment"
	@echo "make super_clean         : cleans the environment and the virtual environment"



