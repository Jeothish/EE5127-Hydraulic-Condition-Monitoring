import json
import random
from pathlib import Path

from sklearn.model_selection import train_test_split

SEED = 1313 ## DONT CHANGE
PER_CLASS = {100: 4, 20: 3, 3: 3} 

current_path = Path(__file__).resolve().parent
profile_path = current_path.parent/"data/condition+monitoring+of+hydraulic+systems/profile.txt"

cooler=[]
with profile_path.open() as f:
    for line in f:
        line = line.strip()
        if line:
            cooler.append(int(line.split()[0]))
 
train, test = train_test_split(range(len(cooler)), test_size=0.20, stratify=cooler,random_state=SEED)  

board_seed = random.Random(SEED)
replay=[]

for target_class, num_samples in PER_CLASS.items():
    class_indices = [idx for idx in test if cooler[idx] == target_class]
    sampled_indices = board_seed.sample(class_indices,num_samples)
    replay.extend(sampled_indices)
    
out = {
    "seed":SEED,
    "index_base": 0,
    "train": sorted(train),
    "test": sorted(test),
    "replay": sorted(replay)
}    

assert not set(train) & set(test), "Training and testing have OVERLAP"    
assert len(train) + len(test) == len(cooler), "Cycles are lost in the split"    
 
(current_path / "heldout_cycles.json").write_text(json.dumps(out,indent=1)+"\n")


print(f"Train:{len(train)} Test:{len(test)} Replay:{len(replay)}")

