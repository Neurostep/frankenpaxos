from .batchedunreplicated import *


def main(args) -> None:
    class SmokeSuite(BatchedUnreplicatedSuite):
        def args(self) -> Dict[Any, Any]:
            return vars(args)

        def inputs(self) -> Collection[Input]:
            return [
                Input(
                    num_client_procs=1,
                    num_warmup_clients_per_proc=1,
                    num_clients_per_proc=1,
                    num_batchers=1,
                    num_proxy_servers=1,
                    client_jvm_heap_size='100m',
                    batcher_jvm_heap_size='100m',
                    server_jvm_heap_size='100m',
                    proxy_server_jvm_heap_size='100m',
                    measurement_group_size=1,
                    warmup_duration=datetime.timedelta(seconds=2),
                    warmup_timeout=datetime.timedelta(seconds=3),
                    warmup_sleep=datetime.timedelta(seconds=0),
                    duration=datetime.timedelta(seconds=2),
                    timeout=datetime.timedelta(seconds=3),
                    client_lag=datetime.timedelta(seconds=0),
                    state_machine='Noop',
                    workload=workload.StringWorkload(size_mean=1, size_std=0),
                    profiled=args.profile,
                    monitored=args.monitor,
                    prometheus_scrape_interval=datetime.timedelta(
                        milliseconds=200),
                    client_options=ClientOptions(),
                    client_log_level=args.log_level,
                    batcher_options=BatcherOptions(batch_size=1,),
                    batcher_log_level=args.log_level,
                    server_options=ServerOptions(flush_every_n=1,),
                    server_log_level=args.log_level,
                    proxy_server_options=ProxyServerOptions(flush_every_n=1,),
                    proxy_server_log_level=args.log_level,
                )
            ]

        def summary(self, input: Input, output: Output) -> str:
            return str({
                'num_client_procs': input.num_client_procs,
                'num_clients_per_proc': input.num_clients_per_proc,
                'latency.median_ms': f'{output.latency.median_ms:.6}',
                'start_throughput_1s.p90': f'{output.start_throughput_1s.p90:.6}',
            })

    suite = SmokeSuite()
    with benchmark.SuiteDirectory(args.suite_directory,
                                  'batchedunreplicated_smoke') as dir:
        suite.run_suite(dir)


if __name__ == '__main__':
    main(get_parser().parse_args())
