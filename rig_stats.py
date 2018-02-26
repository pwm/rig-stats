#!/usr/bin/env python3

import argparse
import atexit
import json
from prometheus_client.core import GaugeMetricFamily, REGISTRY
from prometheus_client.exposition import start_http_server
from py3nvml import py3nvml as nvml
import socket
from sys import exit
import textwrap
import time
from typing import Dict, Generator


class NvidiaCollector(object):
    @staticmethod
    def collect() -> Generator:
        gpu_utilization = GaugeMetricFamily('nvidia_gpu_utilization', 'GPU Utilization', labels=['gpu_id', 'type'])
        clock_speed = GaugeMetricFamily('nvidia_clock_speed', 'Clock Speed', labels=['gpu_id', 'type'])
        power_usage = GaugeMetricFamily('nvidia_power_usage', 'Power Usage', labels=['gpu_id', 'type'])
        memory_usage = GaugeMetricFamily('nvidia_memory_usage', 'Memory Usage', labels=['gpu_id', 'type'])
        bar1_memory_usage = GaugeMetricFamily('nvidia_bar1_memory_usage', 'BAR1 Memory Usage', labels=['gpu_id', 'type'])
        temperature = GaugeMetricFamily('nvidia_temperature', 'Temperature', labels=['gpu_id', 'type'])
        fan_speed = GaugeMetricFamily('nvidia_fan_speed', 'Fan Speed', labels=['gpu_id'])

        gpu_handles = [(i, nvml.nvmlDeviceGetHandleByIndex(i)) for i in range(nvml.nvmlDeviceGetCount())]
        for (i, handle) in gpu_handles:
            gpu_id = nvml.nvmlDeviceGetUUID(handle)
            # GPU Utilization
            nvml_gpu_utilization = nvml.nvmlDeviceGetUtilizationRates(handle)
            gpu_utilization.add_metric([gpu_id, 'gpu'], nvml_gpu_utilization.gpu)
            gpu_utilization.add_metric([gpu_id, 'memory'], nvml_gpu_utilization.memory)
            # Clock Speed
            clock_speed.add_metric([gpu_id, 'core'], nvml.nvmlDeviceGetClockInfo(handle, nvml.NVML_CLOCK_COUNT))
            clock_speed.add_metric([gpu_id, 'memory'], nvml.nvmlDeviceGetClockInfo(handle, nvml.NVML_CLOCK_MEM))
            clock_speed.add_metric([gpu_id, 'max_core'], nvml.nvmlDeviceGetMaxClockInfo(handle, nvml.NVML_CLOCK_COUNT))
            clock_speed.add_metric([gpu_id, 'max_memory'], nvml.nvmlDeviceGetMaxClockInfo(handle, nvml.NVML_CLOCK_MEM))
            # Power Usage
            power_usage.add_metric([gpu_id, 'usage'], nvml.nvmlDeviceGetPowerUsage(handle))
            power_usage.add_metric([gpu_id, 'min_limit'], nvml.nvmlDeviceGetPowerManagementLimitConstraints(handle)[0])
            power_usage.add_metric([gpu_id, 'max_limit'], nvml.nvmlDeviceGetPowerManagementLimitConstraints(handle)[1])
            power_usage.add_metric([gpu_id, 'limit'], nvml.nvmlDeviceGetPowerManagementLimit(handle))
            power_usage.add_metric([gpu_id, 'default_limit'], nvml.nvmlDeviceGetPowerManagementDefaultLimit(handle))
            power_usage.add_metric([gpu_id, 'enforced_limit'], nvml.nvmlDeviceGetEnforcedPowerLimit(handle))
            # Memory Usage
            nvml_memory_usage = nvml.nvmlDeviceGetMemoryInfo(handle)
            memory_usage.add_metric([gpu_id, 'used'], nvml_memory_usage.used)
            memory_usage.add_metric([gpu_id, 'free'], nvml_memory_usage.free)
            memory_usage.add_metric([gpu_id, 'total'], nvml_memory_usage.total)
            # BAR1 Memory Usage
            nvml_bar1_memory_usage = nvml.nvmlDeviceGetBAR1MemoryInfo(handle)
            bar1_memory_usage.add_metric([gpu_id, 'used'], nvml_bar1_memory_usage.bar1Used)
            bar1_memory_usage.add_metric([gpu_id, 'free'], nvml_bar1_memory_usage.bar1Free)
            bar1_memory_usage.add_metric([gpu_id, 'total'], nvml_bar1_memory_usage.bar1Total)
            # Temperature
            temperature.add_metric([gpu_id, 'current'], nvml.nvmlDeviceGetTemperature(handle, nvml.NVML_TEMPERATURE_GPU))
            temperature.add_metric([gpu_id, 'slowdown_threshold'], nvml.nvmlDeviceGetTemperatureThreshold(handle, nvml.NVML_TEMPERATURE_THRESHOLD_SLOWDOWN))
            temperature.add_metric([gpu_id, 'shutdown_threshold'], nvml.nvmlDeviceGetTemperatureThreshold(handle, nvml.NVML_TEMPERATURE_THRESHOLD_SHUTDOWN))
            # Fan Speed
            fan_speed.add_metric([gpu_id], nvml.nvmlDeviceGetFanSpeed(handle))

        yield gpu_utilization
        yield clock_speed
        yield power_usage
        yield memory_usage
        yield bar1_memory_usage
        yield temperature
        yield fan_speed


class DTSMCollector(object):
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

    def collect(self) -> Generator:
        hashrate = GaugeMetricFamily('miner_hashrate', 'Hashrate', labels=['gpu_id', 'type'])
        efficiency = GaugeMetricFamily('miner_efficiency', 'Efficiency', labels=['gpu_id', 'type'])
        pool_shares = GaugeMetricFamily('miner_pool_shares', 'Pool Shares', labels=['gpu_id', 'type'])
        latency = GaugeMetricFamily('miner_latency', 'Latency', labels=['gpu_id'])
        uptime = GaugeMetricFamily('miner_uptime', 'Uptime', labels=['type'])

        miner_data = DTSMCollector.query_miner(self.host, self.port)

        uptime.add_metric(['miner'], miner_data['uptime'])
        uptime.add_metric(['connection'], miner_data['contime'])
        for gpu in miner_data['result']:
            gpu_id = gpu['gpu_uuid']
            # Hashrate
            hashrate.add_metric([gpu_id, 'current'], gpu['sol_ps'])
            hashrate.add_metric([gpu_id, 'average'], gpu['avg_sol_ps'])
            # Efficiency
            efficiency.add_metric([gpu_id, 'current'], gpu['sol_pw'])
            efficiency.add_metric([gpu_id, 'average'], gpu['avg_sol_pw'])
            # Pool Shares
            pool_shares.add_metric([gpu_id, 'accepted'], gpu['accepted_shares'])
            pool_shares.add_metric([gpu_id, 'rejected'], gpu['rejected_shares'])
            # Latency
            latency.add_metric([gpu_id], gpu['latency'])

        yield uptime
        yield hashrate
        yield efficiency
        yield pool_shares
        yield latency

    @staticmethod
    def query_miner(host: str, port: int) -> Dict:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            s.sendall(b'{"id": 1, "method": "getstat"}')
            rsp = s.recv(8192)
        return json.loads(rsp.decode('utf8').rstrip())


def parse_args() -> Dict:
    parser = argparse.ArgumentParser(
        description='Nvidia GPU and miner statistics exporter for prometheus.io',
        allow_abbrev=False,
        formatter_class=argparse.RawTextHelpFormatter)
    miner_parser = parser.add_argument_group('Miner related arguments')

    parser.add_argument(
        '-p', '--port',
        metavar='<port>',
        type=int,
        required=False,
        default=9001,
        help=textwrap.dedent('''\
            The port the exporter listens on for Prometheus queries.
            Default: 9001'''))
    miner_parser.add_argument(
        '-m', '--miner',
        metavar='<name>',
        required=False,
        choices=['dtsm'],
        help=textwrap.dedent('''\
            The miner software, in case miner stats are to be collected.
            Currently supported:
              - dtsm'''))
    miner_parser.add_argument(
        '-H', '--miner-api-host',
        metavar='<host>',
        required=False,
        help='Miner API host')
    miner_parser.add_argument(
        '-P', '--miner-api-port',
        metavar='<port>',
        type=int,
        required=False,
        help='Miner API port')

    args = parser.parse_args()
    if len(tuple(filter(None.__ne__, (args.miner, args.miner_api_host, args.miner_api_port)))) not in (0, 3):
        parser.error('--miner requires --miner_api_host and --miner_api_port.')

    return vars(args)


def miner_collectors() -> Dict:
    return {
        'dtsm': DTSMCollector
    }


def main():
    args = parse_args()

    nvml.nvmlInit()
    atexit.register(nvml.nvmlShutdown)
    REGISTRY.register(NvidiaCollector())
    if args['miner'] is not None:
        REGISTRY.register(miner_collectors()[args['miner'].lower()](args['miner_api_host'], args['miner_api_port']))

    print('Starting exporter...')
    try:
        start_http_server(args['port'])
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('Exiting...')
        exit(0)


if __name__ == '__main__':
    main()
