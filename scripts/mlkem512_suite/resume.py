"""Resume only missing ML-KEM-512 cases; preserve each independently passed batch."""
from pathlib import Path
import argparse
import concurrent.futures
import copy
import datetime
import json
import subprocess
import sys

from collect import ROOT, RESULTS, CONFIGS, sha, payload_bytes, require
from collect_resumed import validate_checkpoint, validate_batch

sys.path.insert(0, str(ROOT / 'scripts/kat'))
from package_mlkem512 import pack_fixture, verify_roundtrip


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def prepare(fixture, prefixes, batch_size):
    """Reuse the existing partition; never repartition completed evidence."""
    jobs = []
    for config in CONFIGS:
        first = len(prefixes[config])
        config_dir = RESULTS / 'batches' / config
        existing = sorted(config_dir.glob('batch_*/batch.json'))
        if existing:
            indices = []
            for path in existing:
                metadata = json.loads(path.read_text(encoding='utf-8'))
                require(metadata['config'] == config, f'Wrong config: {path}')
                indices.extend(metadata['original_indices'])
                jobs.append(path.parent)
            require(indices == list(range(first, 145)), f'Incomplete/overlapping batch plan: {config}')
            continue
        for start in range(first, 145, batch_size):
            original_indices = list(range(start, min(start + batch_size, 145)))
            batch_dir = config_dir / f'batch_{start:03d}_{original_indices[-1]:03d}'
            batch_dir.mkdir(parents=True, exist_ok=True)
            cases = [copy.deepcopy(fixture['cases'][index]) for index in original_indices]
            for local, case in enumerate(cases):
                case['case_index'] = local
            lengths = {}
            for expected, name, key in ((False, 'mlkem512_input.mem', 'input_words'),
                                        (True, 'mlkem512_expected.mem', 'expected_words')):
                words = pack_fixture(cases, expected)
                path = batch_dir / name
                path.write_text(''.join(f'{word:08x}\n' for word in words), encoding='ascii', newline='\n')
                verify_roundtrip(path, cases, expected)
                lengths[key] = len(words)
            write_json(batch_dir / 'batch.json', dict(
                schema_version=1, config=config, original_indices=original_indices,
                case_count=len(cases), **lengths,
                input_bytes=sum(payload_bytes(case, 'input') for case in cases),
                output_bytes=sum(payload_bytes(case, 'output') for case in cases)))
            jobs.append(batch_dir)
    # Interleave configurations, so one configuration cannot monopolize workers.
    return sorted(jobs, key=lambda p: (int(p.name.split('_')[1]), p.parent.name))


def run_batch(batch_dir, vivado, fixture, builds, original_hashes):
    metadata = json.loads((batch_dir / 'batch.json').read_text(encoding='utf-8'))
    config = metadata['config']
    project = ROOT / 'build/mlkem512_suite/batches' / config / batch_dir.name
    project.mkdir(parents=True, exist_ok=True)
    input_names = (
        'rtl/cpu/picorv32.v', 'rtl/benchmark/cpu_benchmark_system.v',
        'tb/software/tb_mlkem512_suite.sv', 'scripts/mlkem512_suite/run_batch.tcl',
        'scripts/mlkem512_suite/sim.tcl', 'scripts/mlkem512_suite/resume.py',
        'scripts/kat/package_mlkem512.py',
        'results/official_baseline/mlkem512/build_manifest.json')
    inputs = [ROOT / name for name in input_names]
    inputs += sorted((ROOT / 'tb/software/mlkem512_suite').glob('*'))
    inputs += sorted((ROOT / 'firmware/images/mlkem512_suite').glob('*.mem'))
    inputs += [batch_dir / name for name in ('batch.json', 'mlkem512_input.mem', 'mlkem512_expected.mem')]
    hashes = {path.relative_to(ROOT).as_posix(): sha(path) for path in inputs if path.is_file()}
    command = [str(vivado), '-mode', 'batch', '-source', str(ROOT / 'scripts/mlkem512_suite/run_batch.tcl'),
               '-log', str(project / 'vivado.log'), '-journal', str(project / 'vivado.jou'),
               '-tclargs', config, str(batch_dir), str(project), str(metadata['case_count'])]
    write_json(batch_dir / 'run_inputs.json', dict(
        config=config, simulator='Vivado/XSim 2024.2', ram_bytes=65536,
        command=command, input_sha256=hashes,
        started_at=datetime.datetime.now().astimezone().isoformat()))
    print(f'START {config}/{batch_dir.name} cases={metadata["case_count"]}', flush=True)
    with (batch_dir / 'console.txt').open('w', encoding='utf-8') as stream:
        code = subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT).returncode
    require(code == 0, f'Vivado failed ({code}): {batch_dir / "console.txt"}')
    for name, wanted in hashes.items():
        require(sha(ROOT / name) == wanted, f'Input changed during batch: {name}')
    success = batch_dir / 'success.json'
    write_json(success, dict(status='passed', config=config, case_count=metadata['case_count'],
                            batch_sha256=sha(batch_dir / 'batch.json'),
                            log_sha256=sha(batch_dir / 'simulate.log'),
                            run_inputs_sha256=sha(batch_dir / 'run_inputs.json'),
                            finished_at=datetime.datetime.now().astimezone().isoformat()))
    try:
        validate_batch(batch_dir, fixture, builds, original_hashes)
    except Exception:
        success.unlink(missing_ok=True)
        raise
    print(f'PASS {config}/{batch_dir.name} cases={metadata["case_count"]}', flush=True)
    return metadata['case_count']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vivado', type=Path, default=Path('E:/Xilinx/Vivado/2024.2/bin/vivado.bat'))
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--max-batches', type=int, help='Run at most this many pending batches')
    parser.add_argument('--stop-file', type=Path, default=ROOT / 'build/mlkem512_suite/STOP')
    args = parser.parse_args()
    require(1 <= args.workers <= 8 and 1 <= args.batch_size <= 145, 'Invalid worker/batch size')
    fixture, builds, prefixes, _, original_hashes = validate_checkpoint()
    jobs = prepare(fixture, prefixes, args.batch_size)
    pending = []
    for batch_dir in jobs:
        if (batch_dir / 'success.json').exists():
            validate_batch(batch_dir, fixture, builds, original_hashes)
        else:
            pending.append(batch_dir)
    print(f'RESUME saved_prefix={sum(map(len, prefixes.values()))} passed_batches={len(jobs)-len(pending)} '
          f'pending_batches={len(pending)} workers={args.workers}', flush=True)
    if args.prepare_only:
        return
    require(args.vivado.is_file(), f'Vivado not found: {args.vivado}')
    if args.max_batches is not None:
        require(args.max_batches > 0, 'max-batches must be positive')
        pending = pending[:args.max_batches]
    iterator = iter(pending)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        active = {}
        def submit_one():
            if args.stop_file.exists():
                return
            batch = next(iterator, None)
            if batch is not None:
                active[pool.submit(run_batch, batch, args.vivado, fixture, builds, original_hashes)] = batch
        for _ in range(args.workers):
            submit_one()
        while active:
            done, _ = concurrent.futures.wait(active, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                active.pop(future)
                future.result()
            for _ in done:
                submit_one()
    print('RESUME_STOPPED' if args.stop_file.exists() else 'RESUME_SELECTED_BATCHES_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
