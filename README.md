# PicoDecoder

AMB/RC3-compatible decoder using a `PicoScope 2204A`, a USB-based, inexpensive 8-bit oscilloscope. Using this project, you can create a lap timer for your track for about 200 EUR.

The detection antenna is connected to the AC-coupled input of the oscilloscope. The oscilloscope triggers on the detected wafeforms, and transfers them through USB for PC-based decoding. The BPSK demodulation happens on the raw waveform in software. There are separate scripts for each further processing steps (decoding RC3 protocol, recording passes).

Consider this project as a proof-of-concept rather than a fully-fledged alternative to other decoders.

## Quickstart

You need to install the oscilloscope's [PicoSDK](https://www.picotech.com/library/our-oscilloscope-software-development-kit-sdk#sdk_dl) first, available from the manufacturer. It is compatible with x86/x86-64 Linux, Windows and MacOS. There is no support of ARM64 architectures yet (MacOS needs Rosetta, Raspberry PI is not supported).

```
pip install picosdk numpy scipy
python3 detector.py | python3 decoder.py | python3 passes.py 
```

You might have to make the SDK available for dynamic loading:
```
export DYLD_LIBRARY_PATH=/Library/Frameworks/PicoSDK.framework/Libraries/libpicoipp/:Library/Frameworks/PicoSDK.framework/Libraries/libps2000/
```

Mac M1/M2/etc users should download the x86-64 binaries, and use [miniconda](https://www.anaconda.com/docs/getting-started/miniconda/install#macos-2) for installing an x86-64 version of Python3, as described on [this stackoverflow thread](https://stackoverflow.com/a/75827006).

## Software

The project contains separate scripts for specific tasks.

### detector.py

PHY-level decoding. Opens the PicoScope and reads a full memory worth of samples (8k) to determine noise floor and potential 0-point bias. Using the data, it sets a positive edge trigger to 3-sigma of the noise, but at least to 3*LSB. On trigger, it reads the sample memory, and does the BPSK decoding.

Output of `python3 detector.py`:
```
opening device...
device opened:  b'CW350/492'
setup channel A...
disable channel B...
timebase:  2
max samples:  8064
reading a sample to measure noise floor
channel noise:  0.264731 mV
channel bias:  -0.14253098 mV
1 LSB:  1.8182373063808654 mV
set channel A trigger to  5.3102206488235115 mV (2.66 %)
collect passings...
1758530782.240 12.36 07E055BA5D139B6CE541AEA2931A5A880000
1758530782.245 14.28 007916E111CD16CBC9A21070C00020
1758530782.249 14.68 07E055845D37845F4A35D68511093E300000
1758530782.253 15.16 007916E111CD16CBC9A21070C00020
1758530782.257 15.48 07E055E9526E44D164D9AC43D6B95D100000
1758530782.261 15.75 07E055CBBE95729D07B98C45EF56B9280000
1758530782.265 16.49 007916E111CD16CBC9A21070C00020
...
```

All the debug info goes to stderr, while the received data goes to stdout. The snippet shows data decoded from an RC4-hybrid transponder. The periodic `007916...` samples are the RC3 packets in the RC4-hybrid data stream.

```
<timestamp> <rms voltage> <raw data>
1758530782.245 14.28 007916E111CD16CBC9A21070C00020
```

There is a `range = PS2000_200MV` line somewhere setting the oscilloscope measuring range. `PS2000_200MV` works fine for under-the-track antenna and proper transponder placement (B-field perpendicular to the loop, see [#Hardware] section below). Overhead antennas require `PS2000_50MV`, and might benefit from a preamp as well.

Note, due to limitations of the hardware (USB2, polling-based datatransfer), we can capture ca 250-300 samples per second only (best-case). The transponder is sending ca 650 tx/s.

### decoder.py

Reads messages from `detector.py`, and decodes the RC3 messages from it.
1. finds `0x7916` preamble in the first 4 octetts of the bpsk stream
2. decodes the payload using a naive algorithm (no viterbi)
3. prints each detected transmission

Output of `python3 detector.py | python3 decoder.py`:
```
<timestamp> <rms voltage> <transponder id>
1758530782.245 14.28 3616557
1758530782.253 15.16 3616557
1758530782.265 16.49 3616557
```

#### RC4 support

It's not supported, and it's not a priority to support it. The RC4 protocol is deliberately obfuscated to hinder its' decoding. I think our efforts - as the open source RC community - should not be wasted on decyphering it, but to make it a thing of the past. We should come up with open transponder protocols that make sense. Modern, highly available manufacturing makes it easy even for a solo maker to produce small batches of transponders at very reasonable prices. With and SDR- or PicoScope based decoders, any track and community could afford to have lap counters, and finally true innovation could happen, like:
* passing speed detection using signal strength or doppler effect
* sector times (multiple detectors)

### passes.py

The output of `decoder.py` is still one line per received packet. This tool uses the first detection per lap to calculate laptimes.

Output of `python3 detector.py | python3 decoder.py | python3 passes.py`:
```
<transponder id> <laptime>
3616557 0
3616557 17.2
3616557 17.6
3616557 17.1
```

Note, it also prints a bell (`\a`) at the beginning of each line.
Also note, it's using the `select` system call. According to some, it might run into throubles on Windows.

## Hardware

The transponders are using a BPSK-modulated stream at 1.25 MHz symbol rate on a 5 MHz carrier. A transmission contains an initialization sequence, a preamble and the actual payload. The total lenght of a message is about 100 us. The transmissions are repeating on average of 1.5 ms, with a random jitter added.

### Antenna (aka the loop)

There is a widespread misunderstanding in the RC community, so I'd like to clarify this first.

For our ourpose, it is not a loop or the inductor of a resonant circuit. This is a **parallel wire transmission line**, a special form of **waveguide**. Disturbances in the magnetic field perpedicular to the plane of the wires (the transponder's signal) will travel towards *both ends* of the structure in the form of electromagnetic waves. As electrons start moving in the conductors (resulting in AC current), they create an electic field between the wires. This E-field create voltage difference. There is a ratio between the voltage created and electrons moved (current), and this ratio is specific to the geometry of the structure (the distance between the wires). It is called **characteristic impedance**, and is measured in Ohms, similarly to resistance.

The antenna has two ends: the far end is *terminated*, while the other end passes the signal eventually to the oscilloscope. As the electromagnetic waves reach the far end of the loop, they can not travel any further. If we connect the wires together (forming a loop) or leave the ends open (leaving them flapping in the wind), the wave *must* reflects, and travel towards the receiver. At the receiver, the reflected wave is added to the incident wave, potentially cancelling it. To avoid this, we must terminate the line on the far end. Remember, by the end of the day, there is a current wave and a voltage wave. If we place a resistor between the wires, with a value "carefully chosen" to match the volage/current ratio (the characteristic impedance), there will be practically no reflection. We terminated the transmission line.

The characteristic impedance is [geometry-dependant](https://learnemc.com/ext/calculators/transmission_line/wirepair.html). The wider the wires separation is, the larger the characteristic impedance is. The larger the surface (wire diameneter), the lower the impedance is. While not ideal, some reflection is tolerable, you don't need to be super-exact. For practical purposes (see later), I suggest using around **18 AWG (1 mm diameter) multi-stranded copper wire, 680/750 Ohm resistor and 20 cm spacing**.

### Impedance transformer (BalUn)

We discussed an impedance mismatch at the far end of the antenna. There is an other one at the receiver end, which we should to overcome. Actually, there are two problems:
1. The parallel wire transmission line has a characteristic impedance around 700 Ohm, while most measurement-purposed coaxial cables have around 50 Ohms. This is quite a mismatch.
2. Ideally we'd like to have the wires floating relative to the electric ground. The shield of the coaxial cable is ground-referenced though. It's connected to the shield of the USB cable, which is connected to the earthing at the PC end.

To solve both of these problems, we have to place an impedance transformer between the parallel wires and the coaxial cable. Ideally this should have a 14:1 ratio, but such ratio must be custom made. Other, 1:9 transformers are widely available though, thanks to the HAM community. These transformers are called "baluns", as they also act between a balanced (parallel wire) line and an unbalanced line (coaxial cable). While 1:9 ratio creates some reflection, but it is within tolerable limits (see "Size matters" section down below).

Search for "NoElec 1:9 HF antenna balun", they cost ca. 3 EUR, and are available from Aliexpress and Amazon.

### Amplifier (optional)

Overhead antenna placement definitely benefit from an LNA placed between the coax line and the balun. I can not recommend one though. Please send a pull request if you can.

### Feed through termination (optional)

Ahh, it's the same thing again... As the 2204A is a budget oscilloscope, there is no internal 50-ohm termination. The high-impedance input is forming an impedance mismatch, again. To overcome this, we can add a "feed through termination". This is literally just a BNC adapter with an 50-ohm resistor between the conductor and the shield.

Search Ali/Amazon for "P57 50Ohm Feed Through Terminator", this is a 10 EUR problem.

### Size matters

At 5 MHz we are dealing with a wavelength of about 40..50 meters. The shortest distance to get a full cancellation is at quarter-wavelenght, which is 10 meters. At the track, a permanent istallation can easily reach such distances. For testing, we can get away with much less cable though. You can solder a single wire to the center conductor of a BNC connector, and you're good to go.

## Learnings (so far...)

Firstly, 8-bit is barely enough. The antenna's ability to pick up the transmission is extremely sensitive to distance and transponder placement. A good transponder placement can easily generate 10x the signal than a suboptimal one. Such a difference is already eaten up a good chunk of the dynamic range.

The analog frontend of the scope can get temporarly overwhelmed when seeing a large signal (this is normal btw.). This severly hinders the ability to receive the transmission properly. Some clipping circuit (like at Cano/[RCHourGlass]() design) or a preamp with automatic gain control would come handly.

The trigger-based design (usb-polling) consumes probably more resources than a continous sampling would, while it captures potentially less transmittions. The PicoScope does not support continuous sampling at this rate.

## Contribute

Feel free :D

I am personally interrested in:
* HackRF-based frontend:
  * true 50 ohm input
  * built-in amplifiers
  * can oversample IQ stream at 20 MHz (SNR improvement)
  * gnuradio support
* JLCPCB-assembled transponder on a panel, using an open proof-of-concept protocol (proposal: max 8 bit init sequence + 8 bit preamble + 24 bit transponder id + 8 bit crc8 + 2 bit trailing sequence).
* Loop preamplifier with auto-gain control (practically compensating 20-30 dB for various suboptimal transponder placement) and input protection.