import sys
import select
import time

TIMEOUT = 0.1  # seconds

passes = {}
last_passes = {}

while True:
    ready, _, _ = select.select([sys.stdin], [], [], TIMEOUT)
    if ready:
        line = sys.stdin.readline()
        if not line:  # EOF
            break
        # read line
        detection_time, strength, transponder_id = line.strip().split(' ')
        # save
        transponder_passes = passes.get(transponder_id, [])
        transponder_passes.append((float(detection_time), float(strength)))
        passes[transponder_id] = transponder_passes
    # process saved stuff

    announced_transponders = []
    for transponder_id, detections in passes.items():
        last_time, _last_strength = detections[-1]
        if float(last_time) + 1.0 <= time.time():
            current_pass_time, _current_strength = detections[0] # first detection
            last_pass_time = last_passes.get(transponder_id, None)
            last_passes[transponder_id] = current_pass_time
            announced_transponders.append(transponder_id)
            if last_pass_time: # seen previously
                print("\a", f"{transponder_id} {current_pass_time - last_pass_time}")
            else: # fresh
                print("\a", f"{transponder_id} {0.0}")
    for transponder_id in announced_transponders:
        del passes[transponder_id]

    