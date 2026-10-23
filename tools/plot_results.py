import csv 
import matplotlib.pyplot as plt

CYCLE_SECONDS = 60
CYCLES = 10

def load(path):
    with open(path) as handle:
        return list(csv.DictReader(handle))

GROUPS = [
    ("Pressure High", ["PS1","PS2"]),
    ("Pressure Low",["PS3","PS4","PS5","PS6"]),
    ("Temperature", ["TS1","TS2","TS3","TS4"]),
    ("Flow", ["FS1","FS2"]),
    ("Power", ["EPS1"]),
    ("Vibration", ["VS1"]),
    ("Cooling", ["CE","SE"]), 
]   

UNITS = { 
    "Pressure High": "Bar",
    "Pressure Low": "Bar",
    "Temperature": "\u00b0C",
    "Flow": "l/min",
    "Power": "Watts",
    "Vibration": "mm/s",
    "Cooling": "%",
}

SOURCES = {
    100: ["PS1", "PS2", "PS3", "PS4", "PS5", "PS6", "EPS1"],
    10: ["FS1", "FS2"],
    1: ["TS1", "TS2", "TS3", "TS4", "VS1", "CE", "CP", "SE"],
}

def plot_replay():
    cache = {}
    for rate in (100, 10, 1):
        rows = load(f"received_{rate}hz.csv")
        cache[rate] = (rows, [float(r["t"]) for r in rows])

    for label, names in GROUPS:
        rate = next(r for r, members in SOURCES.items() if names[0] in members)
        rows, time = cache[rate]

        figure, axis = plt.subplots(figsize=(10,3))   
        for name in names:
            axis.plot(time, [float(r[name])for r in rows], linewidth=0.6,label=name) 
        for cycle in range(1,CYCLES):
            axis.axvline(cycle * CYCLE_SECONDS, color = "grey", linewidth = 0.6, linestyle="--")
        axis.set_xlim(0, CYCLES * CYCLE_SECONDS)
        axis.set_xlabel("Time (s)")
        axis.set_ylabel(UNITS[label])
        axis.set_title(f"{label.replace('_',' ')} ({rate} Hz)")
        axis.grid(True,alpha=0.3)
        axis.legend(loc="upper right", fontsize=8,ncol=min(len(names), 4))
        figure.tight_layout()
        figure.savefig(f"fig_{label}.png", dpi=200) 

def plot_features(channel="PS1", cycle=0, rate=100):
    raw = load(f"received_{rate}hz.csv")
    feat = load("features_1hz.csv")

    start = cycle * CYCLE_SECONDS
    raw_rows = raw[start * rate:(start + CYCLE_SECONDS) * rate]
    t_raw = [float(r["t"]) - start for r in raw_rows]
    y_raw = [float(r[channel]) for r in raw_rows]

    feat_rows = feat[start:start + CYCLE_SECONDS]
    t_feat = [i + 0.5 for i in range(len(feat_rows))]
    mean = [float(r[f"{channel}_mean"]) for r in feat_rows]
    std = [float(r[f"{channel}_std"]) for r in feat_rows]

    figure, axis = plt.subplots(figsize=(10,4))
    axis.plot(t_raw, y_raw,linewidth=0.5, label=f"raw, {rate} Hz")
    axis.plot(t_feat, mean, "o-", color="C1",markersize=3, label="1 s mean")
    axis.fill_between(t_feat,
                      [m - s for m, s in zip(mean,std)],
                      [m + s for m, s in zip(mean,std)],
                      color="C1",alpha=0.3,label="mean ± 1 std")
    axis.set_xlabel("Time (s)")
    axis.set_ylabel(channel)
    axis.legend()
    axis.grid(True, alpha=0.3)
    figure.tight_layout()
    figure.savefig(f"fig_features_{channel}.png",dpi=200)

if __name__ == "__main__":
    plot_replay()
    plot_features("PS1")
    plt.show()               