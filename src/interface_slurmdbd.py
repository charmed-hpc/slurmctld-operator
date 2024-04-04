#!/usr/bin/env python3
"""Slurmdbd."""
import json
import logging
from typing import Any, Dict, Union

from ops import EventBase, EventSource, Object, ObjectEvents, RelationMapping

logger = logging.getLogger()


class SlurmdbdAvailableEvent(EventBase):
    """Emits slurmdbd_available."""


class SlurmdbdUnavailableEvent(EventBase):
    """Emits slurmdbd_unavailable."""


class SlurmdbdAvailableEvents(ObjectEvents):
    """SlurmdbdAvailableEvents."""

    slurmdbd_available = EventSource(SlurmdbdAvailableEvent)
    slurmdbd_unavailable = EventSource(SlurmdbdUnavailableEvent)


class Slurmdbd(Object):
    """Facilitate slurmdbd lifecycle events."""

    on = SlurmdbdAvailableEvents()

    def __init__(self, charm, relation_name):
        """Set the initial attribute values for this interface."""
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
            self._charm.on[self._relation_name].relation_broken,
            self._on_relation_broken,
        )

    def _on_relation_created(self, event) -> None:
        """Perform relation-created event operations."""
        # Check that slurm has been installed so that we know the munge key is
        # available. Defer if slurm has not been installed yet.
        if not self._charm.slurm_installed:
            event.defer()
            return

        # Get the munge_key and set it to the application relation data,
        # to be retrieved on the other side by slurmdbd.
        munge_key = self._charm.get_munge_key()
        event.relation.data[self.model.app]["munge_key"] = munge_key

        # Get the jwt_rsa key from the slurm_ops_manager and set it to the app
        # data on the relation to be retrieved on the other side by slurmdbd.
        jwt_rsa = self._charm.get_jwt_rsa()
        event.relation.data[self.model.app]["jwt_rsa"] = jwt_rsa

        event.relation.data[self.model.app]["cluster-name"] = self._charm.config.get(
            "cluster-name"
        )

    def _on_relation_changed(self, event) -> None:
        event_app_data = event.relation.data.get(event.app)
        if event_app_data:
            slurmdbd_info = event_app_data.get("slurmdbd_info")
            if slurmdbd_info:
                self._charm.slurmdbd_available = True
                self.on.slurmdbd_available.emit()
            else:
                event.defer()
        else:
            event.defer()

    def _on_relation_broken(self, event) -> None:
        if self.framework.model.unit.is_leader():
            event.relation.data[self.model.app]["munge_key"] = ""
            event.relation.data[self.model.app]["jwt_rsa"] = ""
        self._charm.slurmdbd_available = False
        self.on.slurmdbd_unavailable.emit()

    @property
    def _relation(self) -> Union[RelationMapping, None]:
        return self.framework.model.get_relation(self._relation_name)

    @property
    def is_joined(self) -> bool:
        """Return True if the relation to slurmdbd exists."""
        if self._charm.framework.model.relations.get(self._relation_name):
            return True
        else:
            return False

    def get_slurmdbd_info(self) -> Dict[Any, Any]:
        """Return the slurmdbd_info."""
        slurmdbd_info = {}
        if relation := self._relation:
            if app_data := relation.data.get(relation.app):
                if slurmdbd_info := app_data.get("slurmdbd_info"):
                    try:
                        slurmdbd_info = json.loads(slurmdbd_info)
                    except json.JSONDecodeError as e:
                        logger.error("Cannot decode slurmdbd_info from json.")
                        raise e
                else:
                    logger.debug("slurmdbd_info does not yet exist in the application data.")
            else:
                logger.debug("Application data does not yet exist on the relation.")
        else:
            logger.debug("Relation with slurmdbd does not exist.")
        return slurmdbd_info
