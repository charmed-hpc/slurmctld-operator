#!/usr/bin/env python3
"""Nodes Interface.

Node config or `node_config` is a json string that contains the node configuration.

The `node_config` is set by each slurmd unit on its relation data on the `nodes`
interface.

The `node_config` can contain any slurm Node level configuration data and can be found here:
https://slurm.schedmd.com/slurm.conf.html#SECTION_NODE-CONFIGURATION.

Example `node_config`:

{
    'node_name': 'compute-gpu-0',
    'node_addr': '10.204.129.33',
    'real_memory': '64012',
    'cpus': '2',
    'state': 'UNKNOWN',
    'sockets': '2'
{

"""
import copy
import json
import logging

from ops.framework import EventBase, EventSource, Object, ObjectEvents, StoredState

logger = logging.getLogger()


class NodeAvailableEvent(EventBase):
    """Emitted when a slurmd node is available."""


class NodesBrokenEvent(EventBase):
    """Emitted when the nodes relation is broken."""


class NodeDepartedEvent(EventBase):
    """Emitted when a slurmd node departs."""


class NodeInventoryEvents(ObjectEvents):
    """SlurmClusterProviderRelationEvents."""

    node_available = EventSource(NodeAvailableEvent)
    nodes_broken = EventSource(NodesBrokenEvent)
    node_departed = EventSource(NodeDepartedEvent)


class Nodes(Object):
    """Nodes inventory interface."""

    on = NodeInventoryEvents()

    def __init__(self, charm, relation_name):
        """Set self._relation_name and self.charm."""
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

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

    def _on_relation_changed(self, event):
        """Get relation data for nodes that have joined."""
        unit_relation_data = event.relation.data[event.unit]
        node_config = unit_relation_data["node_config"]
        partition_name = unit_relation_data["partition_name"]

        if node_config:
            self._charm.add_node_config_to_nodes(node_config, partition_name)
            self.on.node_available.emit()

    def _on_relation_departed(self, event):
        """Emit the node_departed event and remove node from the nodes."""
        unit_relation_data = event.relation.data[event.unit]
        node_config = unit_relation_data["node_config"]
        partition_name = unit_relation_data["partition_name"]

        if node_config:
            self._charm._remove_node_config_from_nodes(node_config, partition_name)
            self.on.node_departed.emit()

    def _on_relation_broken(self, event):
        """Clear the nodes for this application."""
        unit_relation_data = event.relation.data[event.unit]
        partition_name = unit_relation_data["partition_name"]
        self._charm._clear_node_config(partition_name)
        self.on.nodes_broken.emit()
