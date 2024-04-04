# Copyright 2024 Omnivector, LLC.
# See LICENSE file for licensing details.
"""This module provides the SlurmManager."""

import logging
import os
import shlex
import shutil
import socket
import subprocess
from base64 import b64decode, b64encode
from pathlib import Path
from typing import Dict

import charms.operator_libs_linux.v0.apt as apt  # type: ignore [import-untyped]
import charms.operator_libs_linux.v1.systemd as systemd  # type: ignore [import-untyped]
import distro
from Crypto.PublicKey import RSA
from jinja2 import Environment, FileSystemLoader
from ops.framework import (
    Object,
    StoredState,
)

logger = logging.getLogger()


TEMPLATE_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "templates"


class SlurmctldException(BaseException):
    """Slurmctld generic exception."""

    def __init__(self, msg):
        self.msg = msg

        super().__init__(msg)

    def __str__(self):
        """Return the exception message."""
        return self.msg


SLURM_PPA_KEY: str = """
-----BEGIN PGP PUBLIC KEY BLOCK-----
Comment: Hostname:
Version: Hockeypuck 2.1.1-10-gec3b0e7

xsFNBGTuZb8BEACtJ1CnZe6/hv84DceHv+a54y3Pqq0gqED0xhTKnbj/E2ByJpmT
NlDNkpeITwPAAN1e3824Me76Qn31RkogTMoPJ2o2XfG253RXd67MPxYhfKTJcnM3
CEkmeI4u2Lynh3O6RQ08nAFS2AGTeFVFH2GPNWrfOsGZW03Jas85TZ0k7LXVHiBs
W6qonbsFJhshvwC3SryG4XYT+z/+35x5fus4rPtMrrEOD65hij7EtQNaE8owuAju
Kcd0m2b+crMXNcllWFWmYMV0VjksQvYD7jwGrWeKs+EeHgU8ZuqaIP4pYHvoQjag
umqnH9Qsaq5NAXiuAIAGDIIV4RdAfQIR4opGaVgIFJdvoSwYe3oh2JlrLPBlyxyY
dayDifd3X8jxq6/oAuyH1h5K/QLs46jLSR8fUbG98SCHlRmvozTuWGk+e07ALtGe
sGv78ToHKwoM2buXaTTHMwYwu7Rx8LZ4bZPHdersN1VW/m9yn1n5hMzwbFKy2s6/
D4Q2ZBsqlN+5aW2q0IUmO+m0GhcdaDv8U7RVto1cWWPr50HhiCi7Yvei1qZiD9jq
57oYZVqTUNCTPxi6NeTOdEc+YqNynWNArx4PHh38LT0bqKtlZCGHNfoAJLPVYhbB
b2AHj9edYtHU9AAFSIy+HstET6P0UDxy02IeyE2yxoUBqdlXyv6FL44E+wARAQAB
zRxMYXVuY2hwYWQgUFBBIGZvciBVYnVudHUgSFBDwsGOBBMBCgA4FiEErocSHcPk
oLD4H/Aj9tDF1ca+s3sFAmTuZb8CGwMFCwkIBwIGFQoJCAsCBBYCAwECHgECF4AA
CgkQ9tDF1ca+s3sz3w//RNawsgydrutcbKf0yphDhzWS53wgfrs2KF1KgB0u/H+u
6Kn2C6jrVM0vuY4NKpbEPCduOj21pTCepL6PoCLv++tICOLVok5wY7Zn3WQFq0js
Iy1wO5t3kA1cTD/05v/qQVBGZ2j4DsJo33iMcQS5AjHvSr0nu7XSvDDEE3cQE55D
87vL7lgGjuTOikPh5FpCoS1gpemBfwm2Lbm4P8vGOA4/witRjGgfC1fv1idUnZLM
TbGrDlhVie8pX2kgB6yTYbJ3P3kpC1ZPpXSRWO/cQ8xoYpLBTXOOtqwZZUnxyzHh
gM+hv42vPTOnCo+apD97/VArsp59pDqEVoAtMTk72fdBqR+BB77g2hBkKESgQIEq
EiE1/TOISioMkE0AuUdaJ2ebyQXugSHHuBaqbEC47v8t5DVN5Qr9OriuzCuSDNFn
6SBHpahN9ZNi9w0A/Yh1+lFfpkVw2t04Q2LNuupqOpW+h3/62AeUqjUIAIrmfeML
IDRE2VdquYdIXKuhNvfpJYGdyvx/wAbiAeBWg0uPSepwTfTG59VPQmj0FtalkMnN
ya2212K5q68O5eXOfCnGeMvqIXxqzpdukxSZnLkgk40uFJnJVESd/CxHquqHPUDE
fy6i2AnB3kUI27D4HY2YSlXLSRbjiSxTfVwNCzDsIh7Czefsm6ITK2+cVWs0hNQ=
=cs1s
-----END PGP PUBLIC KEY BLOCK-----
"""


class Slurmctld:
    """Facilitate slurmctld package lifecycle ops."""

    _package_name: str = "slurmctld"
    _keyring_path: Path = Path("/usr/share/keyrings/slurm-wlm.asc")

    def _repo(self) -> apt.DebianRepository:
        """Return the slurmctld repo."""
        ppa_url: str = "https://ppa.launchpadcontent.net/ubuntu-hpc/slurm-wlm-23.02/ubuntu"
        sources_list: str = (
            f"deb [signed-by={self._keyring_path}] {ppa_url} {distro.codename()} main"
        )
        return apt.DebianRepository.from_repo_line(sources_list)

    def install(self) -> None:
        """Install the slurmctld package using lib apt."""
        # Install the key.
        if self._keyring_path.exists():
            self._keyring_path.unlink()
        self._keyring_path.write_text(SLURM_PPA_KEY)

        # Add the repo.
        repositories = apt.RepositoryMapping()
        repositories.add(self._repo())

        # Install the slurmctld, slurm-client packages.
        try:
            # Run `apt-get update`
            apt.update()
            apt.add_package(["mailutils", "logrotate"])
            apt.add_package([self._package_name, "slurm-client"])
        except apt.PackageNotFoundError:
            logger.error(f"{self._package_name} not found in package cache or on system")
        except apt.PackageError as e:
            logger.error(f"Could not install {self._package_name}. Reason: %s", e.message)

    def uninstall(self) -> None:
        """Uninstall the slurmctld package using libapt."""
        # Uninstall the slurmctld package.
        if apt.remove_package(self._package_name):
            logger.info(f"{self._package_name} removed from system.")
        else:
            logger.error(f"{self._package_name} not found on system")

        # Disable the slurmctld repo.
        repositories = apt.RepositoryMapping()
        repositories.disable(self._repo())

        # Remove the key.
        if self._keyring_path.exists():
            self._keyring_path.unlink()

    def upgrade_to_latest(self) -> None:
        """Upgrade slurmctld to latest."""
        try:
            slurmctld = apt.DebianPackage.from_system(self._package_name)
            slurmctld.ensure(apt.PackageState.Latest)
            logger.info("updated vim to version: %s", slurmctld.version.number)
        except apt.PackageNotFoundError:
            logger.error("a specified package not found in package cache or on system")
        except apt.PackageError as e:
            logger.error("could not install package. Reason: %s", e.message)

    def version(self) -> str:
        """Return the slurmctld version."""
        try:
            slurmctld = apt.DebianPackage.from_installed_package(self._package_name)
        except apt.PackageNotFoundError:
            logger.error(f"{self._package_name} not found on system")
        return slurmctld.version.number


class SlurmctldManager(Object):
    """SlurmctldManager."""

    _stored = StoredState()

    def __init__(self, charm, component):
        """Set the initial attribute values."""
        super().__init__(charm, component)

        self._charm = charm

        self._stored.set_default(slurm_installed=False)
        self._stored.set_default(slurm_version_set=False)

        """Set the initial values for attributes in the base class."""
        self._slurm_conf_template_name = "slurm.conf.tmpl"
        self._slurm_conf_path = self._slurm_conf_dir / "slurm.conf"

        self._slurmd_log_file = self._slurm_log_dir / "slurmd.log"
        self._slurmctld_log_file = self._slurm_log_dir / "slurmctld.log"

        self._slurmd_pid_file = self._slurm_pid_dir / "slurmd.pid"
        self._slurmctld_pid_file = self._slurm_pid_dir / "slurmctld.pid"

        # NOTE: Come back to mitigate this configless cruft
        self._slurmctld_parameters = ["enable_configless"]

        self._slurm_conf_template_location = TEMPLATE_DIR / self._slurm_conf_template_name

    @property
    def hostname(self) -> str:
        """Return the hostname."""
        return socket.gethostname().split(".")[0]

    @property
    def port(self) -> str:
        """Return the port."""
        return "6817"

    @property
    def slurm_conf_path(self) -> Path:
        """Return the slurm conf path."""
        return self._slurm_conf_path

    def slurm_is_active(self) -> bool:
        """Return True if the slurm component is running."""
        try:
            cmd = f"systemctl is-active {self._slurm_systemd_service}"
            r = subprocess.check_output(shlex.split(cmd)).decode().strip().lower()
            logger.debug(f"### systemctl is-active {self._slurm_systemd_service}: {r}")
            return "active" == r
        except subprocess.CalledProcessError as e:
            logger.error(f"#### Error checking if slurm is active: {e}")
            return False
        return False

    @property
    def _slurm_bin_dir(self) -> Path:
        """Return the directory where the slurm bins live."""
        return Path("/usr/bin")

    @property
    def _slurm_conf_dir(self) -> Path:
        """Return the directory for Slurm configuration files."""
        return Path("/etc/slurm")

    @property
    def _slurm_spool_dir(self) -> Path:
        """Return the directory for slurmd's state information."""
        return Path("/var/spool/slurmd")

    @property
    def _slurm_state_dir(self) -> Path:
        """Return the directory for slurmctld's state information."""
        return Path("/var/spool/slurmctld")

    @property
    def _slurm_log_dir(self) -> Path:
        """Return the directory for Slurm logs."""
        return Path("/var/log/slurm")

    @property
    def _slurm_pid_dir(self) -> Path:
        """Return the directory for Slurm PID file."""
        return Path("/var/run/")

    @property
    def _jwt_rsa_key_file(self) -> Path:
        """Return the jwt rsa key file path."""
        return self._slurm_state_dir / "jwt_hs256.key"

    @property
    def _munge_key_path(self) -> Path:
        """Return the full path to the munge key."""
        return Path("/etc/munge/munge.key")

    @property
    def munge_socket(self) -> Path:
        """Return the munge socket."""
        return Path("/var/run/munge/munge.socket.2")

    @property
    def _munged_systemd_service(self) -> str:
        """Return the name of the Munge Systemd unit file."""
        return "munge.service"

    @property
    def _munge_user(self) -> str:
        """Return the user for munge daemon."""
        return "munge"

    @property
    def _munge_group(self) -> str:
        """Return the group for munge daemon."""
        return "munge"

    @property
    def _slurm_plugstack_dir(self) -> Path:
        """Return the directory to the SPANK plugins."""
        return Path("/etc/slurm/plugstack.conf.d")

    @property
    def _slurm_plugstack_conf(self) -> Path:
        """Return the full path to the root plugstack configuration file."""
        return self._slurm_conf_dir / "plugstack.conf"

    @property
    def _slurm_systemd_service(self) -> str:
        """Return the Slurm systemd unit file."""
        return "slurmctld.service"

    @property
    def _slurm_user(self) -> str:
        """Return the slurm user."""
        return "slurm"

    @property
    def _slurm_user_id(self) -> str:
        """Return the slurm user ID."""
        return "64030"

    @property
    def _slurm_group(self) -> str:
        """Return the slurm group."""
        return "slurm"

    @property
    def _slurm_group_id(self) -> str:
        """Return the slurm group ID."""
        return "64030"

    @property
    def _slurmd_user(self) -> str:
        """Return the slurmd user."""
        return "root"

    @property
    def _slurmd_group(self) -> str:
        """Return the slurmd group."""
        return "root"

    def create_systemd_override_for_nofile(self) -> None:
        """Create the override.conf file for slurm systemd service."""
        systemd_override_dir = Path(f"/etc/systemd/system/{self._slurm_systemd_service}.d")
        if not systemd_override_dir.exists():
            systemd_override_dir.mkdir(exist_ok=True)

        systemd_override_conf = systemd_override_dir / "override.conf"
        systemd_override_conf_tmpl = TEMPLATE_DIR / "override.conf"

        shutil.copyfile(systemd_override_conf_tmpl, systemd_override_conf)

    def get_charm_maintained_slurm_config_parameters(self) -> Dict[str, str]:
        """Return slurm.conf parameters maintained my this charm."""
        return {
            "AuthInfo": f"socket={self.munge_socket}",
            "MailProg": f"{self._mail_prog}",
            "StateSaveLocation": f"{self._slurm_state_dir}",
            "SlurmdSpoolDir": f"{self._slurm_spool_dir}",
            "PluginDir": f"{self._slurm_plugin_dir}",
            "SlurmdLogFile": f"{self._slurmd_log_file}",
            "SlurmctldLogFile": f"{self._slurmctld_log_file}",
            "SlurmdPidFile": f"{self._slurmd_pid_file}",
            "SlurmctldPidFile": f"{self._slurmctld_pid_file}",
            "AuthAltParameters": f"jwt_key={self._jwt_rsa_key_file}",
            "PlugStackConfig": f"{self._slurm_plugstack_conf}",
            "SlurmUser": self._slurm_user,
            "SlurmdUser": self._slurmd_user,
            "RebootProgram": '"/usr/sbin/reboot --reboot"',
        }

    def write_slurm_conf(self, slurm_conf: dict) -> None:
        """Render the context to a template, adding in common configs."""
        template_name = self._slurm_conf_template_name
        source = self._slurm_conf_template_location
        target = self._slurm_conf_path

        if not isinstance(slurm_conf, dict):
            raise TypeError("Incorrect type for config.")

        if not source.exists():
            raise FileNotFoundError("The slurm config template cannot be found.")

        rendered_template = Environment(loader=FileSystemLoader(TEMPLATE_DIR)).get_template(
            template_name
        )

        if target.exists():
            target.unlink()

        target.write_text(rendered_template.render(slurm_conf))

        user_group = f"{self._slurm_user}:{self._slurm_group}"
        subprocess.call(["chown", user_group, target])

    def write_munge_key(self, munge_key) -> None:
        """Base64 decode and write the munge key."""
        key = b64decode(munge_key.encode())
        self._munge_key_path.write_bytes(key)

    def write_jwt_rsa(self, jwt_rsa) -> None:
        """Write the jwt_rsa key."""
        # Remove jwt_rsa if exists.
        if self._jwt_rsa_key_file.exists():
            self._jwt_rsa_key_file.write_bytes(os.urandom(2048))
            self._jwt_rsa_key_file.unlink()

        # Write the jwt_rsa key to the file and chmod 0600,
        # chown to slurm_user.
        self._jwt_rsa_key_file.write_text(jwt_rsa)
        self._jwt_rsa_key_file.chmod(0o600)
        subprocess.call(
            [
                "chown",
                self._slurm_user,
                str(self._jwt_rsa_key_file),
            ]
        )

    def write_cgroup_conf(self, content):
        """Write the cgroup.conf file."""
        cgroup_conf_path = self._slurm_conf_dir / "cgroup.conf"
        if cgroup_conf_path.exists():
            cgroup_conf_path.unlink()
        cgroup_conf_path.write_text(content)

    def get_munge_key(self) -> str:
        """Read the bytes, encode to base64, decode to a string, return."""
        munge_key = self._munge_key_path.read_bytes()
        return b64encode(munge_key).decode()

    def start_munged(self):
        """Start munge.service."""
        logger.debug("## Starting munge")

        munge = self._munged_systemd_service
        try:
            subprocess.check_output(["systemctl", "start", munge])
        except subprocess.CalledProcessError as e:
            logger.error(f"## Error starting munge: {e}")
            return False

        return self._is_active_munged()

    def _is_active_munged(self):
        munge = self._munged_systemd_service
        try:
            status = subprocess.check_output(f"systemctl is-active {munge}", shell=True)
            status = status.decode().strip()
            if "active" in status:
                logger.debug("#### Munge daemon active")
                return True
            else:
                logger.error(f"## Munge not running: {status}")
                return False
        except subprocess.CalledProcessError as e:
            logger.error(f"## Error querring munged - {e}")
            return False

    def check_munged(self) -> bool:
        """Check if munge is working correctly."""
        # check if systemd service unit is active
        if not self._is_active_munged():
            return False

        # check if munge is working, i.e., can use the credentials correctly
        try:
            logger.debug("## Testing if munge is working correctly")
            cmd = "munge -n"
            munge = subprocess.Popen(
                shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if munge is not None:
                unmunge = subprocess.Popen(
                    ["unmunge"], stdin=munge.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                output = unmunge.communicate()[0].decode()
            if "Success" in output:
                logger.debug(f"## Munge working as expected: {output}")
                return True
            logger.error(f"## Munge not working: {output}")
        except subprocess.CalledProcessError as e:
            logger.error(f"## Error testing munge: {e}")

        return False

    @property
    def _slurm_plugin_dir(self) -> Path:
        # Debian packages slurm plugins in /usr/lib/x86_64-linux-gnu/slurm-wlm/
        # but we symlink /usr/lib64/slurm to it for compatibility with centos
        return Path("/usr/lib64/slurm/")

    @property
    def _mail_prog(self) -> Path:
        return Path("/usr/bin/mail.mailutils")

    def version(self) -> str:
        """Return slurm version."""
        return Slurmctld().version()

    def _install_slurm_from_apt(self) -> bool:
        """Install Slurm debs.

        Returns:
            bool: True on success and False otherwise.
        """
        Slurmctld().install()

        # symlink /usr/lib64/slurm -> /usr/lib/x86_64-linux-gnu/slurm-wlm/ to
        # have "standard" location across OSes
        lib64_slurm = Path("/usr/lib64/slurm")
        if lib64_slurm.exists():
            lib64_slurm.unlink()
        lib64_slurm.symlink_to("/usr/lib/x86_64-linux-gnu/slurm-wlm/")
        return True

    def upgrade(self) -> bool:
        """Run upgrade operations."""
        Slurmctld().upgrade_to_latest()

        # symlink /usr/lib64/slurm -> /usr/lib/x86_64-linux-gnu/slurm-wlm/ to
        # have "standard" location across OSes
        lib64_slurm = Path("/usr/lib64/slurm")
        if lib64_slurm.exists():
            lib64_slurm.unlink()
        lib64_slurm.symlink_to("/usr/lib/x86_64-linux-gnu/slurm-wlm/")
        return True

    def _setup_plugstack_dir_and_config(self) -> None:
        """Create plugstack directory and config."""
        # Create the plugstack config directory.
        plugstack_dir = self._slurm_plugstack_dir

        if plugstack_dir.exists():
            shutil.rmtree(plugstack_dir)

        plugstack_dir.mkdir()
        subprocess.call(["chown", "-R", f"{self._slurm_user}:{self._slurm_group}", plugstack_dir])

        # Write the plugstack config.
        plugstack_conf = self._slurm_plugstack_conf

        if plugstack_conf.exists():
            plugstack_conf.unlink()

        plugstack_conf.write_text(f"include {plugstack_dir}/*.conf")

    def _setup_paths(self) -> None:
        """Create needed paths with correct permissions."""
        user = f"{self._slurm_user}:{self._slurm_group}"

        all_paths = [
            self._slurm_conf_dir,
            self._slurm_log_dir,
            self._slurm_state_dir,
            self._slurm_spool_dir,
        ]
        for syspath in all_paths:
            if not syspath.exists():
                syspath.mkdir()
            subprocess.call(["chown", "-R", user, syspath])

    def restart_munged(self) -> bool:
        """Restart the munged process.

        Return True on success, and False otherwise.
        """
        try:
            logger.debug("## Restarting munge")
            systemd.service_restart("munge")
        except SlurmctldException("Cannot restart munge.") as e:  # type: ignore[misc]
            logger.error("Cannot restart munge.")
            logger.error(e)
            return False
        return self.check_munged()

    def restart_slurmctld(self) -> bool:
        """Restart the slurmctld process.

        Return True on success, and False otherwise.
        """
        try:
            logger.debug("## Restarting slurmctld")
            systemd.service_restart("slurmctld")
        except SlurmctldException("Cannot restart slurmctld.") as e:  # type: ignore[misc]
            logger.error("Error restarting slurmctld.")
            logger.error(e)
            return False
        return True

    def slurm_cmd(self, command, arg_string):
        """Run a slurm command."""
        try:
            return subprocess.call([f"{command}"] + arg_string.split())
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running {command} - {e}")
            return -1

    def generate_jwt_rsa(self) -> str:
        """Generate the rsa key to encode the jwt with."""
        return RSA.generate(2048).export_key("PEM").decode()

    @property
    def slurm_installed(self) -> bool:
        """Return the bool from the stored state.

        Note: Ignore return-value type for now until this is understood better.
        """
        return self._stored.slurm_installed  # type: ignore [return-value]

    @property
    def slurm_component(self) -> str:
        """Return the slurm component."""
        return "slurmctld"

    @property
    def fluentbit_config_slurm(self) -> list:
        """Return Fluentbit configuration parameters to forward Slurm logs."""
        log_file = self._slurmctld_log_file

        cfg = [
            {
                "input": [
                    ("name", "tail"),
                    ("path", log_file.as_posix()),
                    ("path_key", "filename"),
                    ("tag", "slurmctld"),
                    ("parser", "slurm"),
                ]
            },
            {
                "parser": [
                    ("name", "slurm"),
                    ("format", "regex"),
                    ("regex", r"^\[(?<time>[^\]]*)\] (?<log>.*)$"),
                    ("time_key", "time"),
                    ("time_format", "%Y-%m-%dT%H:%M:%S.%L"),
                ]
            },
            {
                "filter": [
                    ("name", "record_modifier"),
                    ("match", "slurmctld"),
                    ("record", "hostname ${HOSTNAME}"),
                    ("record", f"cluster-name {self._charm.cluster_name}"),
                    ("record", "service slurmctld"),
                ]
            },
        ]
        return cfg

    def install(self) -> bool:
        """Install slurmctld to the system.

        Returns:
            bool: True on success, False otherwise.
        """
        if not self._install_slurm_from_apt():
            return False

        # create needed paths with correct permissions
        self._setup_paths()

        self._setup_plugstack_dir_and_config()

        # remove slurm.conf, as the charms setup configless mode
        if self.slurm_conf_path.exists():
            self.slurm_conf_path.unlink()

        systemd.service_stop("slurmctld")
        systemd.service_stop("munge")

        self.create_systemd_override_for_nofile()
        systemd.daemon_reload()

        self._stored.slurm_installed = True

        return True

    @property
    def needs_reboot(self) -> bool:
        """Return True if the machine needs to be rebooted."""
        if Path("/var/run/reboot-required").exists():
            return True
        if Path("/bin/needs-restarting").exists():  # only on CentOS
            p = subprocess.run(["/bin/needs-restarting", "--reboothint"])
            if p.returncode == 1:
                return True

        return False


default_parameters: dict = {
    "ClusterName": "charmedhpc",
    "ProctrackType": "proctrack/linuxproc",
    "JobAcctGatherFrequency": "task=30",
    "JobAcctGatherType": "jobacct_gather/none",
}
