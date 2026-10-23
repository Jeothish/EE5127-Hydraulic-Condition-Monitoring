import asyncio
import struct
import time
from bleak import BleakClient, BleakScanner

DEVICE_NAME = "EE5127-G013-UART"
TX_CHAR = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
RX_CHAR = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
MAGIC = b"CYCLES01"
CYCLE_SECONDS = 60

SENSORS_TO_WATCH = ("PS1","FS1","TS1","VS1","EPS1","CE","CP","SE")

class Stream:
    
    def __init__(self):
        self.buf = bytearray()
        self.run_id = 0
        self.cycles = 0
        self.rows = []
        self.values_per_cycle = 0
        self.ticks_per_cycle = 0
        self.groups = []
        self.frames = {}
        self.recent = (0,0)
        self.values = {}
        self.master = 0
        self.features = {}
        self.window = {}
        
    def feed(self,chunk):
        self.buf += chunk
        while self.buf:
            kind = self.buf[0] 
            if kind == 0x01:
                if len(self.buf) < 23:
                    return
                self.run_id = struct.unpack_from("<I",self.buf,1)[0]
                cycles,channels = struct.unpack_from("<HH",self.buf,15)
                frame_size = 23 + channels * 20 + cycles * 2
                if len(self.buf) < frame_size:
                    return
                self._header(bytes(self.buf[5:frame_size])) 
                del self.buf[:frame_size]
                
            elif kind == 0x02:
                if not self.groups:
                    raise ValueError("Data frame arrived with no header")
                if len(self.buf) < 4:
                    return
                cycle = self.buf[1]
                tick = struct.unpack_from("<H", self.buf, 2)[0]
                frame_size = 4 + 2 * self._due(tick) 
                if len(self.buf) < frame_size:
                    return
                self._data(bytes(self.buf[:frame_size]), cycle,tick)
                del self.buf[:frame_size]
            
            else:
                raise ValueError("Unknown frame type")
    
    def _header(self,block):
        if block[:8] != MAGIC:
            raise ValueError("header is not a CYCLES01 block")
        _version, self.cycles, channels , self.values_per_cycle = struct.unpack_from("<HHHI", block, 8)
        
        grouped = {}
        position = 18
        for _ in range(channels):
            raw_name, rate, _count, offset, scale = struct.unpack_from("<8sHHff", block,position) 
            name = raw_name.rstrip(b"\0").decode()
            self.values[name] = [] 
            grouped.setdefault(rate,[]).append((name,offset,scale)) 
            position += 20
            
        self.rows = list(struct.unpack_from(f"<{self.cycles}H",block,position)) 
        
        self.master = max(grouped)
        self.groups = [(rate,self.master // rate, fields) for rate, fields in grouped.items()]
        values_per_second = sum(rate * len(fields) for rate, _stride, fields in self.groups)
        self.ticks_per_cycle = int(self.master * self.values_per_cycle / values_per_second) 
    
    def _due(self,tick):
        return sum(len(fields) for _rate, stride, fields in self.groups if tick % stride == 0) 
    
    def _data(self,frame,cycle,tick):
        position = 4
        for rate,stride,fields in self.groups:
            if tick % stride:
                continue
            codes = struct.unpack_from(f"<{len(fields)}h", frame, position) 
            position += 2*len(fields) 
            
            for (name,offset,scale), code in zip(fields,codes):
                value = code*scale+offset
                self.values[name].append(value)
                if rate > 1:
                    self.window.setdefault(name,[]).append(value)
        self.frames[cycle] = self.frames.get(cycle,0) + 1
        self.recent = (cycle,tick)
        
        if tick % self.master == self.master - 1:
            self._reduce()
                    
    
    def _reduce(self):
        for name, samples in self.window.items():
            count = len(samples)
            mean = sum(samples) / count
            square_total = sum(sample * sample for sample in samples)
            rms = (square_total / count) ** 0.5
            variance = square_total / count - mean * mean
            std = variance ** 0.5 if variance > 0 else 0.0
            self.features.setdefault(name,[]).append((mean,rms,std))
        
        self.window = {}        
            
    def complete(self):
        return self.recent == (self.cycles - 1, self.ticks_per_cycle - 1)
    
def report(stream,elapsed):
    if not stream.groups:
        print("Nothing was recieved")
        return
    
    frames = sum(stream.frames.values())
    expected = stream.cycles * stream.ticks_per_cycle
    values = sum(len(v) for v in stream.values.values())
    rate = stream.groups[0][0] 
    
    print()
    print(f"Run id {stream.run_id}")
    print(f"Channels {len(stream.values)}")
    print(f"Cycles {stream.cycles} of {stream.ticks_per_cycle} ticks")
    print(f"Held-out rows {stream.rows}")
    print(f"Frames {frames} of {expected}")
    print(f"Values decoded {values} of {stream.values_per_cycle * stream.cycles}")
    print(f"Elapsed {elapsed:.2f} s")
    print(f"tick rate {frames / elapsed:.2f} Hz of {rate}")
    print()
    print("cycle frames/expected")
    for cycle in range(stream.cycles):
        print(f"{cycle:2d} {stream.frames.get(cycle, 0):5d} / {stream.ticks_per_cycle:5d}")
        
    for name, series in stream.values.items():
        if series:
            print(f" {name:<5s} {min(series):10.3f} .. {max(series):10.3f}"
                  f" {len(series):6d} values")  

def write_csvs(stream,prefix="received"):
    for rate, _stride, fields in stream.groups:
        names = [name for name, _offset, _scale in fields]
        series = [stream.values[name] for name in names]
        if not series or not series[0]:
            continue
        path = f"{prefix}_{rate}hz.csv"
        with open(path,"w") as handle:
            handle.write("t," + ",".join(names) + "\n")
            for i in range(len(series[0])):
                cells = ",".join(f"{s[i]:.3f}" for s in series)
                handle.write(f"{i / rate:.4f},{cells} \n")
        print(f"wrote {path}: {len(names)} channels, {len(series[0])} rows")        
        
def write_features(stream,prefix="features"):
    if not stream.features:
        print("No features to write")
        return
    
    names = list(stream.features)
    slow = [n for rate, _s, fields in stream.groups if rate == 1 for n, _o, _sc in fields]
    windows = len(stream.features[names[0]])
    path = f"{prefix}_1hz.csv" 
    
    with open(path,"w") as handle:
        heading = [f"{name}_{kind}" for name in names for kind in ("mean","rms","std")] + slow 
        handle.write("cycle,second," + ",".join(heading) + "\n")
        for index in range(windows):
            cells = [f"{value:.3f}" for name in names for value in stream.features[name][index]]
            cells += [f"{stream.values[n][index]:.3f}" for n in slow]
            handle.write(f"{index // CYCLE_SECONDS},{index % CYCLE_SECONDS},{','.join(cells)}\n")
             
    print(f"wrote {path}: {len(names)} channels, {windows} windows")     
            
                       
                 
        
    
async def main():
    stream = Stream()
    finished = asyncio.Event()
    
    stamped = 0.0
    
    def on_chunk(_sender,data):
        nonlocal stamped
        stream.feed(data)
        
        now = time.monotonic()
        if stream.frames and now - stamped >= 1.0:
            stamped = now
            readings = [f"{name}={stream.values[name][-1]:.1f}" for name in SENSORS_TO_WATCH if stream.values.get(name)]
            print(f"cycle {stream.recent[0] + 1}/{stream.cycles}"
                  f" tick {stream.recent[1]:5d}/ {'   '.join(readings)}")
            
        if stream.complete():
            finished.set()
    
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=15.0)
    if device is None:
        print("No device found")
        return
    
    started = time.monotonic()
    async with BleakClient(device) as client:
        print(f"Connected to {device.name} {device.address}")
        await client.start_notify(TX_CHAR,on_chunk)
        await client.write_gatt_char(RX_CHAR, b"\x00")
        
        try:
            await asyncio.wait_for(finished.wait(),timeout=900)
        except asyncio.TimeoutError:
            print("Timed out after 900s without completing")
            
       
        await client.stop_notify(TX_CHAR)
        
    report(stream, time.monotonic() - started)
    write_csvs(stream) 
    write_features(stream)

if __name__ == "__main__":
    asyncio.run(main())       