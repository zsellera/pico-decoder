from scipy import signal
import numpy as np

class BPSKDecoder:
    def __init__(self, carrier, fs, symbol_rate):
        self.carrier = carrier
        self.fs = fs
        self.symbol_rate = symbol_rate
        self.cycles_per_symbol = int(self.carrier / self.symbol_rate)
        self.samples_per_cycle = int(self.fs / self.carrier)

        self.lpf = signal.firwin(9, (self.carrier - 3 * self.symbol_rate, self.carrier + 3 * self.symbol_rate), fs=self.fs, pass_zero='bandpass')

        t = np.arange(0, self.samples_per_cycle)
        self.lo_i = np.cos(2.0 * np.pi * t / self.samples_per_cycle)
        self.lo_q = np.sin(2.0 * np.pi * t / self.samples_per_cycle)

    def decode(self, buffer, trigger_point):
        received, rms = self.segment_transmission(buffer, trigger_point)
        iq = self.iq_downconvert(received)
        iq_downsampled = self.downsample(iq)
        iq_stabilized = self.fine_tune(iq_downsampled)
        bytestream = self.demodulate(iq_stabilized)

        return bytestream, rms
    
    def segment_transmission(self, buffer, trigger_point):
        # LPF:
        voltages = np.convolve(buffer, self.lpf, 'valid')
        
        # Segment:
        received_power = voltages ** 2
        active_rx_idxs = np.argwhere(received_power > (trigger_point ** 2))
        start_idx = active_rx_idxs[0][0]
        stop_idx = active_rx_idxs[-1][0]
        received = voltages[start_idx:stop_idx]

        # AGC:
        rms = np.sqrt(np.mean(received_power[start_idx:stop_idx]))
        received = received * (1.0 / (rms * 1.41))

        return received, rms
    
    def iq_downconvert(self, received):
        # align to sample
        received_cycle_count = int(len(received) / self.samples_per_cycle)
        received2 = received[:(received_cycle_count * self.samples_per_cycle)].reshape((received_cycle_count, self.samples_per_cycle))
        
        # downconvert
        i0 = np.dot(received2, self.lo_i) / (self.samples_per_cycle / 2.0)
        q0 = np.dot(received2, self.lo_q) / (self.samples_per_cycle / 2.0)
        return (i0 + 1j*q0)
    
    def downsample(self, iq):
        # align
        symbols_received = int(len(iq) / self.cycles_per_symbol)
        iq = iq[:(symbols_received * self.cycles_per_symbol)]

        # find optimal sampling point
        symbols = iq.reshape((symbols_received, self.cycles_per_symbol))
        sampling_point = np.argmax(np.mean(np.abs(symbols), axis=0))

        # downsample
        iq_downsampled = iq[sampling_point::self.cycles_per_symbol]

        return iq_downsampled
    
    def fine_tune(self, iq):
        iq2 = iq * iq
        iq2m = np.mean(iq2)
        phase = np.angle(iq2m) / 2.0
        iq_stab = iq * np.exp(-1j*phase)

        return iq_stab

    def demodulate(self, iq):
        demod = iq.real > 0.0 # BPSK demod
        data = np.logical_xor(demod[1:], demod[:-1]) # reverse differential encoding
        data = data[1:]

        bits_received = len(data)
        bytes_received = int(np.ceil(bits_received / 8.0))

        data = np.pad(data, (0, bytes_received * 8 - bits_received))
        decoded = data.reshape((bytes_received, 8)).dot([128,64,32,16,8,4,2,1])
        
        return decoded



