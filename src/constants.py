# Copyright 2024 Omnivector, LLC.
# See LICENSE file for licensing details.

"""This module provides constants for the slurmctld-operator charm."""

from pathlib import Path

_SNAP_COMMON = Path("/var/snap/slurm/common")

SLURM_USER = "root"
SLURM_GROUP = "root"
SLURM_CONF_PATH = _SNAP_COMMON / "etc/slurm/slurm.conf"
CGROUP_CONF_PATH = _SNAP_COMMON / "etc/slurm/cgroup.conf"
JWT_KEY_PATH = _SNAP_COMMON / "var/lib/slurm/slurmctld/jwt_hs256.key"

CHARM_MAINTAINED_SLURM_CONF_PARAMETERS = {
    "AuthAltParameters": f"jwt_key={JWT_KEY_PATH}",
    "AuthAltTypes": "auth/jwt",
    "AuthInfo": f"{_SNAP_COMMON}/run/munge/munged.socket.2",
    "AuthType": "auth/munge",
    "GresTypes": "gpu",
    "HealthCheckInterval": "600",
    "HealthCheckNodeState": "ANY,CYCLE",
    "HealthCheckProgram": "/usr/sbin/omni-nhc-wrapper",
    "MailProg": "/usr/bin/mail.mailutils",
    "PlugStackConfig": "/etc/slurm/plugstack.conf.d/plugstack.conf",
    "SelectType": "select/cons_tres",
    "SlurmctldPort": "6817",
    "SlurmdPort": "6818",
    "StateSaveLocation": f"{_SNAP_COMMON}/var/lib/slurm/slurmctld",
    "SlurmdSpoolDir": f"{_SNAP_COMMON}/var/lib/slurm/slurmd",
    "SlurmctldParameters": "enable_configless",
    "SlurmctldLogFile": f"{_SNAP_COMMON}/var/log/slurm/slurmctld.log",
    "SlurmdLogFile": f"{_SNAP_COMMON}/var/log/slurm/slurmd.log",
    "SlurmdPidFile": f"{_SNAP_COMMON}/run/slurmd.pid",
    "SlurmctldPidFile": f"{_SNAP_COMMON}/run/slurmctld.pid",
    "SlurmUser": SLURM_USER,
    "SlurmdUser": "root",
    "RebootProgram": '"/usr/sbin/reboot --reboot"',
}
