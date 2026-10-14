"""Validate and collect the three single-case PicoRV32 KeyGen simulations."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / 'results/official_baseline/keygen512_tc1'
CONFIGS = {'rv32i': (0, 0, 0, 0),
           'rv32im_iterative': (1, 0, 1, 1),
           'rv32im_fast': (1, 1, 1, 1)}
FIELDS = ('tcId,param,cpu_mul,cpu_fast_mul,cpu_div,expect_m,raw_cycles,'
          'empty_cycles,input_bytes,output_bytes,m_total,mul,mulh,mulhsu,'
          'mulhu,div,divu,rem,remu,min_sp').split(',')
M_OPS = 'mul mulh mulhsu mulhu div divu rem remu'.split()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_hash(path, wanted):
    require(path.is_file() and sha(path) == wanted, f'Changed or missing input: {path}')


def one_line(log, prefix):
    lines = [line for line in log.splitlines() if line.startswith(prefix)]
    require(len(lines) == 1, f'Expected exactly one {prefix} record, got {len(lines)}')
    return lines[0][len(prefix):]


def key_values(line):
    return {key: int(value, 0) for key, value in re.findall(r'(\w+)=(0x[0-9a-f]+|[0-9]+)', line)}


def parse_log(path, config, build):
    log = path.read_text(encoding='utf-8')
    require(not re.search(r'(?i)fatal:|\$fatal|ERROR:|MLKEM_KEYGEN_FAIL', log),
            f'Failure in {path}')
    require(one_line(log, 'MLKEM_KEYGEN_HEADER,').split(',') == FIELDS, 'Unexpected columns')
    values = one_line(log, 'MLKEM_KEYGEN_ROW,').split(',')
    require(len(values) == len(FIELDS), 'Malformed result row')
    row = dict(zip(FIELDS, (int(value, 0) for value in values)))
    start = key_values(one_line(log, 'MLKEM_KEYGEN_START '))
    end = key_values(one_line(log, 'MLKEM_KEYGEN_PASS '))
    params = CONFIGS[config]
    require(tuple(row[name] for name in FIELDS[2:6]) == params, f'Wrong CPU config: {config}')
    require(tuple(start[name] for name in ('mul', 'fast_mul', 'div', 'expect_m')) == params,
            'Start config mismatch')
    require(tuple(end[name] for name in FIELDS[2:6]) == params, 'Completion config mismatch')
    require(row['tcId'] == 1 and row['param'] == 512, 'Unexpected official case')
    require(start['cases'] == end['cases'] == 1, 'Unexpected case count')
    require(start['ram_bytes'] == build['ram_bytes'] == 65536 and
            start['stack_bytes'] == build['stack_reserved'] == 16384 and
            start['clock_mhz'] == 100, 'Memory/clock mismatch')
    require(row['input_bytes'] == end['input_bytes'] == 64 and
            row['output_bytes'] == end['output_bytes'] == 2432, 'Incomplete byte comparison')
    require(row['raw_cycles'] > row['empty_cycles'] > 0 and
            end['cycles'] > row['raw_cycles'], 'Invalid cycle count')
    require(row['m_total'] == end['all_m'] == sum(row[op] for op in M_OPS), 'M count mismatch')
    require(all(row[op] >= 0 for op in M_OPS), 'Negative M count')
    require(row['m_total'] == 0 if config == 'rv32i' else row['mul'] > 0, 'M not exercised')
    require(build['stack_bottom'] <= end['min_sp'] <= row['min_sp'] <= build['stack_top'],
            'Stack outside reserved area')
    require(end['min_sp'] % 16 == row['min_sp'] % 16 == 0 and
            end['stack_used'] == build['stack_top'] - end['min_sp'], 'Stack accounting mismatch')
    require(build['static_end'] <= build['stack_bottom'], 'Static image overlaps stack')
    return dict(config=config, **row, clock_mhz=100,
                keygen_ms_at_100mhz=row['raw_cycles'] / 100000,
                total_sim_cycles=end['cycles'], ram_bytes=build['ram_bytes'],
                binary_bytes=build['binary_bytes'], static_end=build['static_end'],
                observed_stack_bytes=end['stack_used'], stack_reserved=build['stack_reserved'],
                static_m_instructions=build['static_m_instructions'],
                firmware_sha256=build['firmware_sha256'], log_sha256=sha(path))


def collect(result_dir):
    fixtures = ROOT / 'tb/software/mlkem_keygen'
    fixture = json.loads((fixtures / 'mlkem512_keygen.json').read_text(encoding='utf-8'))
    require(fixture['revision'] == 'FIPS203' and fixture['operation'] == 'keyGen' and
            fixture['parameterSet'] == 'ML-KEM-512' and
            fixture['cases'] == [dict(tcId=1, dBytes=32, zBytes=32, ekBytes=800, dkBytes=1632)],
            'Wrong fixture scope')
    verify_hash(ROOT / fixture['source']['manifest'], fixture['source']['manifest_sha256'])
    for entry in fixture['source']['files']:
        verify_hash(ROOT / entry['path'], entry['sha256'])
    verify_hash(ROOT / fixture['generator']['path'], fixture['generator']['sha256'])
    for name, entry in fixture['outputs'].items():
        verify_hash(fixtures / name, entry['sha256'])

    builds = json.loads((result_dir / 'build_manifest.json').read_text(encoding='utf-8'))
    require(len(builds) == 2 and {b['isa'] for b in builds} == {'rv32i', 'rv32im'},
            'Expected RV32I and RV32IM build records')
    builds = {b['isa']: b for b in builds}
    require(builds['rv32i']['source_sha256'] == builds['rv32im']['source_sha256'],
            'The two ISAs use different source/fixture inputs')
    require(builds['rv32i']['flags'][1:] == builds['rv32im']['flags'][1:] and
            builds['rv32i']['compiler'] == builds['rv32im']['compiler'],
            'Compiler/options differ beyond ISA')
    for isa, build in builds.items():
        require(build['flags'][0] == f'-march={isa}', 'Compiler ISA flag mismatch')
        require((build['static_m_instructions'] == 0) if isa == 'rv32i'
                else (build['static_m_instructions'] > 0), 'Wrong static M instruction count')
        verify_hash(ROOT / build['firmware'], build['firmware_sha256'])
        for name, wanted in build['source_sha256'].items():
            verify_hash(ROOT / name, wanted)

    rows, hashes = [], {}
    for config, params in CONFIGS.items():
        isa = 'rv32i' if config == 'rv32i' else 'rv32im'
        build = builds[isa]
        project = ROOT / f'vivado/mlkem_keygen_{config}'
        # Check both the saved project image and the image actually copied for XSim.
        verify_hash(project / 'mlkem_keygen.mem', build['firmware_sha256'])
        sim_dir = project / 'mlkem_keygen.sim/sim_1/behav/xsim'
        if sim_dir.exists():
            verify_hash(sim_dir / 'mlkem_keygen.mem', build['firmware_sha256'])
            for name in ('mlkem512_keygen_input.mem', 'mlkem512_keygen_expected.mem'):
                verify_hash(sim_dir / name, fixture['outputs'][name]['sha256'])
        xpr = project / 'mlkem_keygen.xpr'
        tree = ET.parse(xpr)
        for fileset, expected in (
            ('sources_1', dict(FIRMWARE_INIT_FILE='mlkem_keygen.mem', RAM_ADDR_BITS='14',
                              **dict(zip(('CPU_ENABLE_MUL', 'CPU_ENABLE_FAST_MUL', 'CPU_ENABLE_DIV'),
                                         map(str, params[:3]))))),
            ('sim_1', dict(zip(('CPU_ENABLE_MUL', 'CPU_ENABLE_FAST_MUL', 'CPU_ENABLE_DIV', 'EXPECT_M'),
                               map(str, params))))):
            actual = {x.get('Name'): x.get('Val')
                      for x in tree.findall(f".//FileSet[@Name='{fileset}']//Generic")}
            require(all(actual.get(k) == v for k, v in expected.items()), f'Wrong {config} {fileset}')
        log = result_dir / config / 'simulate.log'
        rows.append(parse_log(log, config, build))
        for path in (xpr, log, project / 'mlkem_keygen.mem'):
            hashes[path.relative_to(ROOT).as_posix()] = sha(path)
    require(all(rows[1][op] == rows[2][op] for op in M_OPS), 'RV32IM dynamic instruction mismatch')
    for row in rows:
        row['speedup_vs_rv32i'] = rows[0]['raw_cycles'] / row['raw_cycles']
    for path in (ROOT / 'rtl/cpu/picorv32.v', ROOT / 'rtl/benchmark/cpu_benchmark_system.v',
                 ROOT / 'tb/software/tb_mlkem_keygen.sv', ROOT / 'third_party/mlkem-native/SOURCE_MANIFEST.json',
                 ROOT / 'scripts/mlkem_baseline/build.py', ROOT / 'scripts/mlkem_baseline/run.tcl',
                 Path(__file__), result_dir / 'build_manifest.json', fixtures / 'mlkem512_keygen.json'):
        hashes[path.relative_to(ROOT).as_posix()] = sha(path)
    negative = result_dir / 'negative_check'
    if negative.exists():
        mutation = (negative / 'mutation.txt').read_text(encoding='utf-8')
        bad_log = (negative / 'simulate.log').read_text(encoding='utf-8')
        marker = ('MLKEM_KEYGEN_FAIL byte mismatch tcId=1 event=00000103 '
                  'byte=0 got=28 expected=29')
        require(marker in bad_log and 'MLKEM_KEYGEN_PASS' not in bad_log and
                len(re.findall(r'(?i)Fatal:', bad_log)) == 1 and
                'result=MLKEM_REJECTION_CHECK_PASS' in mutation,
                'Negative check did not reject the injected byte')
        for path in (negative / 'simulate.log', negative / 'mutation.txt',
                     ROOT / 'scripts/mlkem_baseline/verify_rejection.tcl'):
            hashes[path.relative_to(ROOT).as_posix()] = sha(path)
    return dict(scope='One official ML-KEM-512 KeyGen case (tcId=1), PicoRV32 RTL simulation only',
                timing='Raw rdcycle delta around keypair_derand; d/z ready; includes default internal '
                       'zeroization; excludes input/output debug streaming, startup and oracle checks; '
                       'empty bracket recorded without subtraction. No entropy-source latency.',
                limitations='Not full KEM/all KAT coverage, certification, board measurement, '
                            'post-route timing, or a performance distribution.',
                acvp_commit=fixture['source']['commit'],
                mlkem_native_commit=builds['rv32i']['mlkem_native_commit'],
                compiler=builds['rv32i']['compiler'], rows=rows, evidence_sha256=hashes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='validate without rewriting summaries')
    args = parser.parse_args()
    summary = collect(RESULTS)
    if not args.check:
        (RESULTS / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        with (RESULTS / 'summary.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(summary['rows'][0]))
            writer.writeheader()
            writer.writerows(summary['rows'])
        lines = ['# PicoRV32：官方 ML-KEM-512 KeyGen 单用例', '',
                 'ACVP FIPS203 / tgId=1 / tcId=1。Vivado 2024.2 RTL 仿真；每组一个样本。', '',
                 '| CPU 配置 | KeyGen 周期 | 时间 @100 MHz (ms) | 相对 RV32I | 输入/输出核对 (B) | 动态 MUL |',
                 '|---|---:|---:|---:|---:|---:|']
        for row in summary['rows']:
            lines.append(f"| {row['config']} | {row['raw_cycles']:,} | {row['keygen_ms_at_100mhz']:.5f} | "
                         f"{row['speedup_vs_rv32i']:.4f}× | 64 / 2432 PASS | {row['mul']:,} |")
        lines += ['', '计时仅覆盖 `keypair_derand()` 调用，种子已就绪；包含库内默认清零，'
                  '不含输入/输出调试传输、启动、结果检查及熵源采集。空计时区间 4 周期单列、不扣除。', '',
                  '| CPU 配置 | 镜像有效字节 | 静态区结束地址（十进制） | RAM (B) | 栈预留 / 观测使用 (B) |',
                  '|---|---:|---:|---:|---:|']
        for row in summary['rows']:
            lines.append(f"| {row['config']} | {row['binary_bytes']:,} | {row['static_end']:,} | "
                         f"65,536 | 16,384 / {row['observed_stack_bytes']:,} |")
        lines += ['', '栈使用按本用例观测到的最低 SP 计算；不是所有合法输入的最坏情况上界。'
                  '当前工程未做综合/布局布线，100 MHz 时间为仿真周期换算。'
                  '未覆盖完整 KEM、全部 KAT 或实板，也不代表 NIST 认证。', '',
                  '来源、镜像、日志和当前构建输入 SHA-256 见 `summary.json` 与 `build_manifest.json`。', '']
        (RESULTS / 'summary.md').write_text('\n'.join(lines), encoding='utf-8')
    print('MLKEM_KEYGEN_COLLECT_PASS configs=3 cases_per_config=1 input_bytes=64 output_bytes=2432')


if __name__ == '__main__':
    main()
