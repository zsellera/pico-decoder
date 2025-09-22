import sys

RC3_PREAMBLE = 0x7916

def preamble_position(bytestream):
    # find preamble in the first 4 octetts
    first4 = int.from_bytes(bytestream[:4].ljust(4, b'\x00'), byteorder="big")
    for shift in range(17):
        candidate = (first4 >> shift) & 0xFFFF
        if candidate == RC3_PREAMBLE:
            return 16 - shift
    return None

def cut_first_bits(bytestream, cut=0):
    cut_bytes = int(cut / 8)
    shift = cut - 8 * cut_bytes

    # shortcut if no further bit-shifting is needed:
    if shift == 0:
        return bytes(bytestream[cut_bytes:])

    # cut the partial bytes
    result = bytearray()
    for i in range(cut_bytes, len(bytestream) - 1):
        b = (bytestream[i] << shift) | (bytestream[i+1] >> (8-shift))
        b &= 0xFF
        result.extend(b.to_bytes(1, "big"))
    return bytes(result)

def decode_rc3(payload):
    # sometimes the first octett is some header, cut it:
    if payload[0] == 0b0011011 and len(payload)>8:
        payload = payload[1:]

    # the convolutional coder produces 2 bits output per input bit
    # 01 and 10 decodes to 1
    # 11 and 00 decodes to 0
    # MSB 2 bits are junk in each byte, meaning there are 3 bits encoded in each octett
    # in reverse order, for the sake of simplicity...
    transponder_bits = [0] * 24
    for i in range(8):
        transponder_bits[24 - i*3 - 1] = ((payload[i] & 0x20) >> 5) ^ ((payload[i] & 0x10) >> 4)
        transponder_bits[24 - i*3 - 2] = ((payload[i] & 0x08) >> 3) ^ ((payload[i] & 0x04) >> 2)
        transponder_bits[24 - i*3 - 3]  = ((payload[i] & 0x02) >> 1) ^ ((payload[i] & 0x01) >> 0)
    # return transponder_bits
    return sum(d << (23 - i) for i, d in enumerate(transponder_bits))


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue  # skip empty lines
    
    try:
        time_str, strength_str, bytestream_hex = line.split(maxsplit=2)
        time = float(time_str)
        strength = float(strength_str)
        bytestream = bytes.fromhex(bytestream_hex)

        # RC3 - at least 2 octetts preamble + 8 octetts of payload
        if len(bytestream) < 10:
            continue

        # locate preamble
        preamble_at = preamble_position(bytestream)
        if preamble_at is None: # preamble not present
            continue

        # cut preamble
        payload = cut_first_bits(bytestream, preamble_at + 16)

        # decode payload
        transponder_id = decode_rc3(payload)

        # some status message, real transponder is 7-digit
        if transponder_id > 9_999_999:
            continue
        
        print(f"{time} {strength} {transponder_id}", flush=True)
    
    except ValueError:
        print(f"Invalid input line: {line}", file=sys.stderr)
