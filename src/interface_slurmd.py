#!/usr/bin/env python3
"""Interface slurmd."""
import json
import logging
from typing import List, Union

from ops.framework import EventBase, EventSource, Object, ObjectEvents, StoredState
from ops.model import Relation

logger = logging.getLogger()


class SlurmdAvailableEvent(EventBase):
    """Emitted when slurmd is available."""


class SlurmdBrokenEvent(EventBase):
    """Emitted when the slurmd relation is broken."""


class SlurmdDepartedEvent(EventBase):
    """Emitted when one slurmd departs."""


class SlurmdInventoryEvents(ObjectEvents):
    """SlurmClusterProviderRelationEvents."""

    slurmd_available = EventSource(SlurmdAvailableEvent)
    slurmd_unavailable = EventSource(SlurmdBrokenEvent)
    slurmd_departed = EventSource(SlurmdDepartedEvent)


class Slurmd(Object):
    """Slurmd inventory interface."""

    on = SlurmdInventoryEvents()

    def __init__(self, charm, relation_name):
        """Set self._relation_name and self.charm."""
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

        self.framework.observe(
            self._charm.on[self._relation_name].relation_created,
            self._on_relation_created,
        )
        self.framework.observe(
            self._charm.on[self._relation_name].relation_changed,
            self._on_relation_changed,
        )
        self.framework.observe(
            self._charm.on[self._relation_name].relation_departed,
            self._on_relation_departed,
        )
        self.framework.observe(
            self._charm.on[self._relation_name].relation_broken,
            self._on_relation_broken,
        )

    @property
    def _relations(self) -> Union[List[Relation], None]:
        return self.framework.model.relations.get(self._relation_name)

    @property
    def _num_relations(self):
        """Return the number of relations (number of slurmd applications)."""
        return len(self._relations)

    @property
    def is_joined(self):
        """Return True if self._relation is not None."""
        return True if self._relations else False

    def _on_relation_created(self, event):
        """Set our data on the relation."""
        # Check that slurm has been installed so that we know the munge key is
        # available. Defer if slurm has not been installed yet.
        if not self._charm.is_slurm_installed():
            event.defer()
            return

        # Get the munge_key and set it to the app data on the relation to be
        # retrieved on the other side by slurmd.
        app_relation_data = event.relation.data[self.model.app]
        app_relation_data["munge_key"] = self._charm.get_munge_key()

        # send the hostname and port to enable configless mode
        app_relation_data["slurmctld_host"] = self._charm.hostname
        app_relation_data["slurmctld_port"] = self._charm.port

        app_relation_data["cluster_name"] = self._charm.config.get("cluster-name")
        app_relation_data["nhc_params"] = self._charm.config.get("health-check-params", "#")

    def _on_relation_changed(self, event):
        """Emit slurmd available event and update new_nodes."""
        if app_data := event.relation.data.get(event.app):
            if app_data.get("partition_info"):
                self._charm.set_slurmd_available(True)
                self.on.slurmd_available.emit()
            else:
                event.defer()
                return

        # The event.unit data isn't in the relation data on the first occurrence
        # of relation-changed so we check for it here in order to prevent things
        # from blowing up. Not much to do if we don't have it other than log
        # and proceed.
        new_nodes_from_charm = self._charm.new_nodes
        if unit_data := event.relation.data.get(event.unit):
            if node := unit_data.get("node"):
                node = json.loads(node)
                if node.get("new_node") == True:
                    all_new_nodes = list(set(new_nodes_from_charm + [node.get("node_config").get("NodeName")]))
                    self._charm.new_nodes = all_new_nodes
            else:
                logger.debug(f"`node` data does not exist for unit: {event.unit}.")
                return
        else:
            logger.debug(f"No relation data for unit: {event.unit}.")

    def _on_relation_departed(self, event):
        """Handle hook when 1 unit departs."""
        self.on.slurmd_departed.emit()

    def _on_relation_broken(self, event):
        """Clear the munge key and emit the event if the relation is broken."""
        if self.framework.model.unit.is_leader():
            event.relation.data[self.model.app]["munge_key"] = ""

        # if there are other partitions, slurmctld needs to update the config
        # only. If there are no other partitions, we set slurmd_available to
        # False as well
        if self._num_relations:
            self.on.slurmd_available.emit()
        else:
            self._charm.set_slurmd_available(False)
            self.on.slurmd_unavailable.emit()

    def set_nhc_params(self, params: str = "") -> None:
        """Send NHC parameters to all slurmd."""
        # juju does not allow setting empty data/strings on the relation data,
        # so we set it to something that behaves like empty
        if not params or params == "":
            params = "#"

        logger.debug(f"## set_nhc_params: {params}")

        if self.is_joined:
            if relations := self._relations:
                for relation in relations:
                    app = self.model.app
                    relation.data[app]["nhc_params"] = params
        else:
            logger.debug("## slurmd not joined")

    def get_new_nodes_and_nodes_and_partitions(self):
        """Return the new_nodes, nodes and partitions configuration.

        Iterate over the relation data to assemble the nodes, new_nodes
        and partition configuration.
        """
        partitions = {}
        nodes = {}
        new_nodes = []

        for relation in self._relations:

            app = relation.app
            units = relation.units

            if app_data := relation.data.get(app):
                if partition := app_data.get("partition_config"):
                    partition_as_dict = json.loads(partition)
                    partition_app_config = partition_as_dict.get(app.name)
                    partition_nodes = []

                    for unit in units:
                        if node := relation.data[unit].get("node"):
                            # Load the node
                            node = json.loads(node)
                            if node_config := node.get("node_config"):

                                # Get the NodeName and append to the partition nodes
                                node_name = node_config["NodeName"]
                                partition_nodes.append(node_name)

                                # Add this node config to the nodes dict.
                                nodes[node_name] = {
                                    k: v for k, v in node_config.items() if k not in ["NodeName"]
                                }

                                # Account for new node.
                                if node.get("new_node"):
                                    new_nodes.append(node_name)

                    # Ensure we have a unique list and add it to the partition.
                    partition_app_config["Nodes"] = list(set(partition_nodes))

                    # Check for default partition.
                    if self._charm.model.config.get("default-partition") == app.name:
                        partition_app_config["Default"] = "YES"

                    partitions[app.name] = partition_app_config

        # If we have down nodes because they are new nodes, then set them here.
        new_node_down_nodes = (
            [{"DownNodes": list(set(new_nodes)), "State": "DOWN", "Reason": "New node."}]
            if len(new_nodes) > 0
            else []
        )
        return new_node_down_nodes, nodes, partitions
