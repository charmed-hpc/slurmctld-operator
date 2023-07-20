<div align="center">

# slurmctld operator

A [Juju](https://juju.is) operator for slurmctld - the central management daemon of [SLURM](https://slurm.schedmd.com/overview.html).

[![Charmhub Badge](https://charmhub.io/slurmctld/badge.svg)](https://charmhub.io/slurmctld)
[![CI](https://github.com/omnivector-solutions/slurmctld-operator/actions/workflows/ci.yaml/badge.svg)](https://github.com/omnivector-solutions/slurmctld/actions/workflows/ci.yaml/badge.svg)
[![Release](https://github.com/omnivector-solutions/slurmctld-operator/actions/workflows/release.yaml/badge.svg)](https://github.com/omnivector-solutions/slurmctld-operator/actions/workflows/release.yaml/badge.svg)
[![Matrix](https://img.shields.io/matrix/ubuntu-hpc%3Amatrix.org?logo=matrix&label=ubuntu-hpc)](https://matrix.to/#/#ubuntu-hpc:matrix.org)

</div>

## Features

The slurmctld operator provides and manages the slurmctld daemon. This operator provides the central management services required for slurmd, slurmdbd, and slurmrestd to function in Charmed SLURM deployments.

## Usage

```shell
$ juju deploy slurmctld --channel edge
$ juju deploy slurmd --channel edge
$ juju deploy slurmdbd --channel edge
$ juju deploy mysql --channel 8.0/stable
$ juju deploy mysql-router slurmdbd-mysql-router --channel 8.0/stable
$ juju integrate slurmctld:slurmd slurmd:slurmd
$ juju integrate slurmdbd-mysql-router:backend-database mysql:database
$ juju integrate slurmdbd:database slurm-mysql-router:database
$ juju integrate slurmctld:slurmdbd slurmdbd:slurmdbd
```

## Project & Community

The slurmctld operator is a project of the [Ubuntu HPC](https://discourse.ubuntu.com/t/high-performance-computing-team/35988) 
community. It is an open source project that is welcome to community involvement, contributions, suggestions, fixes, and 
constructive feedback. Interested in being involved with the development of the slurmctld operator? Check out these links below:

* [Join our online chat](https://matrix.to/#/#ubuntu-hpc:matrix.org)
* [Contributing guidelines](./CONTRIBUTING.md)
* [Code of conduct](https://ubuntu.com/community/ethos/code-of-conduct)
* [File a bug report](https://github.com/omnivector-solutions/slurmctld-operator/issues)
* [Juju SDK docs](https://juju.is/docs/sdk)

## License

The slurmctld operator is free software, distributed under the Apache Software License, version 2.0. See the [LICENSE](./LICENSE) file for more information.
