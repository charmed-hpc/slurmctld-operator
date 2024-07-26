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

"""Configure slurmctld operator integration tests."""

import logging
import os
from pathlib import Path
from typing import Union

import pytest
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)
SLURMD_DIR = Path(os.getenv("SLURMD_DIR", "../slurmd-operator"))
SLURMDBD_DIR = Path(os.getenv("SLURMDBD_DIR", "../slurmdbd-operator"))
SLURMRESTD_DIR = Path(os.getenv("SLURMRESTD_DIR", "../slurmrestd-operator"))


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--charm-base",
        action="store",
        default="ubuntu@22.04",
        help="Charm base version to use for integration tests",
    )
    parser.addoption(
        "--use-local",
        action="store_true",
        default=False,
        help="Use SLURM operators located on localhost rather than pull from Charmhub",
    )


@pytest.fixture(scope="module")
def charm_base(request) -> str:
    """Get slurmctld charm base to use."""
    return request.config.option.charm_base


@pytest.fixture(scope="module")
async def slurmctld_charm(ops_test: OpsTest) -> Path:
    """Pack slurmctld charm to use for integration tests."""
    return await ops_test.build_charm(".")


@pytest.fixture(scope="module")
async def slurmd_charm(request, ops_test: OpsTest) -> Union[str, Path]:
    """Pack slurmd charm to use for integration tests when --use-local is specified.

    Returns:
        `str` "slurmd" if --use-local not specified or if SLURMD_DIR does not exist.
    """
    if request.config.option.use_local:
        logger.info("Using local slurmd operator rather than pulling from Charmhub")
        if SLURMD_DIR.exists():
            return await ops_test.build_charm(SLURMD_DIR)
        else:
            logger.warning(
                f"{SLURMD_DIR} not found. "
                f"Defaulting to latest/edge slurmd operator from Charmhub"
            )

    return "slurmd"


@pytest.fixture(scope="module")
async def slurmdbd_charm(request, ops_test: OpsTest) -> Union[str, Path]:
    """Pack slurmdbd charm to use for integration tests when --use-local is specified.

    Returns:
        `str` "slurmdbd" if --use-local not specified or if SLURMDBD_DIR does not exist.
    """
    if request.config.option.use_local:
        logger.info("Using local slurmdbd operator rather than pulling from Charmhub")
        if SLURMDBD_DIR.exists():
            return await ops_test.build_charm(SLURMDBD_DIR)
        else:
            logger.warning(
                f"{SLURMDBD_DIR} not found. "
                f"Defaulting to latest/edge slurmdbd operator from Charmhub"
            )

    return "slurmdbd"


@pytest.fixture(scope="module")
async def slurmrestd_charm(request, ops_test: OpsTest) -> Union[str, Path]:
    """Pack slurmrestd charm to use for integration tests when --use-local is specified.

    Returns:
        `str` "slurmrestd" if --use-local not specified or if SLURMRESTD_DIR does not exist.
    """
    if request.config.option.use_local:
        logger.info("Using local slurmrestd operator rather than pulling from Charmhub")
        if SLURMRESTD_DIR.exists():
            return await ops_test.build_charm(SLURMRESTD_DIR)
        else:
            logger.warning(
                f"{SLURMRESTD_DIR} not found. "
                f"Defaulting to latest/edge slurmrestd operator from Charmhub"
            )

    return "slurmrestd"
