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
import urllib3


class NvidiaCollector(object):

    @staticmethod
    def call(fn, handle, arg=None):
        try:
            return getattr(nvml, fn)(handle) if arg is None else getattr(nvml, fn)(handle, arg)
        except nvml.NVMLError:
            return 0

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
            nvml_gpu_utilization = NvidiaCollector.call('nvmlDeviceGetUtilizationRates', handle)
            gpu_utilization.add_metric([gpu_id, 'gpu'], nvml_gpu_utilization.gpu)
            gpu_utilization.add_metric([gpu_id, 'memory'], nvml_gpu_utilization.memory)
            # Clock Speed
            clock_speed.add_metric([gpu_id, 'core'], NvidiaCollector.call('nvmlDeviceGetClockInfo', handle, nvml.NVML_CLOCK_COUNT))
            clock_speed.add_metric([gpu_id, 'memory'], NvidiaCollector.call('nvmlDeviceGetClockInfo', handle, nvml.NVML_CLOCK_MEM))
            clock_speed.add_metric([gpu_id, 'max_core'], NvidiaCollector.call('nvmlDeviceGetMaxClockInfo', handle, nvml.NVML_CLOCK_COUNT))
            clock_speed.add_metric([gpu_id, 'max_memory'], NvidiaCollector.call('nvmlDeviceGetMaxClockInfo', handle, nvml.NVML_CLOCK_MEM))
            # Power Usage
            power_usage.add_metric([gpu_id, 'usage'], NvidiaCollector.call('nvmlDeviceGetPowerUsage', handle))
            power_usage.add_metric([gpu_id, 'min_limit'], NvidiaCollector.call('nvmlDeviceGetPowerManagementLimitConstraints', handle)[0])
            power_usage.add_metric([gpu_id, 'max_limit'], NvidiaCollector.call('nvmlDeviceGetPowerManagementLimitConstraints', handle)[1])
            power_usage.add_metric([gpu_id, 'limit'], NvidiaCollector.call('nvmlDeviceGetPowerManagementLimit', handle))
            power_usage.add_metric([gpu_id, 'default_limit'], NvidiaCollector.call('nvmlDeviceGetPowerManagementDefaultLimit', handle))
            power_usage.add_metric([gpu_id, 'enforced_limit'], NvidiaCollector.call('nvmlDeviceGetEnforcedPowerLimit', handle))
            # Memory Usage
            nvml_memory_usage = NvidiaCollector.call('nvmlDeviceGetMemoryInfo', handle)
            memory_usage.add_metric([gpu_id, 'used'], nvml_memory_usage.used)
            memory_usage.add_metric([gpu_id, 'free'], nvml_memory_usage.free)
            memory_usage.add_metric([gpu_id, 'total'], nvml_memory_usage.total)
            # BAR1 Memory Usage
            nvml_bar1_memory_usage = NvidiaCollector.call('nvmlDeviceGetBAR1MemoryInfo', handle)
            bar1_memory_usage.add_metric([gpu_id, 'used'], nvml_bar1_memory_usage.bar1Used)
            bar1_memory_usage.add_metric([gpu_id, 'free'], nvml_bar1_memory_usage.bar1Free)
            bar1_memory_usage.add_metric([gpu_id, 'total'], nvml_bar1_memory_usage.bar1Total)
            # Temperature
            temperature.add_metric([gpu_id, 'current'], NvidiaCollector.call('nvmlDeviceGetTemperature', handle, nvml.NVML_TEMPERATURE_GPU))
            temperature.add_metric([gpu_id, 'slowdown_threshold'], NvidiaCollector.call('nvmlDeviceGetTemperatureThreshold', handle, nvml.NVML_TEMPERATURE_THRESHOLD_SLOWDOWN))
            temperature.add_metric([gpu_id, 'shutdown_threshold'], NvidiaCollector.call('nvmlDeviceGetTemperatureThreshold', handle, nvml.NVML_TEMPERATURE_THRESHOLD_SHUTDOWN))
            # Fan Speed
            fan_speed.add_metric([gpu_id], nvml.nvmlDeviceGetFanSpeed(handle))

        yield gpu_utilization
        yield clock_speed
        yield power_usage
        yield memory_usage
        yield bar1_memory_usage
        yield temperature
        yield fan_speed


class FlyPoolCollector(object):
    def __init__(self, host: str, miner: str):
        self.host = host
        self.miner = miner
        self.data = {}

    def collect(self) -> Generator:
        hashrate = GaugeMetricFamily('pool_hashrate', 'Hashrate', labels=['type'])
        shares = GaugeMetricFamily('pool_shares', 'Hashrate', labels=['type'])
        earnings = GaugeMetricFamily('pool_earnings', 'Hashrate', labels=['type'])

        hashrate.add_metric(['current'], self.data['data']['currentHashrate'])
        hashrate.add_metric(['average'], self.data['data']['averageHashrate'])
        shares.add_metric(['valid'], self.data['data']['validShares'])
        shares.add_metric(['invalid'], self.data['data']['invalidShares'])
        shares.add_metric(['stale'], self.data['data']['staleShares'])
        earnings.add_metric(['unconfirmed'], self.data['data']['unconfirmed'])
        earnings.add_metric(['unpaid'], self.data['data']['unpaid'])
        earnings.add_metric(['coins_per_min'], self.data['data']['coinsPerMin'])
        earnings.add_metric(['btc_per_min'], self.data['data']['btcPerMin'])
        earnings.add_metric(['usd_per_min'], self.data['data']['usdPerMin'])

        yield hashrate
        yield shares
        yield earnings

    def query_pool(self):
        url = "https://{host}/miner/{miner}/currentStats".format(host=self.host, miner=self.miner)
        try:
            rsp = urllib3.PoolManager().request('GET', url, retries=False)
            self.data = json.loads(rsp.data.decode('utf-8'))
        except Exception:
            pass


class DSTMCollector(object):
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

    def collect(self) -> Generator:
        hashrate = GaugeMetricFamily('miner_hashrate', 'Hashrate', labels=['gpu_id', 'type'])
        efficiency = GaugeMetricFamily('miner_efficiency', 'Efficiency', labels=['gpu_id', 'type'])
        pool_shares = GaugeMetricFamily('miner_pool_shares', 'Pool Shares', labels=['gpu_id', 'type'])
        latency = GaugeMetricFamily('miner_latency', 'Latency', labels=['gpu_id'])
        uptime = GaugeMetricFamily('miner_uptime', 'Uptime', labels=['type'])

        miner_data = DSTMCollector.query_miner(self.host, self.port)

        uptime.add_metric(['miner'], miner_data['uptime'])
        uptime.add_metric(['connection'], miner_data['contime'])
        for gpu in miner_data['result']:
            gpu_id = gpu['gpu_uuid']
            hashrate.add_metric([gpu_id, 'current'], gpu['sol_ps'])
            hashrate.add_metric([gpu_id, 'average'], gpu['avg_sol_ps'])
            efficiency.add_metric([gpu_id, 'current'], gpu['sol_pw'])
            efficiency.add_metric([gpu_id, 'average'], gpu['avg_sol_pw'])
            pool_shares.add_metric([gpu_id, 'accepted'], gpu['accepted_shares'])
            pool_shares.add_metric([gpu_id, 'rejected'], gpu['rejected_shares'])
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
            rsp = s.recv(8192)  # todo: handle when rsp is larger
        return json.loads(rsp.decode('utf-8').rstrip())


def parse_args() -> Dict:
    parser = argparse.ArgumentParser(
        description='Nvidia GPU, miner and pool statistics exporter for prometheus.io',
        allow_abbrev=False,
        formatter_class=argparse.RawTextHelpFormatter)

    pool_parser = parser.add_argument_group('Pool related arguments')
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

    pool_parser.add_argument(
        '-o', '--pool',
        metavar='<name>',
        required=False,
        choices=['flypool'],
        help=textwrap.dedent('''\
            The pool name, in case pool stats are to be collected.
            Currently supported:
              - flypool'''))
    pool_parser.add_argument('-O', '--pool-api-host', metavar='<host>', required=False, help='Pool API host')
    pool_parser.add_argument('-u', '--pool-api-miner', metavar='<miner>', required=False, help='Pool API miner')

    miner_parser.add_argument(
        '-m', '--miner',
        metavar='<name>',
        required=False,
        choices=['dstm'],
        help=textwrap.dedent('''\
            The miner software, in case miner stats are to be collected.
            Currently supported:
              - dstm'''))
    miner_parser.add_argument('-H', '--miner-api-host', metavar='<host>', required=False, help='Miner API host')
    miner_parser.add_argument('-P', '--miner-api-port', metavar='<port>', type=int, required=False, help='Miner API port')

    args = parser.parse_args()

    if len(tuple(filter(None.__ne__, (args.pool, args.pool_api_host, args.pool_api_miner)))) not in (0, 3):
        parser.error('--pool requires --pool-api-host and --pool-api-miner.')
    if len(tuple(filter(None.__ne__, (args.miner, args.miner_api_host, args.miner_api_port)))) not in (0, 3):
        parser.error('--miner requires --miner-api-host and --miner-api-port.')

    return vars(args)


def pool_collectors() -> Dict:
    return {
        'flypool': FlyPoolCollector
    }


def miner_collectors() -> Dict:
    return {
        'dstm': DSTMCollector
    }


def main():
    args = parse_args()
    pool_collector = None

    urllib3.disable_warnings()
    nvml.nvmlInit()
    atexit.register(nvml.nvmlShutdown)
    REGISTRY.register(NvidiaCollector())
    if args['pool'] is not None:
        pool_collector = pool_collectors()[args['pool'].lower()](args['pool_api_host'], args['pool_api_miner'])
        pool_collector.query_pool()
        REGISTRY.register(pool_collector)
    if args['miner'] is not None:
        REGISTRY.register(miner_collectors()[args['miner'].lower()](args['miner_api_host'], args['miner_api_port']))

    print('Starting exporter...')
    try:
        start_http_server(args['port'])
        while True:
            time.sleep(60)  # 1 query per minute so we don't reach API request limits
            if pool_collector is not None:
                pool_collector.query_pool()
    except KeyboardInterrupt:
        print('Exiting...')
        exit(0)


if __name__ == '__main__':
    main()
