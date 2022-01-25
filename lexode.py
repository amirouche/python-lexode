# This source file was part of the FoundationDB open source project
#
# Copyright 2013-2018 Apple Inc. and the FoundationDB project authors
# Copyright 2018-2022 Amirouche Boubekki <amirouche@hyper.dev>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import struct


_size_limits = tuple((1 << (i * 8)) - 1 for i in range(9))

# Define type codes:
BYTES_CODE = 0x01
DOUBLE_CODE = 0x09
FALSE_CODE = 0x02
INTEGER_NEGATIVE_CODE = 0x04
INTEGER_POSITIVE_CODE = 0x06
INTEGER_ZERO = 0x05
NESTED_CODE = 0x08
NULL_CODE = 0x00
STRING_CODE = 0x07
TRUE_CODE = 0x03


INTEGER_MAX = struct.unpack('>Q', b'\xff' * 8)[0]


def _find_terminator(v, pos):
    # Finds the start of the next terminator [\x00]![\xff] or the end of v
    while True:
        pos = v.find(b"\x00", pos)
        if pos < 0:
            return len(v)
        if pos + 1 == len(v) or v[pos + 1:pos + 2] != b"\xff":
            return pos
        pos += 2


# If encoding and sign bit is 1 (negative), flip all of the bits. Otherwise, just flip sign.
# If decoding and sign bit is 0 (negative), flip all of the bits. Otherwise, just flip sign.
def _float_adjust(v, encode):
    if encode and v[0] & 0x80 != 0x00:
        return bytes(x ^ 0xFF for x in v)
    elif not encode and v[0] & 0x80 != 0x80:
        return bytes(x ^ 0xFF for x in v)
    else:
        return bytes((v[0] ^ 0x80,)) + v[1:]


def _decode(v, pos):
    code = v[pos]
    if code == NULL_CODE:
        return None, pos + 1
    elif code == BYTES_CODE:
        end = _find_terminator(v, pos + 1)
        return v[pos + 1 : end].replace(b"\x00\xFF", b"\x00"), end + 1
    elif code == STRING_CODE:
        end = _find_terminator(v, pos + 1)
        return v[pos + 1 : end].replace(b"\x00\xFF", b"\x00").decode("utf-8"), end + 1
    elif code == INTEGER_ZERO:
        return 0, pos + 1
    elif code == INTEGER_NEGATIVE_CODE:
        end = pos + 1 + 8
        value = struct.unpack(">Q", v[pos + 1 : end])[0] - INTEGER_MAX
        return value, end
    elif code == INTEGER_POSITIVE_CODE:
        end = pos + 1 + 8
        value = struct.unpack(">Q", v[pos + 1 : end])[0]
        return value, end
    elif code == FALSE_CODE:
        return False, pos + 1
    elif code == TRUE_CODE:
        return True, pos + 1
    elif code == DOUBLE_CODE:
        return (
            struct.unpack(">d", _float_adjust(v[pos + 1 : pos + 9], False))[0],
            pos + 9,
        )
    elif code == NESTED_CODE:
        ret = []
        end_pos = pos + 1
        while end_pos < len(v):
            if v[end_pos] == 0x00:
                if end_pos + 1 < len(v) and v[end_pos + 1] == 0xFF:
                    ret.append(None)
                    end_pos += 2
                else:
                    break
            else:
                val, end_pos = _decode(v, end_pos)
                ret.append(val)
        return tuple(ret), end_pos + 1
    else:
        raise ValueError("Unknown data type from database: " + repr(v))


def _encode(value, nested=False):
    if value is None:
        if nested:
            return bytes((NULL_CODE, 0xFF))
        else:
            return bytes((NULL_CODE,))
    elif isinstance(value, bool):
        if value:
            return bytes((TRUE_CODE,))
        else:
            return bytes((FALSE_CODE,))
    elif isinstance(value, bytes):
        return bytes((BYTES_CODE,)) + value.replace(b"\x00", b"\x00\xFF") + b"\x00"
    elif isinstance(value, str):
        return (
            bytes((STRING_CODE,))
            + value.encode("utf-8").replace(b"\x00", b"\x00\xFF")
            + b"\x00"
        )
    elif value == 0:
        return bytes((INTEGER_ZERO,))
    elif isinstance(value, int):
        if value > 0:
            out = bytes((INTEGER_POSITIVE_CODE,)) + struct.pack('>Q', value)
            return out
        else:
            value = INTEGER_MAX + value
            out = bytes((INTEGER_NEGATIVE_CODE,)) + struct.pack('>Q', value)
            return out
    elif isinstance(value, float):
        return bytes((DOUBLE_CODE,)) + _float_adjust(struct.pack(">d", value), True)
    elif isinstance(value, (tuple, list)):
        child_bytes = list(map(lambda x: _encode(x, True), value))
        return b''.join([bytes((NESTED_CODE,))] + child_bytes + [bytes((0x00,))])
    else:
        raise ValueError("Unsupported data type: {}".format(type(value)))


def pack(t):
    return b"".join((_encode(x) for x in t))


def unpack(key):
    pos = 0
    res = []
    while pos < len(key):
        r, pos = _decode(key, pos)
        res.append(r)
    return tuple(res)


def next_prefix(x):
    x = x.rstrip(b"\xff")
    return x[:-1] + bytes((x[-1] + 1,))
