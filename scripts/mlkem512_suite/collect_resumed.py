"""Validate preserved ML-KEM-512 prefixes and independently completed resume batches."""
from pathlib import Path
import argparse
import csv
import json
import re
import xml.etree.ElementTree as ET

from collect import (ROOT, RESULTS, FIXTURES, CONFIGS, FIELDS, M_OPS, require, sha,
                     verify_hash, one_line, key_values, payload_bytes,
                     expected_rejection, group_stats, markdown)


PREFIX_COUNTS = {'rv32i': 25, 'rv32im_iterative': 31, 'rv32im_fast': 38}
RESUME_MUTABLE = {
    'tb/software/tb_mlkem512_suite.sv',
    'scripts/mlkem512_suite/run.py',
    'scripts/mlkem512_suite/run.tcl',
    'scripts/mlkem512_suite/sim.tcl',
}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def evidence_file(evidence, path):
    evidence[path.relative_to(ROOT).as_posix()] = sha(path)


def validate_fixture_builds(result_dir):
    fixture = read_json(FIXTURES / 'cases.json')
    cases = fixture['cases']
    require(fixture['parameterSet'] == 'ML-KEM-512' and
            fixture['case_count'] == len(cases) == 145, 'Wrong fixture scope')
    require([case['case_index'] for case in cases] == list(range(145)),
            'Noncanonical official case indices')
    require(len({(case['dataset_id'], case['tgId'], case['tcId']) for case in cases}) == 145,
            'Duplicate official cases')
    verify_hash(ROOT / fixture['source']['manifest'], fixture['source']['manifest_sha256'])
    for entry in fixture['source']['files']:
        verify_hash(ROOT / entry['path'], entry['sha256'])
    verify_hash(ROOT / fixture['generator']['path'], fixture['generator']['sha256'])
    for name, entry in fixture['fixture']['files'].items():
        verify_hash(FIXTURES / name, entry['sha256'])
    build_records = read_json(result_dir / 'build_manifest.json')
    require(len(build_records) == 2 and {b['isa'] for b in build_records} == {'rv32i', 'rv32im'},
            'Wrong build records')
    builds = {build['isa']: build for build in build_records}
    require(builds['rv32i']['source_sha256'] == builds['rv32im']['source_sha256'],
            'Different firmware source inputs')
    require(builds['rv32i']['flags'][1:] == builds['rv32im']['flags'][1:] and
            builds['rv32i']['compiler'] == builds['rv32im']['compiler'] and
            builds['rv32i']['mlkem_native_commit'] == builds['rv32im']['mlkem_native_commit'],
            'Compiler/options/library differ beyond ISA')
    for isa, build in builds.items():
        require(build['flags'][0] == f'-march={isa}', 'Compiler ISA mismatch')
        require((build['static_m_instructions'] == 0) if isa == 'rv32i' else
                (build['static_m_instructions'] > 0), 'Wrong static M count')
        require(build['ram_bytes'] == 65536 and build['stack_reserved'] == 16384 and
                build['static_end'] <= build['stack_bottom'] and
                build['stack_top'] - build['stack_bottom'] == build['stack_reserved'],
                'Invalid memory layout')
        verify_hash(ROOT / build['firmware'], build['firmware_sha256'])
        for name, wanted in build['source_sha256'].items():
            verify_hash(ROOT / name, wanted)
    return fixture, builds


def parse_row(line, label):
    values = line.split(',')
    require(len(values) == len(FIELDS), f'Malformed row: {label}')
    try:
        return dict(zip(FIELDS, (int(value, 0) for value in values)))
    except ValueError as error:
        raise ValueError(f'Noninteger row: {label}') from error


def validate_row(row, case, config, build, local_index):
    label = f'{config}/{case["case_index"]}'
    wanted = [local_index] + [case[name] for name in ('dataset_id', 'vsId', 'tgId', 'tcId', 'op')]
    require([row[name] for name in FIELDS[:6]] == wanted, f'Case identity/order mismatch: {label}')
    require(row['return_code'] == case['expected_return'], f'API return mismatch: {label}')
    require(row['input_bytes'] == payload_bytes(case, 'input') and
            row['output_bytes'] == payload_bytes(case, 'output'),
            f'Incomplete byte comparison: {label}')
    require(row['raw_cycles'] > row['empty_cycles'] > 0, f'Invalid cycles: {label}')
    require(all(row[op] >= 0 for op in M_OPS) and row['m_total'] == sum(row[op] for op in M_OPS),
            f'M count mismatch: {label}')
    require(row['m_total'] == 0 if config == 'rv32i' else
            (row['mul'] > 0 if case['op'] in (1, 2, 3, 4) else True),
            f'Wrong M execution: {label}')
    require(build['stack_bottom'] <= row['min_sp'] <= build['stack_top'] and
            row['min_sp'] % 16 == 0, f'Stack outside reservation: {label}')
    return dict(config=config, **dict(row, index=case['case_index']),
                original_case_index=case['case_index'],
                operation=case['operation'], dataset_name=case['dataset'], revision=case['revision'],
                expected_implicit_rejection=expected_rejection(case),
                algorithm_ms_at_100mhz=row['raw_cycles'] / 100000,
                observed_algorithm_stack_bytes=build['stack_top'] - row['min_sp'])


def validate_start(log, config, count):
    require(not re.search(r'(?im)^.*(?:fatal:|\$fatal|ERROR:|MLKEM512_FAIL)',
                          '\n'.join(line for line in log.splitlines() if not line.startswith('#'))),
            f'Failure in {config} log')
    require(one_line(log, 'MLKEM512_HEADER,').split(',') == FIELDS, 'Unexpected columns')
    start = key_values(one_line(log, 'MLKEM512_START '))
    require(tuple(start[name] for name in ('mul', 'fast_mul', 'div', 'expect_m')) == CONFIGS[config],
            f'Start CPU mismatch: {config}')
    require(start['cases'] == count and start['ram_bytes'] == 65536 and
            start['stack_bytes'] == 16384 and start['clock_mhz'] == 100,
            f'Wrong case count, memory or clock: {config}')


def validate_checkpoint(result_dir=RESULTS):
    """Return fixture, builds, per-config prefix rows, provenance and frozen inputs."""
    result_dir = Path(result_dir)
    fixture, builds = validate_fixture_builds(result_dir)
    checkpoint_dir = result_dir / 'checkpoint'
    checkpoint_file = checkpoint_dir / 'checkpoint.json'
    checkpoint = read_json(checkpoint_file)
    require(checkpoint['status'] == 'paused_for_shutdown' and
            checkpoint['total_cases_per_config'] == 145 and
            set(checkpoint['configs']) == set(CONFIGS), 'Wrong checkpoint scope')
    evidence, prefixes, snapshots = {}, {}, []
    evidence_file(evidence, checkpoint_file)
    for config, count in PREFIX_COUNTS.items():
        saved = checkpoint['configs'][config]
        require(saved['completed'] == saved['next_case_index'] == count and
                saved['remaining'] == 145 - count, f'Wrong saved prefix count: {config}')
        directory = checkpoint_dir / config
        csv_path = directory / 'completed_rows.csv'
        verify_hash(csv_path, saved['rows_sha256'])
        csv_lines = csv_path.read_text(encoding='utf-8').splitlines()
        require(csv_lines[0].split(',') == FIELDS and len(csv_lines) == count + 1,
                f'Wrong saved CSV size/columns: {config}')
        log_path = directory / 'partial_console.txt'
        log = log_path.read_text(encoding='utf-8')
        validate_start(log, config, 145)
        require(not any(line.startswith('MLKEM512_PASS ') for line in log.splitlines()),
                f'Checkpoint unexpectedly claims a complete run: {config}')
        log_lines = [line[len('MLKEM512_ROW,'):] for line in log.splitlines()
                     if line.startswith('MLKEM512_ROW,')]
        require(log_lines == csv_lines[1:], f'Saved CSV differs from original console: {config}')
        require(log.index('MLKEM512_START ') < log.index('MLKEM512_ROW,'),
                f'Invalid original log ordering: {config}')
        build = builds['rv32i' if config == 'rv32i' else 'rv32im']
        prefixes[config] = []
        for index, line in enumerate(log_lines):
            row = validate_row(parse_row(line, f'{config}/{index}'), fixture['cases'][index],
                               config, build, index)
            row.update(source_kind='checkpoint_prefix', source_chunk='checkpoint',
                       source_local_index=index)
            prefixes[config].append(row)
        run_path = directory / 'run_inputs.json'
        run = read_json(run_path)
        require(run['config'] == config and run['simulator'] == 'Vivado/XSim 2024.2' and
                run['ram_bytes'] == 65536, f'Wrong original run provenance: {config}')
        required = {'rtl/cpu/picorv32.v', 'rtl/benchmark/cpu_benchmark_system.v',
                    'results/official_baseline/mlkem512/build_manifest.json',
                    'tb/software/mlkem512_suite/cases.json', build['firmware']} | RESUME_MUTABLE
        required.update('tb/software/mlkem512_suite/' + name for name in fixture['fixture']['files'])
        require(required <= run['input_sha256'].keys(), f'Missing frozen simulation input: {config}')
        for name, wanted in run['input_sha256'].items():
            archived = checkpoint_dir / 'inputs' / name
            verify_hash(archived, wanted)
            evidence_file(evidence, archived)
            if name not in RESUME_MUTABLE:
                verify_hash(ROOT / name, wanted)
        snapshots.append(run['input_sha256'])
        for path in (csv_path, log_path, run_path):
            evidence_file(evidence, path)
    require(snapshots[0] == snapshots[1] == snapshots[2], 'Original runs used different frozen inputs')
    return fixture, builds, prefixes, evidence, snapshots[0]


def verify_batch_fixture(directory, cases, expected):
    """Reconstruct every metadata and payload word from the official canonical cases."""
    direction = 'output' if expected else 'input'
    words = [0x3254414B, 1, 512, len(cases), 0, 0, 0, 0]
    for local_index, case in enumerate(cases):
        inputs = [len(bytes.fromhex(case['input'][name])) for name in case['input_fields']]
        outputs = [len(bytes.fromhex(case['output'][name])) for name in case['output_fields']]
        metadata = [local_index] + [case[name] for name in ('dataset_id', 'vsId', 'tgId', 'tcId', 'op')]
        metadata += inputs + [0] * (3 - len(inputs)) + outputs + [0] * (2 - len(outputs))
        metadata += [case['expected_return'] & 0xffffffff if expected else 0]
        require(len(metadata) == 12, 'Invalid official fixture metadata')
        words.extend(metadata)
        for name in case[direction + '_fields']:
            payload = bytes.fromhex(case[direction][name])
            require(len(payload) % 4 == 0, 'Unaligned official payload')
            words.extend(int.from_bytes(payload[offset:offset + 4], 'little')
                         for offset in range(0, len(payload), 4))
    words[4] = len(words)
    path = directory / ('mlkem512_expected.mem' if expected else 'mlkem512_input.mem')
    actual = [int(line, 16) for line in path.read_text(encoding='ascii').splitlines()]
    require(actual == words, f'Batch fixture differs from official cases: {path}')
    return len(words)


def parse_batch_log(path, config, build, cases):
    log = path.read_text(encoding='utf-8')
    validate_start(log, config, len(cases))
    end = key_values(one_line(log, 'MLKEM512_PASS '))
    require(tuple(end[name] for name in ('cpu_mul', 'cpu_fast_mul', 'cpu_div', 'expect_m')) ==
            CONFIGS[config], f'Completion CPU mismatch: {path}')
    lines = [line[len('MLKEM512_ROW,'):] for line in log.splitlines()
             if line.startswith('MLKEM512_ROW,')]
    require(len(lines) == end['cases'] == len(cases), f'Incomplete or duplicate batch rows: {path}')
    require(log.index('MLKEM512_START ') < log.index('MLKEM512_ROW,') <=
            log.rindex('MLKEM512_ROW,') < log.index('MLKEM512_PASS '),
            f'Invalid batch log ordering: {path}')
    rows = [validate_row(parse_row(line, str(path)), case, config, build, index)
            for index, (line, case) in enumerate(zip(lines, cases))]
    require(end['input_bytes'] == sum(row['input_bytes'] for row in rows) and
            end['output_bytes'] == sum(row['output_bytes'] for row in rows),
            f'Incomplete batch byte totals: {path}')
    require(end['cycles'] > sum(row['raw_cycles'] for row in rows), f'Invalid total batch cycles: {path}')
    require(end['all_m'] >= sum(row['m_total'] for row in rows) and
            (end['all_m'] == 0 if config == 'rv32i' else
             (end['all_m'] > 0 if any(case['op'] in (1, 2, 3, 4) for case in cases) else True)),
            f'Invalid whole-batch M count: {path}')
    require(build['stack_bottom'] <= end['min_sp'] <= min(row['min_sp'] for row in rows) and
            end['min_sp'] % 16 == 0 and end['stack_used'] == build['stack_top'] - end['min_sp'],
            f'Batch stack accounting mismatch: {path}')
    return rows, dict(config=config, cases=len(rows), input_bytes=end['input_bytes'],
                      output_bytes=end['output_bytes'], total_sim_cycles=end['cycles'],
                      all_m=end['all_m'], observed_stack_bytes=end['stack_used'],
                      minimum_sp=end['min_sp'], timed_cycles=sum(row['raw_cycles'] for row in rows),
                      timed_m=sum(row['m_total'] for row in rows), log_sha256=sha(path))


def batch_project_dir(batch_dir):
    return ROOT / 'build/mlkem512_suite/batches' / batch_dir.parent.name / batch_dir.name


def validate_project_generics(xpr, config, count):
    tree = ET.parse(xpr)
    params = CONFIGS[config]
    for fileset, expected in (
        ('sources_1', dict(FIRMWARE_INIT_FILE='mlkem512.mem', RAM_ADDR_BITS='14',
                          **dict(zip(('CPU_ENABLE_MUL', 'CPU_ENABLE_FAST_MUL', 'CPU_ENABLE_DIV'),
                                     map(str, params[:3]))))),
        ('sim_1', dict(EXPECTED_CASES=str(count),
                      **dict(zip(('CPU_ENABLE_MUL', 'CPU_ENABLE_FAST_MUL', 'CPU_ENABLE_DIV', 'EXPECT_M'),
                                 map(str, params)))))):
        actual = {item.get('Name'): item.get('Val') for item in
                  tree.findall(f".//FileSet[@Name='{fileset}']//Generic")}
        require(all(actual.get(key) == value for key, value in expected.items()),
                f'Wrong batch project generics: {xpr}/{fileset}')


def expected_project_hashes(batch_dir, build):
    sim = 'mlkem512.sim/sim_1/behav/xsim/'
    return {'mlkem512.mem': build['firmware_sha256'],
            sim + 'mlkem512.mem': build['firmware_sha256'],
            **{sim + name: sha(batch_dir / name) for name in
               ('mlkem512_input.mem', 'mlkem512_expected.mem', 'simulate.log')}}


def validate_project_evidence(batch_dir, build, config, count):
    """Inspect live staging if present; otherwise require previously verified archive."""
    project = batch_project_dir(batch_dir)
    archive = batch_dir / 'project.xpr'
    manifest = batch_dir / 'project_evidence.json'
    wanted = expected_project_hashes(batch_dir, build)
    if project.exists():
        require(project.is_dir(), f'Invalid live batch project: {project}')
        for name, digest in wanted.items():
            verify_hash(project / name, digest)
        validate_project_generics(project / 'mlkem512.xpr', config, count)
    else:
        require(manifest.is_file() and archive.is_file(),
                f'No live project or archived project evidence: {batch_dir}; '
                'archive successful batches before removing build caches')
    if manifest.exists() or archive.exists():
        require(manifest.is_file() and archive.is_file(), f'Incomplete project evidence archive: {batch_dir}')
        record = read_json(manifest)
        require(record['schema_version'] == 1 and record['config'] == config and
                record['batch'] == batch_dir.name and record['case_count'] == count and
                record['archive'] == 'project.xpr' and record['staged_sha256'] == wanted,
                f'Wrong archived project identity or staged hashes: {batch_dir}')
        for name, key in (('batch.json', 'batch_sha256'), ('run_inputs.json', 'run_inputs_sha256'),
                          ('success.json', 'success_sha256'), ('simulate.log', 'log_sha256')):
            verify_hash(batch_dir / name, record[key])
        verify_hash(archive, record['xpr_sha256'])
        validate_project_generics(archive, config, count)
        if project.exists():
            verify_hash(project / 'mlkem512.xpr', record['xpr_sha256'])
        return [archive, manifest]
    return []


def validate_batch(batch_dir, fixture, builds, original_hashes=None):
    """Return (rows, genuine whole-batch metrics, evidence hashes) after strict validation."""
    batch_dir = Path(batch_dir)
    batch_path = batch_dir / 'batch.json'
    batch = read_json(batch_path)
    config = batch['config']
    require(config in CONFIGS and batch_dir.parent.name == config and batch['schema_version'] == 1,
            f'Wrong batch scope: {batch_dir}')
    indices = batch['original_indices']
    require(isinstance(indices, list) and indices and all(type(index) is int for index in indices) and
            len(indices) == len(set(indices)) and indices == sorted(indices) and
            all(PREFIX_COUNTS[config] <= index < 145 for index in indices),
            f'Invalid or repeated original case indices: {batch_dir}')
    require(batch_dir.name == f'batch_{indices[0]:03d}_{indices[-1]:03d}' and
            batch['case_count'] == len(indices), f'Wrong batch identity/count: {batch_dir}')
    cases = [fixture['cases'][index] for index in indices]
    require(batch['input_words'] == verify_batch_fixture(batch_dir, cases, False) and
            batch['expected_words'] == verify_batch_fixture(batch_dir, cases, True) and
            batch['input_bytes'] == sum(payload_bytes(case, 'input') for case in cases) and
            batch['output_bytes'] == sum(payload_bytes(case, 'output') for case in cases),
            f'Batch sizes do not match official records: {batch_dir}')
    run_path, log_path, success_path = [batch_dir / name for name in
                                        ('run_inputs.json', 'simulate.log', 'success.json')]
    success = read_json(success_path)
    require(success['status'] == 'passed' and success['config'] == config and
            success['case_count'] == len(cases), f'Batch did not complete successfully: {batch_dir}')
    for path, key in ((batch_path, 'batch_sha256'), (log_path, 'log_sha256'),
                      (run_path, 'run_inputs_sha256')):
        verify_hash(path, success[key])
    run = read_json(run_path)
    require(run['config'] == config and run['simulator'] == 'Vivado/XSim 2024.2' and
            run['ram_bytes'] == 65536, f'Wrong resumed run provenance: {batch_dir}')
    hashes = run['input_sha256']
    if original_hashes is None:
        _, _, _, _, original_hashes = validate_checkpoint(batch_dir.parents[2])
    stable = {name: wanted for name, wanted in original_hashes.items() if name not in RESUME_MUTABLE}
    required = set(stable) | {'tb/software/tb_mlkem512_suite.sv',
                             'scripts/mlkem512_suite/sim.tcl'}
    required.update(path.relative_to(ROOT).as_posix() for path in
                    (batch_path, batch_dir / 'mlkem512_input.mem', batch_dir / 'mlkem512_expected.mem'))
    require(required <= hashes.keys(), f'Missing frozen batch input: {batch_dir}')
    require(any(name.endswith('.py') and 'mlkem512_suite/' in name for name in hashes) and
            any(name.endswith('.tcl') and 'mlkem512_suite/' in name and not name.endswith('/sim.tcl')
                for name in hashes), f'Missing batch runner provenance: {batch_dir}')
    require(all(hashes[name] == wanted for name, wanted in stable.items()),
            f'Batch changed original CPU, firmware or canonical fixture: {batch_dir}')
    for name, wanted in hashes.items():
        verify_hash(ROOT / name, wanted)
    build = builds['rv32i' if config == 'rv32i' else 'rv32im']
    archived_paths = validate_project_evidence(batch_dir, build, config, len(cases))
    rows, metrics = parse_batch_log(log_path, config, build, cases)
    for index, row in enumerate(rows):
        row.update(source_kind='resumed_batch', source_chunk=batch_dir.name, source_local_index=index)
    metrics.update(batch=batch_dir.name, original_indices=indices,
                   run_inputs_sha256=sha(run_path), batch_sha256=sha(batch_path))
    evidence = {}
    for path in [batch_path, run_path, log_path, success_path, batch_dir / 'mlkem512_input.mem',
                 batch_dir / 'mlkem512_expected.mem'] + archived_paths:
        evidence_file(evidence, path)
    return rows, metrics, evidence


def archive_project_evidence(result_dir=RESULTS):
    """Archive only fully validated successful batches; never change simulation inputs."""
    result_dir = Path(result_dir)
    fixture, builds, _, _, original_hashes = validate_checkpoint(result_dir)
    archived = 0
    successes = sorted((result_dir / 'batches').glob('*/batch_*/success.json'))
    for success in successes:
        batch_dir = success.parent
        validate_batch(batch_dir, fixture, builds, original_hashes)
        manifest = batch_dir / 'project_evidence.json'
        if manifest.exists():
            continue
        batch = read_json(batch_dir / 'batch.json')
        config = batch['config']
        build = builds['rv32i' if config == 'rv32i' else 'rv32im']
        project = batch_project_dir(batch_dir)
        xpr_bytes = (project / 'mlkem512.xpr').read_bytes()
        record = dict(schema_version=1, config=config, batch=batch_dir.name,
                      case_count=batch['case_count'], archive='project.xpr',
                      purpose='Archived simulation project provenance; use normal vivado/mlkem512_* '
                              'projects for opening the main suite in Vivado.',
                      batch_sha256=sha(batch_dir / 'batch.json'),
                      run_inputs_sha256=sha(batch_dir / 'run_inputs.json'),
                      success_sha256=sha(success), log_sha256=sha(batch_dir / 'simulate.log'),
                      xpr_sha256=sha(project / 'mlkem512.xpr'),
                      staged_sha256=expected_project_hashes(batch_dir, build))
        archive = batch_dir / 'project.xpr'
        archive.write_bytes(xpr_bytes)
        manifest.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
        validate_batch(batch_dir, fixture, builds, original_hashes)
        archived += 1
    return dict(successful_batches=len(successes), newly_archived=archived)


def collect(result_dir=RESULTS):
    result_dir = Path(result_dir)
    fixture, builds, prefixes, evidence, frozen = validate_checkpoint(result_dir)
    rows, configs = [], []
    for config in CONFIGS:
        config_rows = list(prefixes[config])
        batches = []
        batch_root = result_dir / 'batches' / config
        require(batch_root.is_dir(), f'Missing resumed batches: {config}')
        for directory in sorted(batch_root.iterdir()):
            if not directory.is_dir():
                continue
            require(directory.name.startswith('batch_'), f'Unexpected batch directory: {directory}')
            parsed, metrics, batch_evidence = validate_batch(directory, fixture, builds, frozen)
            require((directory / 'project_evidence.json').is_file(),
                    f'Missing portable project evidence: {directory}; '
                    'run collect_resumed.py --archive-project-evidence before collecting')
            config_rows.extend(parsed)
            batches.append(metrics)
            evidence.update(batch_evidence)
        config_rows.sort(key=lambda row: row['index'])
        require([row['index'] for row in config_rows] == list(range(145)),
                f'Incomplete, duplicate or unexpected original cases: {config}')
        require(sum(row['input_bytes'] for row in config_rows) == 148160 and
                sum(row['output_bytes'] for row in config_rows) == 101760,
                f'Incomplete combined suite byte totals: {config}')
        build = builds['rv32i' if config == 'rv32i' else 'rv32im']
        observed = max([row['observed_algorithm_stack_bytes'] for row in config_rows] +
                       [batch['observed_stack_bytes'] for batch in batches])
        configs.append(dict(
            config=config, cases=len(config_rows), input_bytes=148160, output_bytes=101760,
            checkpoint_cases=PREFIX_COUNTS[config], resumed_cases=145 - PREFIX_COUNTS[config],
            resumed_batch_count=len(batches), batches=batches,
            total_sim_cycles=None, all_m=None,
            whole_run_totals_note='Unavailable: the interrupted prefix has no final PASS. '
                                 'Batch totals below cover resumed batches only and include repeated boots.',
            resumed_batches_total_sim_cycles=sum(batch['total_sim_cycles'] for batch in batches),
            resumed_batches_all_m=sum(batch['all_m'] for batch in batches),
            timed_cycles=sum(row['raw_cycles'] for row in config_rows),
            timed_m=sum(row['m_total'] for row in config_rows),
            ram_bytes=build['ram_bytes'], binary_bytes=build['binary_bytes'],
            static_end=build['static_end'], stack_reserved=build['stack_reserved'],
            observed_stack_bytes=observed,
            observed_stack_coverage='Maximum observed depth across checkpoint algorithm intervals '
                                    'and complete resumed batches; not a worst-case bound.',
            observed_algorithm_stack_bytes=max(row['observed_algorithm_stack_bytes'] for row in config_rows),
            static_m_instructions=build['static_m_instructions'],
            firmware_sha256=build['firmware_sha256']))
        rows.extend(config_rows)
    by_config = {config: [row for row in rows if row['config'] == config] for config in CONFIGS}
    require(all(left['index'] == right['index'] and
                all(left[name] == right[name] for name in M_OPS + ['m_total'])
                for left, right in zip(by_config['rv32im_iterative'], by_config['rv32im_fast'])),
            'RV32IM per-case dynamic instruction mismatch')
    for path in (Path(__file__), Path(__file__).with_name('collect.py'),
                 result_dir / 'build_manifest.json', FIXTURES / 'cases.json'):
        evidence_file(evidence, path)
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
            evidence_file(evidence, path)
    summary = dict(
        scope='All 145 pinned official ML-KEM-512 public ACVP records on each of three PicoRV32 RTL configurations',
        completion_mode='Validated interrupted prefixes plus independently completed resumed batches; '
                        'no synthetic single-run PASS or full-run cycle/M totals.',
        timing='Raw rdcycle delta around operation dispatch and complete API call; seed-format '
               'decapsulation includes key expansion. Input/output mailbox traffic, startup, oracle '
               'comparison and entropy acquisition excluded. Internal zeroization included; empty '
               'bracket recorded without subtraction.',
        statistics='One retained execution per official record per CPU. Dataset revisions remain '
                   'identified; aggregate tables count records, not independent random samples. '
                   'P95 uses nearest rank (ceil(0.95*n)). Key-check valid/invalid returns are separate.',
        limitations='RTL simulation only; no board measurement, post-route timing, certification, '
                    'or proof of correctness beyond covered cases. Stack figures are observed depths, '
                    'not worst-case bounds. Prefix shutdown prevents recovering whole-run cycle/M totals.',
        acvp_commit=fixture['source']['commit'],
        mlkem_native_commit=builds['rv32i']['mlkem_native_commit'],
        compiler=builds['rv32i']['compiler'], configs=configs,
        rejection_coverage_per_config=dict(
            decapsulation_records=sum(case['op'] in (3, 4) for case in fixture['cases']),
            expected_rejection_keys=sum(expected_rejection(case) is True for case in fixture['cases']),
            method='Expected k equals FIPS 203 J(z || c) = SHAKE256(z || c, 32 bytes); '
                   'API returns 0 for these records too.'),
        aggregate=group_stats(rows, False), by_dataset=group_stats(rows, True),
        evidence_sha256=evidence)
    return summary, rows


def resumed_markdown(summary):
    # The shared table renderer expects numeric whole-run fields. Supply a display
    # view of the explicitly labelled resumed-only count; retain null in the JSON.
    display = dict(summary, configs=[dict(item, all_m=item['resumed_batches_all_m'])
                                     for item in summary['configs']])
    rendered = markdown(display)
    rendered = rendered.replace('栈预留 / 全程观测 B', '栈预留 / 已有观测最大 B')
    rendered = rendered.replace('全程 M / 算法区间 M', '续跑批次全程 M / 全部算法区间 M')
    rendered = rendered.replace('三组 CPU 各执行 145 条固定版本 ACVP 记录；',
                                '三组 CPU 各合并验证 145 条固定版本 ACVP 记录；')
    note = ('\n本次结果由关机前已验证的 25／31／38 条记录与独立完成的续跑批次合并。'
            '原始 case_index 完整且唯一；旧日志没有最终 PASS，未拼造单次全套 PASS。'
            '全程周期与 M 总数无法从原始未完成前缀恢复，summary.json 中对应字段为 null。'
            '下表“续跑批次全程 M”仅包含续跑批次（包括每批启动）；“全部算法区间 M”覆盖全部 145 条。'
            '栈列为原始算法区间及完整续跑批次中的最大观测深度。\n')
    marker = '| CPU | 固件有效 B |'
    rendered = rendered.replace(marker, note + '\n' + marker, 1)
    rendered = rendered.replace('和各配置 `run_inputs.json`。',
                                '、`checkpoint/` 与各 `batches/<config>/<batch>/run_inputs.json`。')
    return rendered


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-checkpoint', action='store_true')
    parser.add_argument('--check', action='store_true', help='validate without rewriting summaries')
    parser.add_argument('--archive-project-evidence', action='store_true',
                        help='validate and archive project provenance for successful batches')
    args = parser.parse_args()
    if args.check_checkpoint:
        validate_checkpoint()
        print('MLKEM512_CHECKPOINT_PASS rv32i=25 rv32im_iterative=31 rv32im_fast=38')
    elif args.archive_project_evidence:
        archived = archive_project_evidence()
        print('MLKEM512_PROJECT_EVIDENCE_PASS ' + ' '.join(f'{key}={value}' for key, value in archived.items()))
    else:
        summary, rows = collect()
        if not args.check:
            (RESULTS / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
            with (RESULTS / 'cases.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            (RESULTS / 'summary.md').write_text(resumed_markdown(summary), encoding='utf-8')
        print('MLKEM512_RESUMED_COLLECT_PASS configs=3 cases_per_config=145 '
              'input_bytes=148160 output_bytes=101760')
