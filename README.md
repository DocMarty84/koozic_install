This repository provides an (un)-installer for KooZic.

# Usage

```
koozic_install.py [-h] [-u USER] [-d DIRECTORY] {install,uninstall,upgrade}

KooZic (un)-installer

positional arguments:
  {install,uninstall,upgrade}
                        install or uninstall mode

optional arguments:
  -h, --help            show this help message and exit
  -u USER, --user USER  user running koozic
  -d DIRECTORY, --directory DIRECTORY
                        install directory

```

# Supported platforms

- Ubuntu 18.04
- Debian 10
- Fedora 31
- OpenSUSE 15.1

# Detailed process

## Installation

- Install Python dependencies from system packages
- Install extra dependencies from pip
- Setup PostgreSQL
- Copy FFMpeg
- Copy files (default: /opt/koozic)
- Initialize database
- Setup systemd

## Uninstallation

- Disable systemd
- Remove database
- Remove files

## Upgrade

- Update sources
- Upgrade database
