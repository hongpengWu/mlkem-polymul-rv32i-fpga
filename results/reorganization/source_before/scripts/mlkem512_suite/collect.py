"""Validate and summarize all three complete ML-KEM-512 PicoRV32 RTL runs."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / 'results/official_baseline/mlkem512'
FIXTURES = ROOT / 'tb/software/mlkem512_suite'
CONFIGS = {'rv32i': (0, 0, 0, 0), 'rv32im_iterative': (1, 0, 1, 1),
           'rv32im_fast': (1, 1, 1, 1)}
FIELDS = ('index,dataset,vsId,tgId,tcId,op,return_code,raw_cycles,empty_cycles,'
          'input_bytes,output_bytes,m_total,mul,mulh,mulhsu,mulhu,div,divu,rem,remu,min_sp').split(',')
M_OPS = 'mul mulh mulhsu mulhu div divu rem remu'.split()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_hash(path, wanted):
    require(path.is_file() and sha(path) == wanted, f'Changed or missing input: {path}')


def one_line(log, prefix):
    lines = [line[len(prefix):] for line in log.splitlines() if line.startswith(prefix)]
    require(len(lines) == 1, f'Expected one {prefix} record, got {len(lines)}')
    return lines[0]


def key_values(line):
    return {key: int(value, 0) for key, value in
            re.findall(r'(\w+)=(-?0x[0-9a-fA-F]+|-?[0-9]+)', line)}


def payload_bytes(case, direction):
    return sum(len(case[direction][name]) // 2 for name in case[direction + '_fields'])


def expected_rejection(case):
    if case['op'] not in (3, 4):
        return None
    parts = [bytes.fromhex(case['input'][name]) for name in case['input_fields']]
    z, ciphertext = (parts[0][-32:], parts[1]) if case['op'] == 3 else (parts[1], parts[2])
    expected_key = bytes.fromhex(case['output'][case['output_fields'][0]])
    return hashlib.shake_256(z + ciphertext).digest(32) == expected_key


def parse_log(path, config, build, cases):
    log = path.read_text(encoding='utf-8')
    require(not re.search(r'(?i)fatal:|\$fatal|ERROR:|MLKEM512_FAIL', log), f'Failure in {path}')
    require(one_line(log, 'MLKEM512_HEADER,').split(',') == FIELDS, 'Unexpected columns')
    start = key_values(one_line(log, 'MLKEM512_START '))
    end = key_values(one_line(log, 'MLKEM512_PASS '))
    params = CONFIGS[config]
    require(tuple(start[name] for name in ('mul', 'fast_mul', 'div', 'expect_m')) == params,
            f'Start CPU mismatch: {config}')
    require(tuple(end[name] for name in ('cpu_mul', 'cpu_fast_mul', 'cpu_div', 'expect_m')) == params,
            f'Completion CPU mismatch: {config}')
    require(start['cases'] == end['cases'] == len(cases) == 145, 'Wrong case count')
    require(start['ram_bytes'] == build['ram_bytes'] == 65536 and
            start['stack_bytes'] == build['stack_reserved'] == 16384 and
            start['clock_mhz'] == 100, 'Memory/clock mismatch')
    lines = [line[len('MLKEM512_ROW,'):] for line in log.splitlines()
             if line.startswith('MLKEM512_ROW,')]
    require(len(lines) == len(cases), f'Incomplete or duplicate rows: {config}')
    require(log.index('MLKEM512_START ') < log.index('MLKEM512_ROW,') <
            log.rindex('MLKEM512_ROW,') < log.index('MLKEM512_PASS '), 'Invalid log ordering')
    rows = []
    for index, (line, case) in enumerate(zip(lines, cases)):
        values = line.split(',')
        require(len(values) == len(FIELDS), f'Malformed row: {config}/{index}')
        row = dict(zip(FIELDS, (int(value, 0) for value in values)))
        wanted = [case[name] for name in ('case_index', 'dataset_id', 'vsId', 'tgId', 'tcId', 'op')]
        require([row[name] for name in FIELDS[:6]] == wanted and row['index'] == index,
                f'Case identity/order mismatch: {config}/{index}')
        require(row['return_code'] == case['expected_return'], f'API return mismatch: {config}/{index}')
        require(row['input_bytes'] == payload_bytes(case, 'input') and
                row['output_bytes'] == payload_bytes(case, 'output'),
                f'Incomplete byte comparison: {config}/{index}')
        require(row['raw_cycles'] > row['empty_cycles'] > 0, f'Invalid cycles: {config}/{index}')
        require(all(row[op] >= 0 for op in M_OPS) and row['m_total'] == sum(row[op] for op in M_OPS),
                f'M count mismatch: {config}/{index}')
        require(row['m_total'] == 0 if config == 'rv32i' else
                (row['mul'] > 0 if case['op'] in (1, 2, 3, 4) else True),
                f'Wrong M execution: {config}/{index}')
        require(build['stack_bottom'] <= end['min_sp'] <= row['min_sp'] <= build['stack_top'] and
                row['min_sp'] % 16 == 0, f'Stack outside reservation: {config}/{index}')
        rows.append(dict(config=config, **row, operation=case['operation'],
                         dataset_name=case['dataset'], revision=case['revision'],
                         expected_implicit_rejection=expected_rejection(case),
                         algorithm_ms_at_100mhz=row['raw_cycles'] / 100000,
                         observed_algorithm_stack_bytes=build['stack_top'] - row['min_sp']))
    require(end['input_bytes'] == sum(row['input_bytes'] for row in rows) == 148160 and
            end['output_bytes'] == sum(row['output_bytes'] for row in rows) == 101760,
            'Incomplete suite byte totals')
    require(end['cycles'] > sum(row['raw_cycles'] for row in rows), 'Invalid total run cycles')
    require(end['all_m'] >= sum(row['m_total'] for row in rows) and
            (end['all_m'] == 0 if config == 'rv32i' else end['all_m'] > 0), 'Invalid whole-run M count')
    require(end['min_sp'] % 16 == 0 and end['stack_used'] == build['stack_top'] - end['min_sp'],
            'Stack accounting mismatch')
    return rows, dict(config=config, cases=len(rows), input_bytes=end['input_bytes'],
                     output_bytes=end['output_bytes'], total_sim_cycles=end['cycles'],
                     timed_cycles=sum(row['raw_cycles'] for row in rows), all_m=end['all_m'],
                     timed_m=sum(row['m_total'] for row in rows), ram_bytes=build['ram_bytes'],
                     binary_bytes=build['binary_bytes'], static_end=build['static_end'],
                     stack_reserved=build['stack_reserved'], observed_stack_bytes=end['stack_used'],
                     static_m_instructions=build['static_m_instructions'],
                     firmware_sha256=build['firmware_sha256'], log_sha256=sha(path))


def group_stats(rows, by_dataset):
    groups = {}
    for row in rows:
        key = (row['config'], row['dataset'] if by_dataset else 0, row['op'], row['return_code'])
        groups.setdefault(key, []).append(row)
    result = []
    for (config, dataset, op, ret), members in groups.items():
        cycles = sorted(row['raw_cycles'] for row in members)
        entry = dict(config=config, op=op, operation=members[0]['operation'], expected_return=ret,
                     samples=len(members), cycle_min=min(cycles), cycle_mean=statistics.mean(cycles),
                     cycle_median=statistics.median(cycles), cycle_p95=cycles[math.ceil(.95 * len(cycles)) - 1],
                     cycle_max=max(cycles), mean_ms_at_100mhz=statistics.mean(cycles) / 100000,
                     input_bytes=sum(row['input_bytes'] for row in members),
                     output_bytes=sum(row['output_bytes'] for row in members),
                     m_total=sum(row['m_total'] for row in members),
                     m_by_instruction={name: sum(row[name] for row in members) for name in M_OPS},
                     observed_algorithm_stack_max=max(row['observed_algorithm_stack_bytes'] for row in members),
                     empty_cycles=sorted({row['empty_cycles'] for row in members}))
        if by_dataset:
            entry.update(dataset_id=dataset, dataset=members[0]['dataset_name'], revision=members[0]['revision'])
        result.append(entry)
    for entry in result:
        baseline = next(item for item in result if item['config'] == 'rv32i' and item['op'] == entry['op']
                        and item['expected_return'] == entry['expected_return']
                        and (not by_dataset or item['dataset_id'] == entry['dataset_id']))
        entry['speedup_vs_rv32i'] = baseline['cycle_mean'] / entry['cycle_mean']
    return result


def collect(result_dir=RESULTS):
    fixture = json.loads((FIXTURES / 'cases.json').read_text(encoding='utf-8'))
    cases = fixture['cases']
    require(fixture['parameterSet'] == 'ML-KEM-512' and fixture['case_count'] == len(cases) == 145,
            'Wrong fixture scope')
    require(len({(c['dataset_id'], c['tgId'], c['tcId']) for c in cases}) == 145, 'Duplicate official cases')
    verify_hash(ROOT / fixture['source']['manifest'], fixture['source']['manifest_sha256'])
    for entry in fixture['source']['files']:
        verify_hash(ROOT / entry['path'], entry['sha256'])
    verify_hash(ROOT / fixture['generator']['path'], fixture['generator']['sha256'])
    for name, entry in fixture['fixture']['files'].items():
        verify_hash(FIXTURES / name, entry['sha256'])
    builds = json.loads((result_dir / 'build_manifest.json').read_text(encoding='utf-8'))
    require(len(builds) == 2 and {b['isa'] for b in builds} == {'rv32i', 'rv32im'}, 'Wrong build records')
    builds = {build['isa']: build for build in builds}
    require(builds['rv32i']['source_sha256'] == builds['rv32im']['source_sha256'], 'Different source inputs')
    require(builds['rv32i']['flags'][1:] == builds['rv32im']['flags'][1:] and
            builds['rv32i']['compiler'] == builds['rv32im']['compiler'] and
            builds['rv32i']['mlkem_native_commit'] == builds['rv32im']['mlkem_native_commit'],
            'Compiler/options/library differ beyond ISA')
    for isa, build in builds.items():
        require(build['flags'][0] == f'-march={isa}', 'Compiler ISA mismatch')
        require((build['static_m_instructions'] == 0) if isa == 'rv32i' else
                (build['static_m_instructions'] > 0), 'Wrong static M count')
        require(build['static_end'] <= build['stack_bottom'] and
                build['stack_top'] - build['stack_bottom'] == build['stack_reserved'], 'Static/stack overlap')
        verify_hash(ROOT / build['firmware'], build['firmware_sha256'])
        for name, wanted in build['source_sha256'].items():
            verify_hash(ROOT / name, wanted)
    rows, configs, evidence, snapshots = [], [], {}, []
    for config, params in CONFIGS.items():
        build = builds['rv32i' if config == 'rv32i' else 'rv32im']
        run_file = result_dir / config / 'run_inputs.json'
        run = json.loads(run_file.read_text(encoding='utf-8'))
        require(run['config'] == config and run['simulator'] == 'Vivado/XSim 2024.2' and
                run['ram_bytes'] == build['ram_bytes'], 'Wrong run provenance')
        required = {'rtl/cpu/picorv32.v', 'rtl/benchmark/cpu_benchmark_system.v',
                    'tb/software/tb_mlkem512_suite.sv', 'scripts/mlkem512_suite/run.py',
                    'scripts/mlkem512_suite/run.tcl', 'scripts/mlkem512_suite/sim.tcl',
                    'results/official_baseline/mlkem512/build_manifest.json',
                    'tb/software/mlkem512_suite/cases.json', build['firmware']}
        required.update('tb/software/mlkem512_suite/' + name for name in fixture['fixture']['files'])
        require(required <= run['input_sha256'].keys(), 'Missing frozen simulation input')
        for name, wanted in run['input_sha256'].items():
            verify_hash(ROOT / name, wanted)
        snapshots.append(run['input_sha256'])
        project = ROOT / f'vivado/mlkem512_{config}'
        sim_dir = project / 'mlkem512.sim/sim_1/behav/xsim'
        verify_hash(project / 'mlkem512.mem', build['firmware_sha256'])
        verify_hash(sim_dir / 'mlkem512.mem', build['firmware_sha256'])
        for name, entry in fixture['fixture']['files'].items():
            verify_hash(sim_dir / name, entry['sha256'])
        xpr = project / 'mlkem512.xpr'
        tree = ET.parse(xpr)
        for fileset, expected in (
            ('sources_1', dict(FIRMWARE_INIT_FILE='mlkem512.mem', RAM_ADDR_BITS='14',
                              **dict(zip(('CPU_ENABLE_MUL', 'CPU_ENABLE_FAST_MUL', 'CPU_ENABLE_DIV'),
                                         map(str, params[:3]))))),
            ('sim_1', dict(zip(('CPU_ENABLE_MUL', 'CPU_ENABLE_FAST_MUL', 'CPU_ENABLE_DIV', 'EXPECT_M'),
                               map(str, params))))):
            actual = {item.get('Name'): item.get('Val') for item in
                      tree.findall(f".//FileSet[@Name='{fileset}']//Generic")}
            require(all(actual.get(key) == value for key, value in expected.items()), f'Wrong {config} {fileset}')
        log = result_dir / config / 'simulate.log'
        parsed, metrics = parse_log(log, config, build, cases)
        rows.extend(parsed)
        configs.append(metrics)
        for path in (run_file, xpr, log):
            evidence[path.relative_to(ROOT).as_posix()] = sha(path)
    require(snapshots[0] == snapshots[1] == snapshots[2], 'Runs used different frozen inputs')
    iterative = [row for row in rows if row['config'] == 'rv32im_iterative']
    fast = [row for row in rows if row['config'] == 'rv32im_fast']
    require(all(all(left[op] == right[op] for op in M_OPS) for left, right in zip(iterative, fast)),
            'RV32IM dynamic instruction mismatch')
    for path in (Path(__file__), result_dir / 'build_manifest.json', FIXTURES / 'cases.json'):
        evidence[path.relative_to(ROOT).as_posix()] = sha(path)
    negative = result_dir / 'negative_check'
    if negative.exists():
        log = (negative / 'simulate.log').read_text(encoding='utf-8')
        mutation = (negative / 'mutation.txt').read_text(encoding='utf-8')
        require('MLKEM512_FAIL byte mismatch case=0 output=1 byte=0 got=28 expected=29' in log
                and 'MLKEM512_PASS' not in log and len(re.findall(r'(?i)Fatal:', log)) == 1
                and 'result=MLKEM512_REJECTION_CHECK_PASS' in mutation,
                'Incorrect negative-check result')
        for path in (negative / 'simulate.log', negative / 'mutation.txt',
                     ROOT / 'scripts/mlkem512_suite/verify_rejection.tcl'):
            evidence[path.relative_to(ROOT).as_posix()] = sha(path)
    return dict(scope='All 145 pinned official ML-KEM-512 public ACVP records on each of three PicoRV32 RTL configurations',
                timing='Raw rdcycle delta around operation dispatch and complete API call; seed-format decapsulation includes key expansion. Input/output mailbox traffic, startup, oracle comparison and entropy acquisition excluded. Internal zeroization included; empty bracket recorded without subtraction.',
                statistics='One execution per official record per CPU. Dataset revisions remain identified; aggregate tables count records, not independent random samples. P95 uses nearest rank (ceil(0.95*n)). Key-check valid/invalid returns are separate.',
                limitations='RTL simulation only; no board measurement, post-route timing, certification, or proof of correctness beyond covered cases. Stack figures are observed depths, not worst-case bounds.',
                acvp_commit=fixture['source']['commit'], mlkem_native_commit=builds['rv32i']['mlkem_native_commit'],
                compiler=builds['rv32i']['compiler'], configs=configs,
                rejection_coverage_per_config=dict(decapsulation_records=30,
                    expected_rejection_keys=sum(expected_rejection(case) is True for case in cases),
                    method='Expected k equals FIPS 203 J(z || c) = SHAKE256(z || c, 32 bytes); API returns 0 for these records too.'),
                aggregate=group_stats(rows, False), by_dataset=group_stats(rows, True),
                evidence_sha256=evidence), rows


def markdown(summary):
    lines = ['# PicoRV32 ML-KEM-512 官方公开向量回归', '',
             '三组 CPU 各执行 145 条固定版本 ACVP 记录；输入核对 148,160 B、输出核对 101,760 B／组。',
             'Vivado 2024.2 RTL 仿真，100 MHz 时间仅为周期换算。未做实板测量或正式认证。', '',
             '每条记录执行一次。P95 使用 nearest-rank；不同数据集可能包含相同输入，样本数表示记录数。'
             'KeyCheck 成功／失败分别统计；seed decapsulation 包含 KeyGen 展开，不与 expanded decapsulation 混合。', '',
             '| CPU | 固件有效 B | 静态区结束地址 | RAM B | 栈预留 / 全程观测 B | 全程 M / 算法区间 M |',
             '|---|---:|---:|---:|---:|---:|']
    for item in summary['configs']:
        lines.append(f"| {item['config']} | {item['binary_bytes']:,} | {item['static_end']:,} | {item['ram_bytes']:,} | "
                     f"{item['stack_reserved']:,} / {item['observed_stack_bytes']:,} | {item['all_m']:,} / {item['timed_m']:,} |")
    for label, key in (('按操作汇总', 'aggregate'), ('按来源数据集与操作分组', 'by_dataset')):
        lines += ['', '## ' + label, '',
                  '| CPU | 数据集 | 操作 / 返回值 | N | 最小周期 | 平均周期 | 中位周期 | P95 周期 | 最大周期 | 平均 ms | 对 RV32I | 输入 / 输出 B | M 指令总计 | 算法栈最大 B |',
                  '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
        for item in summary[key]:
            dataset = str(item.get('dataset_id', '全部'))
            lines.append(f"| {item['config']} | {dataset} | {item['operation']} / {item['expected_return']} | {item['samples']} | "
                         f"{item['cycle_min']:,} | {item['cycle_mean']:,.2f} | {item['cycle_median']:,.1f} | {item['cycle_p95']:,} | "
                         f"{item['cycle_max']:,} | {item['mean_ms_at_100mhz']:.5f} | {item['speedup_vs_rv32i']:.3f}× | "
                         f"{item['input_bytes']:,} / {item['output_bytes']:,} | {item['m_total']:,} | {item['observed_algorithm_stack_max']:,} |")
    lines += ['', '数据集 1：FIPS203 KeyGen；2：FIPS203 encapDecap；3：FIPS203-tr1 encapDecap。', '',
              '计时排除 mailbox 输入／输出、启动、预期值检查和熵源采集；包括库内清零。空计时区间原值保留、不扣除。'
              '栈使用是本次回归观测值，不是所有输入的最坏情况上界。', '',
              '逐例数据见 `cases.csv`；来源、固件、仿真输入与日志 SHA-256 见 `summary.json`、`build_manifest.json` 和各配置 `run_inputs.json`。', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='validate without rewriting summaries')
    args = parser.parse_args()
    summary, rows = collect()
    if not args.check:
        (RESULTS / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        with (RESULTS / 'cases.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (RESULTS / 'summary.md').write_text(markdown(summary), encoding='utf-8')
    print('MLKEM512_COLLECT_PASS configs=3 cases_per_config=145 input_bytes=148160 output_bytes=101760')


if __name__ == '__main__':
    main()
