#!/usr/bin/env python3
# Copyright 2024 Omnivector, LLC
# See LICENSE file for licensing details.

"""SlurmctldCharm."""

import logging
import shlex
import subprocess
from typing import Any, Dict, List, Optional, Union

from charms.fluentbit.v0.fluentbit import FluentbitClient  # type: ignore
from interface_slurmctld_peer import (
    SlurmctldPeer,
    SlurmctldPeerAvailableEvent,
)
from interface_slurmd import (
    Slurmd,
    SlurmdAvailableEvent,
    SlurmdBrokenEvent,
    SlurmdDepartedEvent,
)
from interface_slurmdbd import (
    Slurmdbd,
    SlurmdbdAvailableEvent,
    SlurmdbdUnavailableEvent,
)
from interface_slurmrestd import (
    Slurmrestd,
    SlurmrestdAvailableEvent,
    SlurmrestdUnavailableEvent,
)
from ops import (
    ActionEvent,
    ConfigChangedEvent,
    InstallEvent,
    RelationCreatedEvent,
    UpdateStatusEvent,
    UpgradeCharmEvent,
)
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from slurmctld_ops import SlurmctldManager, default_parameters

logger = logging.getLogger()


class SlurmctldCharm(CharmBase):
    """Slurmctld lifecycle events."""

    _stored = StoredState()

    def __init__(self, *args):
        """Init _stored attributes and interfaces, observe events."""
        super().__init__(*args)

        self._stored.set_default(
            jwt_key=str(),
            munge_key=str(),
            slurm_installed=False,
            slurmd_available=False,
            slurmrestd_available=False,
            slurmdbd_available=False,
            new_nodes=[],
        )

        self._slurm_manager = SlurmctldManager(self, "slurmctld")

        self._slurmd = Slurmd(self, "slurmd")
        self._slurmdbd = Slurmdbd(self, "slurmdbd")
        self._slurmrestd = Slurmrestd(self, "slurmrestd")
        self._slurmctld_peer = SlurmctldPeer(self, "slurmctld-peer")

        self._fluentbit = FluentbitClient(self, "fluentbit")

        event_handler_bindings = {
            # Charm lifecycle hook events
            self.on.install: self._on_install,
            self.on.upgrade_charm: self._on_upgrade,
            self.on.update_status: self._on_update_status,
            self.on.config_changed: self._on_write_slurm_config,
            # slurmdbd lifecycle hook events
            self._slurmdbd.on.slurmdbd_available: self._on_slurmdbd_available,
            self._slurmdbd.on.slurmdbd_unavailable: self._on_slurmdbd_unavailable,
            # slurmd lifecycle hook events
            self._slurmd.on.slurmd_available: self._on_write_slurm_config,
            self._slurmd.on.slurmd_unavailable: self._on_write_slurm_config,
            self._slurmd.on.slurmd_departed: self._on_write_slurm_config,
            # slurmrestd lifecycle hook events
            self._slurmrestd.on.slurmrestd_available: self._on_slurmrestd_available,
            self._slurmrestd.on.slurmrestd_unavailable: self._on_slurmrestd_unavailable,
            # NOTE: a second slurmctld should get the jwt/munge keys and configure them
            self._slurmctld_peer.on.slurmctld_peer_available: self._on_write_slurm_config,
            # fluentbit
            self.on["fluentbit"].relation_created: self._on_fluentbit_relation_created,
            # actions
            self.on.show_current_config_action: self._on_show_current_config,
            self.on.drain_action: self._drain_nodes_action,
            self.on.resume_action: self._resume_nodes_action,
        }
        for event, handler in event_handler_bindings.items():
            self.framework.observe(event, handler)

    @property
    def new_nodes(self) -> List[Any]:
        """Return new_nodes from StoredState.

        Note: Ignore the attr-defined for now until this is fixed upstream.
        """
        return list(self._stored.new_nodes)  # type: ignore [call-overload]

    @new_nodes.setter
    def new_nodes(self, new_nodes: List[Any]) -> None:
        """Set the new nodes."""
        self._stored.new_nodes = new_nodes

    def _on_install(self, event: InstallEvent) -> None:
        """Perform installation operations for slurmctld."""
        self.unit.status = WaitingStatus("Installing slurmctld")

        successful_installation = self._slurm_manager.install()

        self.unit.set_workload_version(self._slurm_manager.version())

        if successful_installation:
            self._stored.slurm_installed = True

            # Store the munge_key and jwt_rsa key in the stored state.
            # NOTE: Use leadership settings instead of stored state when
            # leadership settings support becomes available in the framework.
            if self._is_leader():
                # NOTE the backup controller should also have the jwt and munge
                #      keys configured. We should move these information to the
                #      peer relation.
                self._stored.jwt_rsa = self._slurm_manager.generate_jwt_rsa()
                self._stored.munge_key = self._slurm_manager.get_munge_key()
                self._slurm_manager.write_jwt_rsa(self.get_jwt_rsa())
            else:
                # NOTE: the secondary slurmctld should get the jwt and munge
                #       keys from the peer relation here
                logger.debug("secondary slurmctld")

            # all slurmctld should restart munged here, as it would assure
            # munge is working
            self._slurm_manager.restart_munged()
        else:
            self.unit.status = BlockedStatus("Error installing slurmctld")
            event.defer()

        self._check_status()

    def _on_upgrade(self, event: UpgradeCharmEvent) -> None:
        """Perform upgrade operations."""
        self.unit.set_workload_version(self._slurm_manager.version())

    def _on_update_status(self, event: UpdateStatusEvent) -> None:
        """Handle update status."""
        self._check_status()

    def _on_show_current_config(self, event: ActionEvent) -> None:
        """Show current slurm.conf."""
        slurm_conf = self._slurm_manager.slurm_conf_path.read_text()
        event.set_results({"slurm.conf": slurm_conf})

    def _on_fluentbit_relation_created(self, event: RelationCreatedEvent) -> None:
        """Set up Fluentbit log forwarding."""
        logger.debug("## Configuring fluentbit")
        cfg = []
        cfg.extend(self._slurm_manager.fluentbit_config_nhc)
        cfg.extend(self._slurm_manager.fluentbit_config_slurm)
        self._fluentbit.configure(cfg)

    def _on_slurmrestd_available(self, event: SlurmrestdAvailableEvent) -> None:
        """Check that we have what we nSet slurm_config on the relation when slurmrestd available."""
        if not self._check_status():
            event.defer()

        if not self._assemble_slurm_config():
            self.unit.status = BlockedStatus("Cannot generate slurm_config - deferring event.")
            event.defer()

    def _on_slurmrestd_unavailable(self, event: SlurmrestdUnavailableEvent) -> None:
        """Set slurmrestd_available to False."""
        self.set_slurmrestd_available(False)

    def _on_slurmdbd_available(self, event: SlurmdbdAvailableEvent) -> None:
        self._set_slurmdbd_available(True)
        self._on_write_slurm_config(event)

    def _on_slurmdbd_unavailable(self, event: SlurmdbdUnavailableEvent) -> None:
        self._set_slurmdbd_available(False)
        self._check_status()

    def _drain_nodes_action(self, event: ActionEvent) -> None:
        """Drain specified nodes."""
        nodes = event.params["nodename"]
        reason = event.params["reason"]

        logger.debug(f"#### Draining {nodes} because {reason}.")
        event.log(f"Draining {nodes} because {reason}.")

        try:
            cmd = f'scontrol update nodename={nodes} state=drain reason="{reason}"'
            subprocess.check_output(shlex.split(cmd))
            event.set_results({"status": "draining", "nodes": nodes})
        except subprocess.CalledProcessError as e:
            event.fail(message=f"Error draining {nodes}: {e.output}")

    def _resume_nodes_action(self, event: ActionEvent) -> None:
        """Resume specified nodes."""
        nodes = event.params["nodename"]

        logger.debug(f"#### Resuming {nodes}.")
        event.log(f"Resuming {nodes}.")

        try:
            cmd = f"scontrol update nodename={nodes} state=resume"
            subprocess.check_output(shlex.split(cmd))
            event.set_results({"status": "resuming", "nodes": nodes})
        except subprocess.CalledProcessError as e:
            event.fail(message=f"Error resuming {nodes}: {e.output}")

    def _on_write_slurm_config(
        self,
        event: Union[
            ConfigChangedEvent,
            SlurmctldPeerAvailableEvent,
            SlurmdAvailableEvent,
            SlurmdBrokenEvent,
            SlurmdDepartedEvent,
            SlurmdbdAvailableEvent,
        ],
    ) -> None:
        """Check that we have what we need before we proceed."""
        logger.debug("### Slurmctld - _on_write_slurm_config()")

        # only the leader should write the config, restart, and scontrol reconf
        if not self._is_leader():
            return

        if not self._check_status():
            event.defer()
            return

        if slurm_config := self._assemble_slurm_config():
            self._slurm_manager.write_slurm_conf(slurm_config)

            # Write out any user_supplied_cgroup_parameters to /etc/slurm/cgroup.conf.
            if user_supplied_cgroup_parameters := self.config.get("cgroup-parameters"):
                self._slurm_manager.write_cgroup_conf(user_supplied_cgroup_parameters)

            # Restart is needed if nodes are added/removed from the cluster, but since we don't
            # currently have a method of identifying if nodes are being added or removed, simply
            # restart every time after writing slurm.conf.
            self._slurm_manager.restart_slurmctld()
            self._slurm_manager.slurm_cmd("scontrol", "reconfigure")

            # Send the custom NHC parameters to all slurmd.
            #
            # Todo (jamesbeedy): We can clean this up by only sending the health-check-params
            #                    to slurmd using config-changed event hook.
            self._slurmd.set_nhc_params(self.config.get("health-check-params"))

            # Transitioning Nodes
            #
            # 1) Identify transitioning_nodes by comparing the new_nodes in StoredState with the
            #    new_nodes that come from slurmd relation data.
            #
            # 2) If there are transitioning_nodes, resume them, and update the new_nodes in
            #    StoredState.
            new_nodes_from_stored_state = self.new_nodes
            new_nodes_from_slurm_config = self._get_new_node_names_from_slurm_config(slurm_config)

            transitioning_nodes: list = [
                node
                for node in new_nodes_from_stored_state
                if node not in new_nodes_from_slurm_config
            ]

            if len(transitioning_nodes) > 0:
                self._resume_nodes(transitioning_nodes)
                self.new_nodes = new_nodes_from_slurm_config.copy()

            # slurmrestd needs the slurm.conf file, so send it every time it changes.
            if self._stored.slurmrestd_available is not False:
                self._slurmrestd.set_slurm_config_on_app_relation_data(slurm_config)
                # NOTE: scontrol reconfigure does not restart slurmrestd
                self._slurmrestd.restart_slurmrestd()
        else:
            logger.debug("## Should rewrite slurm.conf, but we don't have it. " "Deferring.")
            event.defer()

    @property
    def hostname(self) -> str:
        """Return the hostname."""
        return self._slurm_manager.hostname

    @property
    def port(self) -> str:
        """Return the port."""
        return self._slurm_manager.port

    @property
    def cluster_name(self) -> str:
        """Return the cluster name."""
        return self.config.get("cluster-name") or default_parameters["ClusterName"]

    def _get_user_supplied_parameters(self) -> Dict[str, str]:
        """Gather, parse, and return the user supplied parameters."""
        user_supplied_parameters = {}
        if custom_config := self.config.get("slurm-conf-parameters"):
            user_supplied_parameters = {
                line.split("=")[0]: line.split("=")[1]
                for line in custom_config.split("\n")
                if "#" not in line and line != ""
            }
        return user_supplied_parameters

    def _get_new_node_names_from_slurm_config(
        self, slurm_config: Dict[str, Any]
    ) -> List[Optional[str]]:
        """Given the slurm_config, return the nodes that are DownNodes with reason 'New node.'."""
        new_node_names: list = []
        if down_nodes_from_slurm_config := slurm_config.get("down_nodes"):
            for down_nodes_entry in down_nodes_from_slurm_config:

                for down_node_name in down_nodes_entry["DownNodes"]:
                    if down_nodes_entry["Reason"] == "New node.":
                        new_node_names.append(down_node_name)
        return new_node_names

    def _get_slurmdbd_parameters(self) -> Dict[str, str]:
        """Return the slurmdbd parameters for the slurm.conf."""
        slurmdbd_parameters = {}
        if slurmdbd_info := self._slurmdbd.get_slurmdbd_info():
            slurmdbd_parameters = {
                "AccountingStorageType": "accounting_storage/slurmdbd",
                "AccountingStorageHost": slurmdbd_info["active_slurmdbd_hostname"],
                "AccountingStoragePort": slurmdbd_info["active_slurmdbd_port"],
                "AccountingStoragePass": f"{self._slurm_manager.munge_socket}",
            }
        return slurmdbd_parameters

    def _get_parameters(self) -> Dict[str, str]:
        """Return the slurm.conf parameters provided by this charm."""
        slurm_manager = self._slurm_manager
        mandatory_slurmctld_parameters = ["enable_configless"]

        default_health_check_interval = "600"
        default_health_check_state = "ANY,CYCLE"
        health_check_program = "/usr/sbin/omni-nhc-wrapper"

        charm_maintained_parameters = slurm_manager.get_charm_maintained_slurm_config_parameters()

        user_supplied_parameters = self._get_user_supplied_parameters()

        # Preprocess merging slurmctld_parameters if they exist in the context
        slurmctld_parameters = mandatory_slurmctld_parameters
        if user_supplied_slurmctld_parameters := user_supplied_parameters.get(
            "SlurmctldParameters"
        ):
            slurmctld_parameters = list(
                set(slurmctld_parameters + user_supplied_slurmctld_parameters.split(","))
            )
            user_supplied_parameters.pop("SlurmctldParameters")

        slurmctld_info = self._slurmctld_peer.get_slurmctld_info()

        return {
            "ClusterName": self.cluster_name,
            "ControlAddr": slurmctld_info["ControlAddr"],
            "ControlMachine": slurmctld_info["ControlMachine"],
            "HealthCheckInterval": self.config.get("health-check-interval")
            or default_health_check_interval,
            "HealthCheckNodeState": self.config.get("health-check-state")
            or default_health_check_state,
            "HealthCheckProgram": health_check_program,
            "SlurmctldParameters": ",".join(slurmctld_parameters),
            "ProctrackType": self.config.get("proctrack-type") or "proctrack/linuxproc",
            **charm_maintained_parameters,
            **user_supplied_parameters,
            **self._get_slurmdbd_parameters(),
        }

    def _assemble_slurm_config(self) -> Dict[Any, Any]:
        """Assemble and return the slurm config."""
        # If we don't have slurmdbd relation then there isn't much we can do so bail out.
        if not self._get_slurmdbd_parameters():
            return {}

        new_nodes, nodes, partitions = self._slurmd.get_new_nodes_and_nodes_and_partitions()

        slurm_conf = {
            **self._get_parameters(),
            "down_nodes": new_nodes,
            "partitions": partitions,
            "nodes": nodes,
        }

        logger.debug(f"slurm.conf: {slurm_conf}")
        return slurm_conf

    def set_slurmd_available(self, flag: bool) -> None:
        """Set stored value of slurmd available."""
        self._stored.slurmd_available = flag

    def _set_slurmdbd_available(self, flag: bool) -> None:
        """Set stored value of slurmdbd available."""
        self._stored.slurmdbd_available = flag

    def set_slurmrestd_available(self, flag: bool) -> None:
        """Set stored value of slurmdrest available."""
        self._stored.slurmrestd_available = flag

    def _is_leader(self) -> bool:
        return self.model.unit.is_leader()

    def is_slurm_installed(self) -> bool:
        """Return true/false based on whether or not slurm is installed."""
        return False if self._stored.slurm_installed is not True else True

    def _check_status(self) -> bool:  # noqa C901
        """Check for all relations and set appropriate status.

        This charm needs these conditions to be satisfied in order to be ready:
        - Slurm components installed.
        - Munge running.
        - slurmdbd node running.
        - slurmd inventory.
        """
        # NOTE: slurmd and slurmrestd are not needed for slurmctld to work,
        #       only for the cluster to operate. But we need slurmd inventory
        #       to assemble slurm.conf
        if self._stored.slurm_installed is not True:
            self.unit.status = BlockedStatus("Error installing slurmctld")
            return False

        if not self._slurm_manager.check_munged():
            self.unit.status = BlockedStatus("Error configuring munge key")
            return False

        # statuses of mandatory components:
        # - joined: someone executed juju relate slurmctld foo
        # - available: the units exchanged data through the relation
        # NOTE: slurmrestd is not mandatory for the cluster to work, that's why
        #       it is not acounted for in here
        statuses = {
            "slurmd": {
                "available": self._stored.slurmd_available,
                "joined": self._slurmd.is_joined,
            },
            "slurmdbd": {
                "available": self._stored.slurmdbd_available,
                "joined": self._slurmdbd.is_joined,
            },
        }

        relations_needed = []
        waiting_on = []
        for component in statuses.keys():
            if not statuses[component]["joined"]:
                relations_needed.append(component)
            if not statuses[component]["available"]:
                waiting_on.append(component)

        if len(relations_needed):
            msg = f"Need relations: {','.join(relations_needed)}"
            self.unit.status = BlockedStatus(msg)
            return False

        if len(waiting_on):
            msg = f"Waiting on: {','.join(waiting_on)}"
            self.unit.status = WaitingStatus(msg)
            return False

        self.unit.status = ActiveStatus("slurmctld available")
        return True

    def get_munge_key(self) -> Optional[str]:
        """Get the stored munge key."""
        return str(self._stored.munge_key)

    def get_jwt_rsa(self) -> Optional[str]:
        """Get the stored jwt_rsa key."""
        return str(self._stored.jwt_rsa)

    def _resume_nodes(self, nodelist: List[str]) -> None:
        """Run scontrol to resume the specified node list."""
        nodes = ",".join(nodelist)
        update_cmd = f"update nodename={nodes} state=resume"
        self._slurm_manager.slurm_cmd("scontrol", update_cmd)


if __name__ == "__main__":
    main(SlurmctldCharm)
