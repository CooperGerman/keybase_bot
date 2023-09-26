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

install : check_bins env setup install_python_deps service

setup: venv

service:
	$(info Setting up service)
	systemctl --user enable /home/$(USER)/scripts/keybase_bot.service
	systemctl --user start keybase_bot.service
	$(info Done)

venv:
	echo "Setting up environment" ; \
	mkdir -p .venv ; \
	python3.7 -m venv .venv ; \
	source .venv/bin/activate ; \
	echo "Installing python dependencies" ; \
	pip install -r tools/requirements.txt ; \
	pip install --upgrade pip ; \
	echo "Done initializing virtual environment"

REQUIRED_BINS := pip python3.7
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

install_python_deps:
	pip install -r tools/requirements.txt

freeze:
	cd tools &&	pip freeze > requirements.txt

# ./pip.sh check requirements.txt
help :
	@echo "make help                : prints this help"
	@echo "make install_python_deps : install python dependencies"
	@echo "make freeze              : freeze python dependencies"
	@echo "make clean               : clean build files"
	@echo "make super_clean         : clean build files and virtual environment"
	@echo "make check_bins          : check if required binaries are installed"
	@echo "make env                 : create work, result, logs and tmp directories"
	@echo "make setup               : setup service"
	@echo "make service             : start service"
	@echo "make venv                : setup virtual environment"
	@echo "make install             : install dependencies"
	@echo "make all                 : install dependencies"



