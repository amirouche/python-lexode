import lexode




def test_nominal():
    expected = [
        None, True, False,
        -2**64 + 1, -1234567890, -42, -3.14, 0, 3.14, 42, 1234567890, 2**64 - 1,
        "hello world",
        b"C0FF33B4D",
    ]
    expected.append(tuple(expected))
    expected = tuple(expected)

    assert lexode.unpack(lexode.pack(expected)) == expected
