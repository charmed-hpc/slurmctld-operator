#!/usr/bin/env python3
"""SlurmrestdProvides."""
import json
import logging
import uuid

from ops.framework import EventBase, EventSource, Object, ObjectEvents

logger = logging.getLogger()


class SlurmrestdAvailableEvent(EventBase):
    """Emitted when slurmrestd is available."""


class SlurmrestdUnavailableEvent(EventBase):
    """Emitted when the slurmrestd relation is broken."""


class SlurmrestdEvents(ObjectEvents):
    """SlurmrestdEvents."""

    slurmrestd_available = EventSource(SlurmrestdAvailableEvent)
    slurmrestd_unavailable = EventSource(SlurmrestdUnavailableEvent)


class Slurmrestd(Object):
    """Slurmrestd interface."""

    on = SlurmrestdEvents()

    def __init__(self, charm, relation_name):
        """Set the initial data."""
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        self.framework.observe(
            self._charm.on[relation_name].relation_created, self._on_relation_created
        )
        self.framework.observe(
            self._charm.on[relation_name].relation_broken, self._on_relation_broken
        )

    @property
    def is_joined(self) -> bool:
        """Return True if relation is joined."""
        if self._charm.framework.model.relations.get(self._relation_name):
            return True
        else:
            return False

    def _on_relation_created(self, event) -> None:
        # Check that slurm has been installed so that we know the munge key is
        # available. Defer if slurm has not been installed yet.
        if not self._charm.slurm_installed:
            event.defer()
            return

        # make sure slurmdbd started before sending signal to slurmrestd
        if not self._charm.slurmdbd_available:
            event.defer()
            return

        # Get the munge_key from the slurm_ops_manager and set it to the app
        # data on the relation to be retrieved on the other side by slurmdbd.
        app_relation_data = event.relation.data[self.model.app]
        app_relation_data["munge_key"] = self._charm.get_munge_key()
        app_relation_data["jwt_rsa"] = self._charm.get_jwt_rsa()
        self._charm.slurmrestd_available = True
        self.on.slurmrestd_available.emit()

    def _on_relation_broken(self, event):
        self._charm.slurmrestd_available = False
        self.on.slurmrestd_unavailable.emit()

    def set_slurm_config_on_app_relation_data(self, slurm_config) -> None:
        """Set the slurm_conifg to the app data on the relation.

        Setting data on the relation forces the units of related applications
        to observe the relation-changed event so they can acquire and
        render the updated slurm_config.
        """
        relations = self._charm.framework.model.relations.get(self._relation_name)
        for relation in relations:
            app_relation_data = relation.data[self.model.app]
            app_relation_data["slurm_config"] = json.dumps(slurm_config)

    def restart_slurmrestd(self) -> None:
        """Send a restart signal to related slurmd applications."""
        relations = self._charm.framework.model.relations.get(self._relation_name)
        for relation in relations:
            app_relation_data = relation.data[self.model.app]
            app_relation_data["restart_slurmrestd_uuid"] = str(uuid.uuid4())
