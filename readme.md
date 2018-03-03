# Rig Stats

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Nvidia GPU, pool and miner statistics exporter for prometheus.io.

It is useful in combination with Grafana. Included a sample dashboard [here](grafana-dashboard-sample.json).

The goal is to create dashboards like this:

![Screenshot](grafana-dashboard-sample.png)

## Table of Contents

* [Requirements](#requirements)
* [Installation](#installation)
* [Usage](#usage)
* [How it works](#how-it-works)
* [Changelog](#changelog)
* [Licence](#licence)

## Requirements

* Python 3
* [NVIDIA Management Library (NVML)](https://developer.nvidia.com/cuda-downloads)

Supported pools (optional):

* Flypool

Supported miners (optional):

* DSTM

## Installation

    $ git clone https://github.com/pwm/rig-stats.git
    $ cd rig-stats
    $ pip3 install -r requirements.txt

## Usage

Simple usage (runs on default port 9001):

    $ ./rig_stats.py

With pool:

	$ ./rig_stats.py -o flypool -O api-zcash.flypool.org -u <your_zcash_address>

With pool, custom port and miner:

	$ ./rig_stats.py -p 9003 -o flypool -O api-zcash.flypool.org -u <your_zcash_address> -m dstm -H 127.0.0.1 -P 2222

It is recommended to run it in a screen ot tmux session, eg.:

	$ screen -S rig-stats
	$ ./rig_stats.py

Full help:

    $ ./rig_stats.py -h
	usage: rig_stats.py [-h] [-p <port>] [-o <name>] [-O <host>] [-u <miner>]
	                    [-m <name>] [-H <host>] [-P <port>]
	
	Nvidia GPU, miner and pool statistics exporter for prometheus.io
	
	optional arguments:
	  -h, --help            show this help message and exit
	  -p <port>, --port <port>
	                        The port the exporter listens on for Prometheus queries.
	                        Default: 9001
	
	Pool related arguments:
	  -o <name>, --pool <name>
	                        The pool name, in case pool stats are to be collected.
	                        Currently supported:
	                          - flypool
	  -O <host>, --pool-api-host <host>
	                        Pool API host
	  -u <miner>, --pool-api-miner <miner>
	                        Pool API miner
	
	Miner related arguments:
	  -m <name>, --miner <name>
	                        The miner software, in case miner stats are to be collected.
	                        Currently supported:
	                          - dstm
	  -H <host>, --miner-api-host <host>
	                        Miner API host
	  -P <port>, --miner-api-port <port>
	                        Miner API port

## How it works

The program uses the python 3 bindings for the NVIDIA Management Library (NVML) to query GPU telemetry data, eg. clock speed or power usage. 

If the optional pool arguments are set then it will include pool statistics, eg. pool hashrate or earnings.

If the optional miner arguments are set then it will include miner telemetry data, eg. hashrate or efficiency.

It runs as an http server using Prometheus' own client library, which makes it east for Prometheus to poll it.

## Changelog

[Click here](changelog.md)

## Licence

[MIT](LICENSE)
