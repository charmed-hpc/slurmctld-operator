#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Test default charm events such as upgrade charm, install, etc."""

import unittest
from unittest.mock import patch

import ops.testing
from charm import SlurmctldCharm
from ops.model import BlockedStatus
from ops.testing import Harness

ops.testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(SlurmctldCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("slurm_ops_manager.SlurmManager.hostname", return_val="localhost")
    def test_hostname(self, hostname) -> None:
        """Test that the hostname property works."""
        self.assertEqual(self.harness.charm.hostname, hostname)

    @patch("slurm_ops_manager.SlurmManager.port", return_val=12345)
    def test_port(self, port) -> None:
        """Test that the port property works."""
        self.assertEqual(self.harness.charm.port, port)

    def test_cluster_name(self) -> None:
        """Test that the cluster_name property works."""
        self.assertEqual(self.harness.charm.cluster_name, "osd-cluster")

    @patch("interface_slurmctld_peer.SlurmctldPeer.get_slurmctld_info", return_value={})
    def test_slurmctld_info(self, info) -> None:
        """Test that the slurmctld_info property works."""
        self.assertEqual(self.harness.charm._slurmctld_info, info.return_value)

    @patch("interface_slurmdbd.Slurmdbd.get_slurmdbd_info", return_value={})
    def test_slurmdbd_info(self, info) -> None:
        """Test that the slurmdbd_info property works."""
        self.assertEqual(self.harness.charm.slurmdbd_info, info.return_value)

    @patch("interface_slurmd.Slurmd.get_slurmd_info", return_value={})
    def test_slurmd_info(self, info) -> None:
        """Test that the slurmd_info property works."""
        self.assertEqual(self.harness.charm._slurmd_info, info.return_value)

    def test_cluster_info(self) -> None:
        """Test the cluster_info property works."""
        self.assertEqual(type(self.harness.charm._cluster_info), dict)

    def test_addons_info(self) -> None:
        """Test that the addons_info property works."""
        self.assertEqual(type(self.harness.charm._addons_info), dict)

    def test_set_slurmd_available(self) -> None:
        """Test that the set_slurmd_available method works."""
        self.harness.charm.set_slurmd_available(True)
        self.assertEqual(self.harness.charm._stored.slurmd_available, True)
        self.harness.charm.set_slurmd_available(False)
        self.assertEqual(self.harness.charm._stored.slurmd_available, False)

    def test_set_slurmdbd_available(self) -> None:
        """Test that the set_slurmdbd_available method works."""
        self.harness.charm._set_slurmdbd_available(True)
        self.assertEqual(self.harness.charm._stored.slurmdbd_available, True)
        self.harness.charm._set_slurmdbd_available(False)
        self.assertEqual(self.harness.charm._stored.slurmdbd_available, False)

    def test_set_slurmrestd_available(self) -> None:
        """Test that the set_slurmrestd_available method works."""
        self.harness.charm.set_slurmrestd_available(True)
        self.assertEqual(self.harness.charm._stored.slurmrestd_available, True)
        self.harness.charm.set_slurmrestd_available(False)
        self.assertEqual(self.harness.charm._stored.slurmrestd_available, False)

    @patch("ops.model.Unit.is_leader", return_value=True)
    def test_is_leader(self, _) -> None:
        """Test that the is_leader method works.

        Notes:
            This method should be removed as this behavior is already
            defined in the ops framework.
        """
        self.assertEqual(self.harness.charm._is_leader(), True)

    @patch("ops.model.Unit.is_leader", return_value=False)
    def test_is_not_leader(self, _) -> None:
        """Test that the is_leader method works when unit is not leader."""
        self.assertEqual(self.harness.charm._is_leader(), False)

    def test_is_slurm_installed(self) -> None:
        """Test that the is_slurm_installed method works."""
        setattr(self.harness.charm._stored, "slurm_installed", True)  # Patch StoredState
        self.assertEqual(self.harness.charm.is_slurm_installed(), True)

    def test_is_slurm_not_installed(self) -> None:
        """Test that the is_slurm_installed method works when slurm is not installed."""
        setattr(self.harness.charm._stored, "slurm_installed", False)  # Patch StoredState
        self.assertEqual(self.harness.charm.is_slurm_installed(), False)

    @unittest.expectedFailure
    @patch("slurm_ops_manager.SlurmManager.install")
    @patch("slurm_ops_manager.SlurmManager.generate_jwt_rsa")
    @patch("charm.SlurmctldCharm.get_jwt_rsa")
    @patch("slurm_ops_manager.SlurmManager.configure_jwt_rsa")
    @patch("slurm_ops_manager.SlurmManager.get_munge_key")
    @patch("charm.SlurmctldCharm.model.resources.fetch")
    def test_install_success(self, *_) -> None:
        """Test that the on_install method works.

        Notes:
            This method is expected to fail due to the 'version' file missing.
        """
        self.harness.charm.on.install.emit()
        self.assertNotEqual(
            self.harness.charm.unit.status, BlockedStatus("Error installing slurmctld")
        )

    @unittest.expectedFailure
    @patch("slurm_ops_manager.SlurmManager.install", return_value=False)
    def test_install_fail(self, _) -> None:
        """Test that the on_install method works when slurmctld fails to install.

        Notes:
            This method is expected to fail due to the 'version' file missing.
        """
        self.harness.charm.on.install.emit()
        self.assertEqual(
            self.harness.charm.unit.status, BlockedStatus("Error installing slurmctld")
        )

    @patch("pathlib.Path.read_text", return_value="v1.0.0")
    def test_on_upgrade(self, *_) -> None:
        """Test that the on_upgrade method works,."""
        self.harness.charm.on.upgrade_charm.emit()
        self.assertEqual(self.harness.get_workload_version(), "v1.0.0")

    def test_check_status_slurm_not_installed(self) -> None:
        """Test that the check_status method works when slurm is not installed."""
        self.harness.charm._stored.slurm_installed = False
        res = self.harness.charm._check_status()
        self.assertEqual(
            self.harness.charm.unit.status, BlockedStatus("Error installing slurmctld")
        )
        self.assertEqual(
            res, False, msg="_check_status returned value True instead of expected value False."
        )

    @patch("slurm_ops_manager.SlurmManager.check_munged", return_value=False)
    def test_check_status_bad_munge(self, _) -> None:
        """Test that the check_status method works when munge encounters an error."""
        setattr(self.harness.charm._stored, "slurm_installed", True)  # Patch StoredState
        res = self.harness.charm._check_status()
        self.assertEqual(
            self.harness.charm.unit.status, BlockedStatus("Error configuring munge key")
        )
        self.assertEqual(
            res, False, msg="_check_status returned value True instead of expected value False."
        )

    def test_get_munge_key(self) -> None:
        """Test that the get_munge_key method works."""
        setattr(self.harness.charm._stored, "munge_key", "=ABC=")  # Patch StoredState
        self.assertEqual(self.harness.charm.get_munge_key(), "=ABC=")

    def test_get_jwt_rsa(self) -> None:
        """Test that the get_jwt_rsa method works."""
        setattr(self.harness.charm._stored, "jwt_rsa", "=ABC=")  # Patch StoredState
        self.assertEqual(self.harness.charm.get_jwt_rsa(), "=ABC=")

    def test_assemble_slurm_config(self) -> None:
        """Test that the assemble_slurm_config method works."""
        self.assertEqual(type(self.harness.charm._assemble_slurm_config()), dict)

    @patch("charm.SlurmctldCharm._check_status", return_value=False)
    def test_on_slurmrestd_available_status_false(self, _) -> None:
        """Test that the on_slurmrestd_available method works when _check_status is False."""
        self.harness.charm._slurmrestd.on.slurmrestd_available.emit()

    @patch("charm.SlurmctldCharm._check_status", return_value=True)
    @patch("charm.SlurmctldCharm._assemble_slurm_config", return_value={})
    def test_on_slurmrestd_available_no_config(self, config, status) -> None:
        """Test that the on_slurmrestd_available method works if no slurm config is available."""
        self.harness.charm._slurmrestd.on.slurmrestd_available.emit()
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Cannot generate slurm_config - deferring event."),
        )

    @patch("charm.SlurmctldCharm._check_status", return_value=True)
    @patch("charm.SlurmctldCharm._assemble_slurm_config")
    @patch("interface_slurmrestd.Slurmrestd.set_slurm_config_on_app_relation_data")
    @patch("interface_slurmrestd.Slurmrestd.restart_slurmrestd")
    def test_on_slurmrestd_available_if_available(self, *_) -> None:
        """Test that the on_slurmrestd_available method works if slurm_config is available.

        Notes:
            This method is testing the _on_slurmrestd_available event handler
            completes successfully.
        """
        self.harness.charm._stored.slurmrestd_available = True
        self.harness.charm._slurmrestd.on.slurmrestd_available.emit()

    def test_on_slurmdbd_available(self) -> None:
        """Test that the on_slurmdbd_method works."""
        self.harness.charm._slurmdbd.on.slurmdbd_available.emit()
        self.assertEqual(self.harness.charm._stored.slurmdbd_available, True)

    def test_on_slurmdbd_unavailable(self) -> None:
        """Test that the on_slurmdbd_unavailable method works."""
        self.harness.charm._slurmdbd.on.slurmdbd_unavailable.emit()
        self.assertEqual(self.harness.charm._stored.slurmdbd_available, False)
