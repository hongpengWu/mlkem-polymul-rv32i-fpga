"""Recheck saved board evidence without contacting or programming the board."""
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RELEASE = ROOT / 'release/mlkem1024_pynq'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    report_path = HERE / 'board_full_20261016.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    vectors = json.loads((RELEASE / 'kat_vectors.json').read_text(encoding='utf-8'))
    cases = report['cases']
    expected = {c['case_index']: c for c in vectors['cases']}
    check(set(expected) == set(range(145)), 'Official vector coverage')
    indices = [c['case_index'] for c in cases]
    check(len(indices) == 145 and set(indices) == set(range(145)), 'Unique board coverage')
    check(report['requested_indices'] == indices == report['checked_indices'], 'Coverage metadata')
    check(report['status'] == 'FULL_PASS' and report['passed'] and report['full_pass']
          and report['unique_checked_cases'] == 145, 'Report status')
    check(report['measurement_kind'] == 'PYNQ_BOARD_AXI_LIVE', 'Measurement kind')
    artifacts = report['artifacts']
    manifest_path = HERE / 'host_snapshot/release_manifest.json'
    check(sha(manifest_path) == artifacts['manifest_sha256'], 'Run manifest hash')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    check(manifest['files'] == artifacts['files_sha256'], 'Run file hashes')
    for name, digest in artifacts['files_sha256'].items():
        check(sha(RELEASE / name) == digest, 'Release hash: ' + name)
    for name, digest in manifest['notebook_template_sha256'].items():
        check(sha(HERE / 'host_snapshot' / name) == digest, 'Notebook template hash')
    check(sha(RELEASE / 'release_manifest.json') == manifest['working_copy_of_manifest_sha256'],
          'Parent release manifest')
    for c in cases:
        ref = expected[c['case_index']]
        for key in ('identity', 'op', 'operation', 'output_lengths', 'historical_rtl_cpu_only'):
            check(c[key] == ref[key], 'Case {} {}'.format(c['case_index'], key))
        payload = bytes.fromhex(c['output_hex'])
        check(payload == bytes.fromhex(ref['expected_hex']), 'Official output bytes')
        check(len(payload) == sum(ref['output_lengths']), 'Output lengths')
        check(hashlib.sha256(payload).hexdigest() == c['output_sha256'] == ref['expected_sha256'],
              'Output hash')
        check(c['return_code'] == ref['expected_return'], 'Official return')
        check(c['passed'] and c['trap'] == 0 and c['hardware_status'] == 0x4B415450, 'Board status')
        check(c['measurement_kind'] == 'PYNQ_BOARD_AXI_LIVE', 'Case measurement')
        hw = c['hardware']
        for key, value in ref['expected_hardware'].items():
            check(hw[key] == value, 'Hardware count: ' + key)
        raw, empty, busy = c['raw_cycles'], c['empty_cycles'], hw['busy_cycles']
        check(raw > empty > 0, 'API measurement')
        check(0 < busy < raw if hw['starts'] else busy == 0, 'Hardware busy cycles')
        profile = c['profile_words']
        check(profile[0] == 0x4B415450 and profile[1] == 0 and profile[3] == raw
              and profile[8] == empty and profile[9] == (c['return_code'] & 0xFFFFFFFF),
              'Firmware profile')
        check(c['frequency_hz'] == report['clock_hz'] == 100000000, 'Clock contract')
        check(abs(c['algorithm_seconds'] - raw / 100000000) < 1e-12, 'API time conversion')
    summary = dict(status='INDEPENDENT_FULL145_CHECK_PASS', unique_cases=145,
        evidence_sha256=sha(report_path), started_at_utc=report['started_at_utc'],
        finished_at_utc=report['finished_at_utc'], runtime=report['runtime'],
        operation_counts=dict(Counter(c['operation'] for c in cases)),
        return_code_counts=dict(Counter(str(c['return_code']) for c in cases)),
        api_cycles=sum(c['raw_cycles'] for c in cases),
        hardware_totals={key: sum(c['hardware'][key] for c in cases)
                         for key in ('starts', 'busy_cycles', 'buffer_writes', 'buffer_reads')},
        host_seconds={key: sum(c[key] for c in cases) for key in
                      ('upload_seconds', 'download_seconds', 'run_wait_seconds',
                       'verification_seconds', 'wall_seconds')},
        full_run_wall_seconds=report['total_wall_seconds'],
        board_cpu_only_comparison=False)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
