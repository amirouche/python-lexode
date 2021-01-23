# This source file was part of the FoundationDB open source project
#
# Copyright 2013-2018 Apple Inc. and the FoundationDB project authors
# Copyright 2018 Amirouche Boubekki <amirouche.boubekki@gmail.com>
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

from uuid import UUID
from bisect import bisect_left


_size_limits = tuple((1 << (i * 8)) - 1 for i in range(9))

int2byte = struct.Struct(">B").pack

# Define type codes:
BYTES_CODE = 0x01
DOUBLE_CODE = 0x21
FALSE_CODE = 0x26
INT_ZERO_CODE = 0x14
NEG_INT_START = 0x0B
NESTED_CODE = 0x05
NULL_CODE = 0x00
POS_INT_END = 0x1D
STRING_CODE = 0x02
TRUE_CODE = 0x27
UUID_CODE = 0x30


# Reserved: Codes 0x03, 0x04, 0x23, and 0x24 are reserved for historical reasons.

def _reduce_children(child_values):
    version_pos = -1
    len_so_far = 0
    bytes_list = []
    for child_bytes, child_pos in child_values:
        if child_pos >= 0:
            if version_pos >= 0:
                raise ValueError("Multiple incomplete versionstamps included in tuple")
            version_pos = len_so_far + child_pos
        len_so_far += len(child_bytes)
        bytes_list.append(child_bytes)
    return bytes_list, version_pos


def strinc(key):
    key = key.rstrip(b"\xff")
    return key[:-1] + int2byte(ord(key[-1:]) + 1)


def _find_terminator(v, pos):
    # Finds the start of the next terminator [\x00]![\xff] or the end of v
    while True:
        pos = v.find(b"\x00", pos)
        if pos < 0:
            return len(v)
        if pos + 1 == len(v) or v[pos + 1 : pos + 2] != b"\xff":
            return pos
        pos += 2


# If encoding and sign bit is 1 (negative), flip all of the bits. Otherwise, just flip sign.
# If decoding and sign bit is 0 (negative), flip all of the bits. Otherwise, just flip sign.
def _float_adjust(v, encode):
    if encode and v[0] & 0x80 != 0x00:
        return b"".join((int2byte(x ^ 0xFF) for x in v))
    elif not encode and v[0] & 0x80 != 0x80:
        return b"".join((int2byte(x ^ 0xFF) for x in v))
    else:
        return int2byte(v[0] ^ 0x80) + v[1:]


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
    elif code >= INT_ZERO_CODE and code < POS_INT_END:
        n = code - 20
        end = pos + 1 + n
        return struct.unpack(">Q", b"\x00" * (8 - n) + v[pos + 1 : end])[0], end
    elif code > NEG_INT_START and code < INT_ZERO_CODE:
        n = 20 - code
        end = pos + 1 + n
        return (
            struct.unpack(">Q", b"\x00" * (8 - n) + v[pos + 1 : end])[0]
            - _size_limits[n],
            end,
        )
    elif code == POS_INT_END:  # 0x1d; Positive 9-255 byte integer
        length = v[pos + 1]
        val = 0
        for i in range(length):
            val = val << 8
            val += v[pos + 2 + i]
        return val, pos + 2 + length
    elif code == NEG_INT_START:  # 0x0b; Negative 9-255 byte integer
        length = v[pos + 1] ^ 0xFF
        val = 0
        for i in range(length):
            val = val << 8
            val += v[pos + 2 + i]
        return val - (1 << (length * 8)) + 1, pos + 2 + length
    elif code == DOUBLE_CODE:
        return (
            struct.unpack(">d", _float_adjust(v[pos + 1 : pos + 9], False))[0],
            pos + 9,
        )
    elif code == UUID_CODE:
        return UUID(bytes=v[pos + 1 : pos + 17]), pos + 17
    elif code == FALSE_CODE:
        return False, pos + 1
    elif code == TRUE_CODE:
        return True, pos + 1
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
        raise ValueError("Unknown data type in DB: " + repr(v))


def _encode(value):
    # returns [code][data] (code != 0xFF)
    # encoded values are self-terminating
    # sorting need to work too!
    if value is None:
        return int2byte(NULL_CODE)
    elif isinstance(value, bool):
        if value:
            return int2byte(TRUE_CODE)
        else:
            return int2byte(FALSE_CODE)
    elif isinstance(value, bytes):
        return int2byte(BYTES_CODE) + value.replace(b"\x00", b"\x00\xFF") + b"\x00"
    elif isinstance(value, str):
        return (
            int2byte(STRING_CODE)
            + value.encode("utf-8").replace(b"\x00", b"\x00\xFF")
            + b"\x00"
        )
    elif isinstance(value, int):
        if value == 0:
            return int2byte(INT_ZERO_CODE)
        elif value > 0:
            if value >= _size_limits[-1]:
                length = (value.bit_length() + 7) // 8
                data = [int2byte(POS_INT_END), int2byte(length)]
                for i in range(length - 1, -1, -1):
                    data.append(int2byte((value >> (8 * i)) & 0xFF))
                return b"".join(data)

            n = bisect_left(_size_limits, value)
            return int2byte(INT_ZERO_CODE + n) + struct.pack(">Q", value)[-n:]
        else:
            if -value >= _size_limits[-1]:
                length = (value.bit_length() + 7) // 8
                value += (1 << (length * 8)) - 1
                data = [int2byte(NEG_INT_START), int2byte(length ^ 0xFF)]
                for i in range(length - 1, -1, -1):
                    data.append(int2byte((value >> (8 * i)) & 0xFF))
                return b"".join(data)

            n = bisect_left(_size_limits, -value)
            maxv = _size_limits[n]
            return int2byte(INT_ZERO_CODE - n) + struct.pack(">Q", maxv + value)[-n:]
    elif isinstance(value, float):
        return int2byte(DOUBLE_CODE) + _float_adjust(struct.pack(">d", value), True)
    elif isinstance(value, UUID):
        return int2byte(UUID_CODE) + value.bytes
    elif isinstance(value, tuple) or isinstance(value, list):
        child_bytes, _ = _reduce_children(map(lambda x: _encode(x, True), value))
        return b''.join([bytes([NESTED_CODE])] + child_bytes + [bytes([0x00])])
    else:
        raise ValueError("Unsupported data type: " + str(type(value)))


def pack(t):
    return b"".join((_encode(x) for x in t))


def unpack(key):
    pos = 0
    res = []
    if not isinstance(key, bytes):
        # it's ffi.buffer
        key = b"".join((x for x in key))
    while pos < len(key):
        r, pos = _decode(key, pos)
        res.append(r)
    return tuple(res)
