import struct
import time

from adafruit_ble import BLERadio
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.nordic import UARTService

DEVICE_NAME = "EE5127-G013-UART"
DATASET = "/cycles.bin"
TICK_HZ = 100
CYCLE_SECONDS = 60

ble = BLERadio()
ble.name = DEVICE_NAME
uart = UARTService()
advertisement = ProvideServicesAdvertisement(uart)

def read_header():
    
    with open(DATASET,"rb") as handle:
        head = handle.read(18)
        if head[:8] != b"CYCLES01":
            raise ValueError("cycles.bin is not a CYCLES01 file")
        version, cycles, channels, values = struct.unpack_from("<HHHI",head,8)
        header = head + handle.read(channels * 20 + cycles * 2)
        
    print("version", version, "cycles", cycles,"channels", channels, "values/cycle", values)
    return header, cycles , channels, values

def build_groups(header,channels):
    groups = []
    position = 18
    for _ in range(channels):
        name , rate , _count, _offset, _scale = struct.unpack_from("<8sHHff",header,position)
        if not groups or groups[-1][0] != rate:
            groups.append((rate,TICK_HZ // rate, []))
        groups[-1][2].append(name.rstrip(b"\0").decode())    
        position += 20
    return groups   
    
def main():
    header,cycles, channels, values_per_cycle = read_header()
    groups = build_groups(header, channels)
        
    header_size = len(header)
    cycle_bytes = values_per_cycle * 2
        
    for rate, stride, names in groups:
        print(" group", rate, "Hz, every", stride, "tick(s):"," ".join(names))
        
    handles = [open(DATASET, "rb") for _ in groups]
        
    while True:
        ble.stop_advertising()
        ble.start_advertising(advertisement) 
        print("Advertising as", ble.name, "waiting for a central....")   
            
        while not ble.connected:
            time.sleep(0.1)
        ble.stop_advertising()
        print("Central connected")
        
        while not uart.read(1):
            time.sleep(0.05)
            
        run_id = int(time.monotonic() * 1000) & 0xFFFFFFFF
        uart.write(b"\x01" + struct.pack("<I", run_id) + header)
                
        for cycle in range(cycles):
            position = header_size + cycle * cycle_bytes
            for index in range(len(groups)):
                rate, _stride, names = groups[index]
                handles[index].seek(position)
                position += rate * CYCLE_SECONDS * len(names) * 2
                    
            start = time.monotonic()
            for tick in range(TICK_HZ * CYCLE_SECONDS):
                frame = bytearray(b"\x02")
                frame.append(cycle)
                frame += struct.pack("<H", tick)
                    
                for index in range(len(groups)):
                    _rate, stride, names = groups[index]
                    if tick % stride == 0:
                        frame += handles[index].read(len(names) * 2)
                     
                try:
                    uart.write(frame)
                except (OSError, RuntimeError):
                    break
                    
                deadline = start + (tick + 1) / TICK_HZ
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
                        
            print("cycle", cycle , "took", round(time.monotonic() - start, 2), "s")
                
            if not ble.connected :
                break
                
        print("replay complete" if ble.connected else "connection lost")            
                          
main()                       