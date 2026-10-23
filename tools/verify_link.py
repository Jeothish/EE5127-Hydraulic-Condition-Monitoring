import csv
import struct
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "cycles.bin"
MAGIC = b"CYCLES01"

TOLERANCE = 0.001

def read_bin():
    raw = BIN.read_bytes()
    magic, _ver, cycles, count, per_cycle = struct.unpack_from("<8sHHHI", raw)
    if magic != MAGIC:
        raise SystemExit("cycles.bin is not a replay file")

    channels, at = [], 18
    for _ in range(count):
        name, rate, _samples, offset, scale = struct.unpack_from("<8sHHff",raw,at)
        channels.append({"name": name.rstrip(b"\0").decode(), "rate": rate,
                         "offset": offset, "scale": scale})
        at += 20
    rows = list(struct.unpack_from(f"<{cycles}H", raw, at))
    codes = array("h")
    codes.frombytes(raw[at + 2 * cycles:])
    return channels, codes, rows, cycles, per_cycle

def decode(channels, codes,cycles):
    rates = sorted({c["rate"] for c in channels}, reverse=True)
    values = {c["name"]: [] for c in channels}
    at = 0
    for _ in range(cycles):
        for rate in rates:
            members = [c for c in channels if c["rate"] == rate]
            for _ in range(rate * 60):
                for c in members:
                    values[c["name"]].append(codes[at] * c["scale"] + c["offset"])
                    at += 1
    return values

def read_csv(path):
    with path.open() as handle:
        reader= csv.reader(handle)
        names = next(reader)[1:]
        times, rows = [], []
        for line in reader:
            times.append(float(line[0]))
            rows.append([float(cell) for cell in line[1:]]) 
    return names, times, rows

def main():
    channels, codes, rows, cycles, per_cycle = read_bin()
    sent = decode(channels, codes, cycles)

    print(f"cycles.bin    {cycles} cycles, {len(channels)} channels, "
          f"{per_cycle} values/cycle, {len(codes)} decoded")
    print(f"held-out rows {rows}")
    print()

    total_corrupted = 0
    total_lost = 0
    worst = 0.0

    for rate in (100, 10, 1):
        path = ROOT / f"received_{rate}hz.csv"
        if not path.exists():
            print(f"{rate:3d} Hz    MISSING - not produced by this run")
            continue

        names, times, received = read_csv(path)
        expected = sent[names[0]]
        limit = min(len(received), len(expected))      

        corrupted = 0
        stream_worst =0.0
        for i in range(limit):
            for column, name in enumerate(names):
                error = abs(received[i][column] - sent[name][i])
                stream_worst = max(stream_worst, error)
                if error > TOLERANCE:
                    corrupted += 1

        span = times[limit - 1] - times[0] if limit > 1 else 0.0
        achieved = (limit - 1) / span if span else 0.0
        lost = len(expected) - limit

        print(f"{rate:3d} Hz    rows{limit:6d}  lost {lost:5d} "
              f"corrupted {corrupted:5d} worst {stream_worst:.6f} "
              f"rate {achieved:6.2f} Hz of {rate}")

        total_corrupted += corrupted
        total_lost += max(lost,0)
        worst = max(worst, stream_worst)

    print()
    print(f"total: {total_lost} lost, {total_corrupted} corrupted, "
              f"worst error {worst:.6f}")
    print("RESULT:", "PASS" if total_lost == 0
          and total_corrupted == 0 else "FAIL")

if __name__ == "__main__":
    main()