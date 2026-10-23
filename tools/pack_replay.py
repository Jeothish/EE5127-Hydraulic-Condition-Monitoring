from array import array
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "cycles.bin"
DATA = ROOT / "data" / "condition+monitoring+of+hydraulic+systems"
ROWS = json.loads((ROOT / "tools" / "heldout_cycles.json").read_text())["replay"]

if len(set(ROWS)) != len(ROWS):
    raise SystemExit("the repaly list contains duplicates")

CHANNELS = (
    ("PS1", 100), ("PS2", 100), ("PS3", 100), ("PS4", 100),
    ("PS5", 100), ("PS6", 100), ("EPS1", 100),
    ("FS1", 10), ("FS2", 10),
    ("TS1", 1), ("TS2", 1), ("TS3", 1), ("TS4", 1),
    ("VS1", 1), ("CE", 1), ("CP", 1), ("SE", 1),
)

SAMPLES = [(name,sampling_rate,sampling_rate * 60) for name,sampling_rate in CHANNELS]
PER_CYCLE = sum(count for _, _, count in SAMPLES)
LOW, HIGH = -32768, 32767

RATES = []
for _name, rate, _count in SAMPLES:
    if rate not in RATES:
        RATES.append(rate)

GROUPS = []
for rate in RATES:
    members = []
    for index in range(len(SAMPLES)):
        if SAMPLES[index][1] == rate:
            members.append(index)
    GROUPS.append((rate, members))


def load_rows():
    wanted, last = set(ROWS),max(ROWS)
    columns = []
    for name, _sampling_rate, count in SAMPLES:
        found = {}
        with (DATA / f"{name}.txt").open() as handle:
            for index, line in enumerate(handle):
                if index in wanted:
                    found[index] = [float(token) for token in line.split()]
                    if len(found[index]) != count:
                        raise SystemExit(f"{name}.txt row {index}: wrong width")
                if index >= last:
                    break
            if len(found) != len(wanted):
                raise SystemExit(f"{name}.txt: replay rows missing in this file")
            columns.append([found[row] for row in ROWS])
    return columns
        
        
def choose_encoding(values):
    low,high = min(values),max(values)
    middle =(low+high) / 2
    
    if high == low:
        return middle,1.0,True
    
    for power in range(4):
        step = 1 / (10 ** power)
        offset = round(middle / step) * step
        
        codes = []
        exact = True
        for value in values:
            code = (value-offset) / step
            codes.append(code)
            if abs(code-round(code)) > 1e-6:
                exact = False   
        if exact and min(codes) >= LOW and max(codes) <= HIGH:
            return offset,step, True
        
    scale = (high-low) / 65532
    return middle, scale, False


def main():
    columns = load_rows()
    encodings=[]
    for column in columns:
        all_values = []
        for cycle in column:
            for value in cycle:
                all_values.append(value)  
        encodings.append(choose_encoding(all_values))

    samples = array("h")
    worst = 0.0

    for cycle in range(len(ROWS)):
        for rate, members in GROUPS:
            for tick in range(rate * 60):
                for channel in members:
                    offset, scale, _exact = encodings[channel]
                    value = columns[channel][cycle][tick]
                    code = round((value - offset) / scale)
                    if code < LOW or code > HIGH:
                        raise SystemExit(
                            f"{SAMPLES[channel][0]}: {value} falls outside int16")
                    error = abs(code * scale + offset - value)
                    if error > worst:
                        worst = error
                    samples.append(code)   
    
    expected = len(ROWS) * PER_CYCLE
    if len(samples) != expected:
        raise SystemExit(f"encoded {len(samples)} values, expected {expected}")

    for position, channel in enumerate(GROUPS[0][1]):
        offset, scale, _exact = encodings[channel]
        code = round((columns[channel][0][0] - offset) / scale)
        if samples[position] != code:
            raise SystemExit(f"layout check failed for {SAMPLES[channel][0]}")

    header = struct.pack("<8sHHHI", b"CYCLES01", 1, len(ROWS), len(SAMPLES), PER_CYCLE)
    
    for index in range(len(SAMPLES)):
        name,sampling_rate,count = SAMPLES[index]
        offset, scale, exact = encodings[index]
        header += struct.pack("<8sHHff", name.encode(), sampling_rate, count, offset, scale)
        
    header += struct.pack(f"<{len(ROWS)}H", *ROWS)
    OUTPUT_FILE.write_bytes(header + samples.tobytes())
    
    print(f"{'channel':<8}{'rate':>8}{'per cycle':>11}{'offset':>12}{'scale':>14}  encoding")
    for index in range(len(SAMPLES)):
        name, rate, count = SAMPLES[index]
        offset, scale, exact = encodings[index]
        label = "exact" if exact else "lossy"
        print(f"{name:<8}{str(rate) + 'Hz':>8}{count:>11}{offset:>12.3f}{scale:>14.8f}  {label}")
        
    print(f"worst round-trip error: {worst}")    
             
    
if __name__ == "__main__":
    main()    