from ctypes import byref, c_byte, c_int16, c_int32
from time import time, sleep
import sys

import numpy as np
from bpsk import BPSKDecoder

from picosdk.ps2000 import ps2000 as ps
from picosdk.functions import adc2mV, assert_pico2000_ok

PS2000_50MV = 2
PS2000_100MV = 3
PS2000_200MV = 4


def get_timebase(device, requested_interval):
    current_timebase = 0
    time_interval = c_int32(0)
    time_units = c_int16()
    max_samples = c_int32()

    while ps.ps2000_get_timebase(device.handle, current_timebase, 4000, byref(time_interval), byref(time_units), 1, byref(max_samples)) != 0:
        if time_interval.value == requested_interval:
            return current_timebase, max_samples.value
        if current_timebase > 65535:
            raise Exception('No appropriate timebase was identifiable')
        current_timebase += 1

    raise Exception('No appropriate timebase was identifiable')

def calc_noise(device, timebase, max_samples):
    time_indisposed_ms = c_int32()
    res = ps.ps2000_run_block(
        device.handle, 
        max_samples,
        timebase,
        1,
        byref(time_indisposed_ms)
    )
    assert_pico2000_ok(res)

    while ps.ps2000_ready(device.handle) == 0:
        sleep(0.01)
    
    times = (c_int32 * max_samples)()
    buffer_a = (c_int16 * max_samples)()
    overflow = c_byte(0)
    res = ps.ps2000_get_times_and_values(
        device.handle,
        byref(times),
        byref(buffer_a),
        None,
        None,
        None,
        byref(overflow),
        2,
        max_samples,
    )
    assert_pico2000_ok(res)
    ps.ps2000_stop(device.handle)

    channel_mv = np.array(buffer_a, dtype=np.float32)
    return np.std(channel_mv), np.mean(channel_mv)

def setup_channel(device, range=PS2000_100MV):
    print("setup channel A...", file=sys.stderr)
    res = ps.ps2000_set_channel(
        device.handle,
        0, # 0 - channel A
        True, # channel is active
        False, # AC coupling
        range
    )
    assert_pico2000_ok(res)

    print("disable channel B...", file=sys.stderr)
    res = ps.ps2000_set_channel(
        device.handle,
        1, # 0 - channel A
        False, # channel is active
        False, # AC coupling
        range
    )
    assert_pico2000_ok(res)

    # setup timebase for 25 MSPS (every 40 ns)
    timebase, max_samples = get_timebase(device, 40)
    print("timebase: ", timebase, file=sys.stderr)
    print("max samples: ", max_samples, file=sys.stderr)
    
    # determine noise floor
    print("reading a sample to measure noise floor", file=sys.stderr)
    channel_noise, channel_bias = calc_noise(device, timebase, max_samples)
    print("channel noise: ", adc2mV([channel_noise], range, c_int16(32767))[0], "mV", file=sys.stderr)
    print("channel bias: ", adc2mV([channel_bias], range, c_int16(32767))[0], "mV", file=sys.stderr)
    print("1 LSB: ", adc2mV([(2**16 / 220)], range, c_int16(32767))[0], "mV", file=sys.stderr)

    # calculate trigger point
    # the picoscope typically has better-than 1 LSB noise; putting a trigger to 3*LSB is a safe choice
    # the driver scales the 8 bit ADC to 16 bit, using a strange scaling factor (220)
    default_trigger_point = int(channel_bias + 3 * (2**16 / 220))
    # if there is a preamp, it can add noise higher than the ADC/scope inherent noise
    calculated_trigger_point = int(channel_bias + 3 * channel_noise) + (2**16 / 220) # add 1 LSB (220)
    # use the worst-case triggering mechanism:
    trigger_point = int(max(default_trigger_point, calculated_trigger_point))
    
    # set the trigger
    print("set channel A trigger to ", adc2mV([trigger_point], range, c_int16(32767))[0], "mV", "(%.2f %%)" % (100.0 * trigger_point / 32767.0), file=sys.stderr)
    res = ps.ps2000_set_trigger(
        device.handle,
        0, # source, channel A
        trigger_point,
        2, # rising
        -10, # show data starting from the triggered event
        0 # no auto trigger
    )
    assert_pico2000_ok(res)

    return timebase, trigger_point

def gather_passings(device, timebase, trigger_point, range):
    bpsk = BPSKDecoder(5_000_000, 25_000_000, 1_250_000)

    print("collect passings...", file=sys.stderr)
    while True:
        time_indisposed_ms = c_int32()
        res = ps.ps2000_run_block(
            device.handle, 
            4000,
            timebase,
            1,
            byref(time_indisposed_ms)
        )
        assert_pico2000_ok(res)

        while ps.ps2000_ready(device.handle) == 0:
            sleep(0.001)
        
        times = (c_int32 * 4000)()
        buffer_a = (c_int16 * 4000)()
        overflow = c_byte(0)
        res = ps.ps2000_get_times_and_values(
            device.handle,
            byref(times),
            byref(buffer_a),
            None,
            None,
            None,
            byref(overflow),
            2,
            4000,
        )
        assert_pico2000_ok(res)
        channel_mv = np.array(buffer_a, dtype=np.float32)
        data, rms = bpsk.decode(channel_mv, trigger_point)

        rms_mv = adc2mV([rms], range, c_int16(32767))[0]
        print("%.3f %.2f %s" % (time(), rms_mv, ''.join('{:02X}'.format(a) for a in data)), flush=True)
        if rms_mv * 2 >= 50.0 * (2 ** (range - 2)):
            print(f"overvoltage alert: {rms_mv} mV", file=sys.stderr)


np.set_printoptions(threshold=sys.maxsize)
print("opening device...", file=sys.stderr)
with ps.open_unit() as device:
    print("device opened: ", str(device.info.serial), file=sys.stderr)
    range = PS2000_200MV
    timebase, trigger_point = setup_channel(device, range)
    gather_passings(device, timebase, trigger_point, range)
