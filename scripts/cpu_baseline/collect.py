"""Parse CPU baseline logs into report-ready CSV/JSON without remeasuring."""
from pathlib import Path
import csv, json, re, statistics

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ['rv32i', 'rv32im_iterative', 'rv32im_fast']
HEADER = ['case','mode','cpu_mul','cpu_fast_mul','cpu_div','expect_m','prepare','ntt_a','ntt_b',
          'basemul','invntt','canonical','total','empty','m_total','mul','mulh','mulhsu',
          'mulhu','div','divu','rem','remu','min_sp','checksum']
PARAMETERS = {'rv32i': (0, 0, 0, 0), 'rv32im_iterative': (1, 0, 1, 1),
              'rv32im_fast': (1, 1, 1, 1)}
PHASES = ['prepare', 'ntt_a', 'ntt_b', 'basemul', 'invntt', 'canonical']
M_OPS = ['mul', 'mulh', 'mulhsu', 'mulhu', 'div', 'divu', 'rem', 'remu']


def parse_log(config, log):
    """Validate a complete run before permitting any derived file writes."""
    def require(condition, detail):
        if not condition:
            raise ValueError(f'{config}: {detail}')

    require(config in PARAMETERS, 'unknown configuration')
    require(not re.search(r'CPU_BASELINE_FAIL\b|\bFATAL\s*:|\$fatal\b|\bERROR\s*:',
                          log, re.IGNORECASE), 'log contains a failure or tool error')
    lines = log.splitlines()
    headers = [line for line in lines if line.startswith('CPU_BENCH_HEADER,')]
    require(headers == ['CPU_BENCH_HEADER,' + ','.join(HEADER)],
            'missing, duplicate or unexpected CSV header')
    passes = [line for line in lines if line.startswith('CPU_BASELINE_PASS')]
    require(len(passes) == 1, 'expected exactly one PASS record')
    pass_match = re.fullmatch(
        r'CPU_BASELINE_PASS cases=(\d+) checks=(\d+) mul=(\d+) fast_mul=(\d+) '
        r'div=(\d+) expect_m=(\d+) cycles=(\d+) m_total=(\d+) '
        r'min_sp=(0x[0-9a-fA-F]+) stack_used=(\d+)', passes[0])
    require(pass_match is not None, 'malformed PASS record')
    pass_values = [int(value, 16 if index == 8 else 10)
                   for index, value in enumerate(pass_match.groups())]
    require(pass_values[:2] == [8, 4096], 'PASS has incorrect case/result counts')
    require(tuple(pass_values[2:6]) == PARAMETERS[config],
            'PASS CPU parameters do not match its configuration directory')
    require(pass_values[6] > 0, 'PASS has invalid execution cycles')
    require(0x37f0 <= pass_values[8] <= 0x3ff0 and
            pass_values[9] == 0x3ff0 - pass_values[8], 'PASS has invalid stack data')

    rows, seen = [], set()
    for line in lines:
        if not line.startswith('CPU_BENCH_ROW,'):
            continue
        values = next(csv.reader([line]))[1:]
        require(len(values) == len(HEADER), 'incorrect CSV row width')
        item = dict(zip(HEADER, values))
        item['config'] = config
        try:
            numbers = {key: int(item[key], 16 if key in ('min_sp', 'checksum') else 10)
                       for key in HEADER if key != 'mode'}
        except ValueError as error:
            raise ValueError(f'{config}: nonnumeric CSV field') from error
        key = (numbers['case'], item['mode'])
        require(key[0] in range(8) and key[1] in ('unsegmented', 'profiled'),
                f'invalid case/mode {key}')
        require(key not in seen, f'duplicate case/mode {key}')
        seen.add(key)
        require(tuple(numbers[name] for name in ('cpu_mul', 'cpu_fast_mul', 'cpu_div',
                                                'expect_m')) == PARAMETERS[config],
                f'{key}: row CPU parameters do not match configuration')
        require(all(numbers[name] >= 0 for name in M_OPS) and
                numbers['m_total'] == sum(numbers[name] for name in M_OPS),
                f'{key}: invalid M instruction counts')
        require((numbers['m_total'] == 0) if config == 'rv32i'
                else (numbers['mul'] > 0), f'{key}: incorrect M instruction expectation')
        require(0 < numbers['empty'] < numbers['total'] < 2**32,
                f'{key}: invalid timing bracket')
        if key[1] == 'profiled':
            require(all(numbers[name] > 0 for name in PHASES) and
                    sum(numbers[name] for name in PHASES) == numbers['total'],
                    f'{key}: phase sum does not equal total')
        else:
            require(all(numbers[name] == -1 for name in PHASES),
                    f'{key}: unsegmented phases must be unsampled')
        require(pass_values[8] <= numbers['min_sp'] <= 0x3ff0 and
                0 <= numbers['checksum'] < 2**32, f'{key}: invalid stack/checksum data')
        rows.append(item)

    require(seen == {(case, mode) for case in range(8)
                     for mode in ('unsegmented', 'profiled')}, 'incomplete 8 x 2 result set')
    require(sum(int(row['m_total']) for row in rows) == pass_values[7],
            'PASS M total differs from algorithm windows')
    require(len({int(row['empty']) for row in rows}) == 1, 'empty bracket changed')
    for case in range(8):
        require(len({int(row['checksum'], 16) for row in rows
                     if int(row['case']) == case}) == 1,
                f'case {case}: checksums differ between timing modes')
    return rows, passes[0]

def main():
    out = ROOT/'results/cpu_baseline'
    rows, pass_lines = [], {}
    for config in CONFIGS:
        log = (out/config/'simulate.log').read_text(encoding='utf-8-sig')
        config_rows, pass_lines[config] = parse_log(config, log)
        rows.extend(config_rows)
    for config in CONFIGS:
        (out/config/'PASS.txt').write_text(pass_lines[config]+'\n', encoding='ascii')
    with (out/'cpu_benchmark_rows.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['config']+HEADER); writer.writeheader(); writer.writerows(rows)
    summary = []
    for config in CONFIGS:
        un = [x for x in rows if x['config']==config and x['mode']=='unsegmented']
        prof = [x for x in rows if x['config']==config and x['mode']=='profiled']
        totals = [int(x['total']) for x in un]
        prof_totals = [int(x['total']) for x in prof]
        phases = {name: [int(x[name]) for x in prof] for name in ['prepare','ntt_a','ntt_b','basemul','invntt','canonical']}
        summary.append(dict(config=config, cases=len(un), raw_total_min=min(totals),
            raw_total_mean=statistics.mean(totals), raw_total_max=max(totals),
            profiled_total_min=min(prof_totals), profiled_total_mean=statistics.mean(prof_totals),
            profiled_total_max=max(prof_totals), empty_cycles=sorted({int(x['empty']) for x in un}),
            phase_means={k: statistics.mean(v) for k,v in phases.items()},
            m_instructions_per_window=sorted({int(x['m_total']) for x in prof}),
            mul_per_window=sorted({int(x['mul']) for x in prof}),
            min_sp=sorted({x['min_sp'] for x in prof}),
            pass_line=(out/config/'PASS.txt').read_text(encoding='ascii').strip()))
    (out/'cpu_benchmark_summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    print('CPU_BASELINE_MEASUREMENTS_PASS configs=3 rows=48 output=results/cpu_baseline')
    for x in summary:
        print(f"CPU_BASELINE_SUMMARY config={x['config']} raw_mean={x['raw_total_mean']:.1f} "
              f"profiled_mean={x['profiled_total_mean']:.1f} m={x['m_instructions_per_window']}")

if __name__ == '__main__':
    main()
