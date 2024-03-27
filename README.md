# Keybase bot (by Uboe)

This repo contains the keybase bot developped and used by Uboe.

## Installation

```bash
make
```

This should `check` the needed binaries, `setup` the `virtualenv` and install the needed python packages, generate a device  specific `paperkey`, create a `channel` for the current machine and start the `bot service`.

# Limitations
	- This bot must be installed in the `/home/$USER/keybase_bot` directory.
	- Raspbian is not supported yet (because of the `keybase` installation). Uboe uses this bot on x86 machines with Archlinux installations.
