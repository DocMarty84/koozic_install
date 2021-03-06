#!/usr/bin/env python3

import argparse
import os
import pwd
import subprocess as s
import sys
import tarfile
from collections import OrderedDict
from glob import glob
from multiprocessing import cpu_count
from shutil import rmtree, which
from tempfile import NamedTemporaryFile

import requests

BRANCH = "v3"
K_NAME_DIR = K_NAME_DB = "koozic-{}".format(BRANCH)
DOWN_URL = "https://github.com/DocMarty84/koozic/releases/download/{v}/koozic-{v}.tar.gz"


class Driver:
    def __init__(self, args):
        self.dep = set([])
        self.pip_dep = set([])
        self.user = args.user
        self.dir = os.path.join(args.directory, K_NAME_DIR)

    def __setitem__(self, key, val):
        return setattr(self, key, val)

    def set_config(self):
        with open(os.path.join(os.sep, "etc", "koozic-install.conf"), "w") as f:
            f.write("USER={}\n".format(self.user))
            f.write("DIR={}\n".format(self.dir))

    def get_config(self):
        fn = os.path.join(os.sep, "etc", "koozic-install.conf")
        if not os.path.isfile(fn):
            sys.exit("Configuration file {} could not be found! Exiting...".format(fn))
        with open(fn, "r") as f:
            for line in f:
                data = line.split("=")
                self[data[0].lower()] = data[1].rstrip()

    def install_dep(self):
        print("Installing package dependencies...")
        self._install(list(self.dep))

    def install_pip_dep(self):
        print("Installing pip dependencies...")
        self._pip_install(list(self.pip_dep))

    def setup_postgresql(self):
        s.call('su - postgres -c "createuser -s {}"'.format(self.user), shell=True)

    def download_and_extract(self):
        print("Downloading the latest KooZic version...")
        with NamedTemporaryFile() as out_file:
            dir = os.path.split(self.dir)[0]
            out_file.write(requests.get(DOWN_URL).content)
            tarfile.open(name=out_file.name).extractall(path=dir)
            os.rename(os.path.join(dir, "koozic"), self.dir)
        s.call(["chown", "-R", "{u}:{u}".format(u=self.user), self.dir])

    def copy_ffmpeg(self):
        if which("ffmpeg"):
            return
        ffmpeg = glob(os.path.join(self.dir, "extra", "ffmpeg", "*.tar.gz"))
        if ffmpeg:
            path = os.path.join(os.sep, "usr", "local", "bin")
            tarfile.open(name=ffmpeg[0]).extractall(path=path)
            s.call(["chown", "{u}:{u}".format(u=self.user), os.path.join(path, "ffmpeg")])

    def init_koozic(self):
        print("Initializing KooZic...")
        s.call(self._init_koozic_cmd(), shell=True)

    def enable_systemd(self):
        # Create koozic@.service file
        service = glob(
            os.path.join(self.dir, "extra", "linux-systemd", "system", "koozic@.service")
        )
        output = ""
        with open(service[0], "r") as f:
            for line in f:
                if line.startswith("ExecStart"):
                    output += "ExecStart={}\n".format(os.path.join(self.dir, "odoo-bin"))
                else:
                    output += "{}".format(line)
        with open(os.path.join(os.sep, "etc", "systemd", "system", "koozic@.service"), "w") as f:
            f.write(output)

        # Create ~/.odoorc file
        output = "[options]\n"
        output += "\n".join(["{} = {}".format(k, v) for k, v in self._compute_options().items()])
        output += "\n"
        output += "\n".join(["#{} = {}".format(k, v) for k, v in self._default_options().items()])
        output += "\n"
        odoorc_path = os.path.expanduser("~{}/.odoorc".format(self.user))
        with open(odoorc_path, "w") as f:
            f.write(output)
        os.chown(odoorc_path, pwd.getpwnam(self.user).pw_uid, -1)
        os.chmod(odoorc_path, 0o640)

        s.call(["systemctl", "enable", "koozic@{}.service".format(self.user)])
        s.call(["systemctl", "start", "koozic@{}.service".format(self.user)])

    def clean_system(self):
        if self._ask_user("Do you want to deactivate the KooZic systemd service? "):
            s.call(["systemctl", "stop", "koozic@{}.service".format(self.user)])
            s.call(["systemctl", "disable", "koozic@{}.service".format(self.user)])
        if self._ask_user("Do you want to drop the KooZic database? "):
            s.call('su - {} -c "dropdb {}"'.format(self.user, K_NAME_DB), shell=True)

    def clean_files(self):
        to_delete = [
            os.path.expanduser("~{}/.local/share/Odoo".format(self.user)),
            os.path.expanduser("~{}/.odoorc".format(self.user)),
            os.path.join(os.sep, "etc", "systemd", "system", "koozic@.service"),
            os.path.join(os.sep, "etc", "koozic-install.conf"),
            os.path.join(os.sep, "usr", "local", "bin", "ffmpeg"),
            self.dir,
        ]
        if self._ask_user(
            "Do you want to delete the following files/folders?\n{}\n".format("\n".join(to_delete))
        ):
            for dir in to_delete:
                if os.path.isfile(dir):
                    os.remove(dir)
                elif os.path.isdir(dir):
                    rmtree(dir, ignore_errors=True)

    def upgrade(self):
        s.call(["systemctl", "stop", "koozic@{}.service".format(self.user)])
        if self._ask_user(
            "Delete content of folder {} and replace with new sources? ".format(self.dir)
        ):
            rmtree(self.dir, ignore_errors=True)
            self.download_and_extract()
        self.init_koozic()
        s.call(["systemctl", "start", "koozic@{}.service".format(self.user)])

    def install_message(self):
        print(
            """
  ___           _        _ _       _   _
 |_ _|_ __  ___| |_ __ _| | | __ _| |_(_) ___  _ __
  | || '_ \/ __| __/ _` | | |/ _` | __| |/ _ \| '_ \\
  | || | | \__ \ || (_| | | | (_| | |_| | (_) | | | |
 |___|_| |_|___/\__\__,_|_|_|\__,_|\__|_|\___/|_| |_|
  ____                               __       _ _
 / ___| _   _  ___ ___ ___  ___ ___ / _|_   _| | |
 \___ \| | | |/ __/ __/ _ \/ __/ __| |_| | | | | |
  ___) | |_| | (_| (_|  __/\__ \__ \  _| |_| | |_|
 |____/ \__,_|\___\___\___||___/___/_|  \__,_|_(_)

        """
        )
        print("You can now connect to http://localhost:8069/.")
        print("Default credentials:")
        print("    Email:    admin")
        print("    Password: admin")

    def _install(self, packages=[]):
        raise NotImplementedError()

    def _pip_install(self, packages=[]):
        if packages:
            s.call(["pip3", "install", "-q"] + packages)

    def _init_koozic_cmd(self):
        return (
            'su - {} -c "{}{}odoo-bin -i oomusic,oovideo -d {} '
            '--without-demo=all --stop-after-init --log-level=warn"'.format(
                self.user, self.dir, os.sep, K_NAME_DB
            )
        )

    def _compute_options(self):
        cpu = cpu_count()
        max_mem = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        workers = max(cpu, 2)
        max_cron_threads = 1
        limit_memory_soft = min(max_mem / (workers + max_cron_threads), 2048 * 1024 ** 2)
        limit_memory_hard = max_mem * 0.90
        return {
            "db_name": K_NAME_DB,
            "dbfilter": "^{}$".format(K_NAME_DB),
            "limit_memory_hard": max(1024 ** 3, int(limit_memory_hard)),
            "limit_memory_soft": max(896 * 1024 ** 2, int(limit_memory_soft)),
            "limit_time_cpu": 1800,
            "limit_time_real": 3600,
            "list_db": False,
            "max_cron_threads": max_cron_threads,
            "workers": workers,
        }

    def _default_options(self):
        addons_path = (
            os.path.join(self.dir, "odoo", "addons") + "," + os.path.join(self.dir, "addons")
        )
        return {
            "addons_path": addons_path,
            "admin_passwd": "admin",
            "csv_internal_sep": ",",
            "data_dir": os.path.expanduser("~{}/.local/share/Odoo".format(self.user)),
            "db_host": "False",
            "db_maxconn": 64,
            "db_password": "False",
            "db_port": "False",
            "db_sslmode": "prefer",
            "db_template": "template1",
            "db_user": "False",
            "demo": "{}",
            "email_from": "False",
            "geoip_database": "/usr/share/GeoIP/GeoLite2-City.mmdb",
            "http_enable": "True",
            "http_interface": "",
            "http_port": 8069,
            "import_partial": "",
            "limit_request": 8192,
            "limit_time_real_cron": -1,
            "log_db": "False",
            "log_db_level": "warning",
            "log_handler": ":INFO",
            "log_level": "info",
            "logfile": "None",
            "logrotate": "False",
            "longpolling_port": 8072,
            "osv_memory_age_limit": 1.0,
            "osv_memory_count_limit": "False",
            "pg_path": "None",
            "pidfile": "None",
            "proxy_mode": "False",
            "reportgz": "False",
            "server_wide_modules": "web",
            "smtp_password": "False",
            "smtp_port": 25,
            "smtp_server": "localhost",
            "smtp_ssl": "False",
            "smtp_user": "False",
            "syslog": "False",
            "test_commit": "False",
            "test_enable": "False",
            "test_file": "False",
            "test_report_directory": "False",
            "translate_modules": "['all']",
            "unaccent": "False",
            "without_demo": "False",
        }

    def _ask_user(self, question):
        accepted_answers = ["y", "n", "yes", "no"]
        while True:
            ans = input("\n{}(Y/n) ".format(question))
            if ans and ans.lower() not in accepted_answers:
                print("Valid answers are: {}".format(", ".join(accepted_answers)))
            else:
                return False if ans.lower() in ["n", "no"] else True


class DriverDeb(Driver):
    def __init__(self, args):
        super().__init__(args)
        self.dep |= set(
            [
                "adduser",
                "build-essential",
                "ffmpeg",
                "libtag1-dev",
                "lsb-base",
                "mediainfo",
                "postgresql",
                "postgresql-client",
                "python3-babel",
                "python3-chardet",
                "python3-dateutil",
                "python3-decorator",
                "python3-dev",
                "python3-docutils",
                "python3-feedparser",
                "python3-gevent",
                "python3-html2text",
                "python3-jinja2",
                "python3-ldap",
                "python3-libsass",
                "python3-lxml",
                "python3-mako",
                "python3-mock",
                "python3-passlib",
                "python3-pil",
                "python3-pip",
                "python3-polib",
                "python3-psutil",
                "python3-psycopg2",
                "python3-pydot",
                "python3-pyparsing",
                "python3-pypdf2",
                "python3-qrcode",
                "python3-reportlab",
                "python3-requests",
                "python3-setuptools",
                "python3-tz",
                "python3-vatnumber",
                "python3-vobject",
                "python3-werkzeug",
                "python3-wheel",
                "python3-xlsxwriter",
                "python3-yaml",
                "python3-zeep",
            ]
        )
        self.pip_dep |= set(
            ["mutagen==1.43.0", "pytaglib==1.4.5", "num2words==0.5.6", "webvtt-py==0.4.2"]
        )

    def _install(self, packages=[]):
        if packages:
            s.call(["apt-get", "install", "-y", "--no-install-recommends", "-qq"] + packages)


DriverUbuntu2004 = DriverDeb
DriverDebian10 = DriverDeb


class DriverFedora31(Driver):
    def __init__(self, args):
        super().__init__(args)
        self.dep = set(
            [
                "babel",
                "gcc",
                "gcc-c++",
                "libxslt-python",
                "mediainfo",
                "postgresql",
                "postgresql-contrib",
                "postgresql-devel",
                "postgresql-libs",
                "postgresql-server",
                "pychart",
                "pyparsing",
                "python3-PyPDF2",
                "python3-PyYAML",
                "python3-babel",
                "python3-chardet",
                "python3-dateutil",
                "python3-decorator",
                "python3-devel",
                "python3-docutils",
                "python3-feedparser",
                "python3-gevent",
                "python3-greenlet",
                "python3-html2text",
                "python3-jinja2",
                "python3-ldap",
                "python3-libsass",
                "python3-lxml",
                "python3-mako",
                "python3-markupsafe",
                "python3-mock",
                "python3-num2words",
                "python3-ofxparse",
                "python3-passlib",
                "python3-pillow",
                "python3-polib",
                "python3-psutil",
                "python3-psycopg2",
                "python3-pydot",
                "python3-pyparsing",
                "python3-pyserial",
                "python3-pytz",
                "python3-pyusb",
                "python3-qrcode",
                "python3-reportlab",
                "python3-requests",
                "python3-six",
                "python3-stdnum",
                "python3-vatnumber",
                "python3-vobject",
                "python3-werkzeug",
                "python3-xlrd",
                "python3-xlwt",
                "python3-zeep",
                "redhat-rpm-config",
                "taglib-devel",
            ]
        )
        self.pip_dep = set(
            ["XlsxWriter==1.1.2", "mutagen==1.43.0", "pytaglib==1.4.5", "webvtt-py==0.4.2"]
        )

    def setup_postgresql(self):
        s.call(["postgresql-setup", "--initdb", "--unit", "postgresql"])
        s.call(["systemctl", "enable", "postgresql"])
        s.call(["systemctl", "start", "postgresql"])
        super().setup_postgresql()

    def _install(self, packages=[]):
        if packages:
            s.call(["dnf", "install", "-y", "-q"] + packages)

    def _init_koozic_cmd(self):
        return super()._init_koozic_cmd()[:-1] + ' --db-template=template0"'


class DriverSuse15(Driver):
    def __init__(self, args):
        super().__init__(args)
        self.dep = set(
            [
                "ffmpeg-3",
                "gcc",
                "gcc-c++",
                "libxslt-python",
                "mediainfo",
                "postgresql",
                "postgresql-contrib",
                "postgresql-devel",
                "postgresql-server",
                "python3-Babel",
                "python3-Jinja2",
                "python3-Mako",
                "python3-MarkupSafe",
                "python3-Pillow",
                "python3-PyPDF2",
                "python3-PyYAML",
                "python3-Werkzeug",
                "python3-chardet",
                "python3-decorator",
                "python3-devel",
                "python3-docutils",
                "python3-feedparser",
                "python3-gevent",
                "python3-greenlet",
                "python3-html2text",
                "python3-ldap",
                "python3-libsass",
                "python3-lxml",
                "python3-mock",
                "python3-num2words",
                "python3-passlib",
                "python3-polib",
                "python3-psutil",
                "python3-psycopg2",
                "python3-pydot",
                "python3-pyparsing",
                "python3-pyserial",
                "python3-pytaglib",
                "python3-python-dateutil",
                "python3-pytz",
                "python3-qrcode",
                "python3-reportlab",
                "python3-requests",
                "python3-six",
                "python3-vobject",
                "python3-xlrd",
                "python3-xlwt",
                "python3-zeep",
            ]
        )
        self.pip_dep = set(
            [
                "XlsxWriter==1.1.2",
                "mutagen==1.43.0",
                "ofxparse==0.19",
                "pyusb==1.0.2",
                "vatnumber==1.2",
                "webvtt-py==0.4.2",
            ]
        )

    def setup_postgresql(self):
        s.call(["systemctl", "enable", "postgresql"])
        s.call(["systemctl", "start", "postgresql"])
        super().setup_postgresql()

    def _install(self, packages=[]):
        if packages:
            s.call(["zypper", "install"] + packages)


def get_driver(args):
    # Choose OS
    os_choices = OrderedDict()
    os_choices["1"] = ("Ubuntu 20.04 / 18.04", DriverUbuntu2004)
    os_choices["2"] = ("Debian 10", DriverDebian10)
    os_choices["3"] = ("Fedora 31", DriverFedora31)
    os_choices["4"] = ("OpenSUSE 15.1", DriverSuse15)

    print("Choose your operating system:")
    while True:
        for k, v in os_choices.items():
            print("  {} : {}".format(k, v[0]))
        print("  0 : exit this installer")

        os_choice = input("Your choice: ")
        if os_choice == "0":
            sys.exit()
        if os_choices.get(os_choice):
            return os_choices[os_choice][1](args)
        else:
            print("\nIncorrect choice! Please choose from the following list:")


def install(args):
    driver = get_driver(args)
    driver.set_config()
    driver.install_dep()
    driver.install_pip_dep()
    driver.setup_postgresql()
    driver.download_and_extract()
    driver.copy_ffmpeg()
    driver.init_koozic()
    driver.enable_systemd()
    driver.install_message()


def uninstall():
    driver = get_driver(args)
    driver.get_config()
    driver.clean_system()
    driver.clean_files()


def upgrade():
    driver = get_driver(args)
    driver.get_config()
    driver.upgrade()


# Only root can run the installer
if os.getuid():
    sys.exit("Please execute this script as root! Exiting...")

# Parse arguments
parser = argparse.ArgumentParser(description="KooZic (un)-installer")
parser.add_argument(
    "mode", choices=["install", "uninstall", "upgrade"], help="install or uninstall mode"
)
parser.add_argument("-u", "--user", default="root", help="user running koozic")
parser.add_argument("-d", "--directory", default="/opt", help="install directory")
args = parser.parse_args()

# Get latest version
url_versions = "https://raw.githubusercontent.com/DocMarty84/koozic/{}/VERSIONS.md".format(BRANCH)
lines = requests.get(url_versions).iter_lines(decode_unicode=True)
DOWN_URL = DOWN_URL.format(v=next(lines))

if args.mode == "install":
    # Check directory
    dir = os.path.join(args.directory, K_NAME_DIR)
    if os.path.exists(dir):
        sys.exit(
            "Directory {} already exists. Delete this directory of choose another one.".format(dir)
        )
    install(args)

elif args.mode == "uninstall":
    uninstall()

elif args.mode == "upgrade":
    upgrade()
