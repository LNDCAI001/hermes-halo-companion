"""
Unit tests for the SMP/CBOR machinery behind BrilliantBle's OTA support.
No hardware required.
"""
import asyncio

import pytest

from brilliant_ble._smp import (
    GROUP_IMAGE,
    GROUP_OS,
    ID_IMAGE_STATE,
    ID_IMAGE_UPLOAD,
    ID_OS_RESET,
    OP_READ,
    OP_READ_RSP,
    OP_WRITE,
    OP_WRITE_RSP,
    OtaError,
    SmpClient,
    cbor_decode,
    cbor_encode,
)


def make_response(op: int, group: int, id: int, seq: int, payload: dict) -> bytes:
    body = cbor_encode(payload)
    return (
        bytes([op, 0])
        + len(body).to_bytes(2, "big")
        + group.to_bytes(2, "big")
        + bytes([seq, id])
        + body
    )


class TestCbor:
    def test_upload_payload_round_trip(self):
        payload = {
            "image": 0,
            "len": 300000,
            "sha": bytes(range(32)),
            "off": 0,
            "data": b"\x01\x02" * 200,
        }
        assert cbor_decode(cbor_encode(payload)) == payload

    def test_int_width_breakpoints(self):
        values = [0, 1, 23, 24, 255, 256, 65535, 65536, 2**32 - 1]
        assert cbor_decode(cbor_encode(values)) == values

    def test_bool_str_bytes(self):
        payload = {"confirm": False, "ok": True, "hash": b"\xaa" * 32, "name": "halo"}
        assert cbor_decode(cbor_encode(payload)) == payload

    def test_none_values_skipped(self):
        assert cbor_decode(cbor_encode({"a": 1, "b": None})) == {"a": 1}

    def test_negative_int_decode(self):
        assert cbor_decode(b"\x20") == -1
        assert cbor_decode(b"\x38\x63") == -100

    def test_indefinite_length_decode(self):
        indef_map = b"\xbf" + cbor_encode("rc") + cbor_encode(0) + cbor_encode("off") + cbor_encode(384) + b"\xff"
        assert cbor_decode(indef_map) == {"rc": 0, "off": 384}

        indef_bytes = b"\x5f" + cbor_encode(b"ab") + cbor_encode(b"cd") + b"\xff"
        assert cbor_decode(indef_bytes) == b"abcd"

    def test_unencodable_value_raises(self):
        with pytest.raises(OtaError):
            cbor_encode(1.5)

    def test_truncated_data_raises(self):
        with pytest.raises(OtaError):
            cbor_decode(cbor_encode({"off": 384})[:-1])


class TestSmpClient:
    def test_request_framing_and_sequence_increment(self):
        async def run():
            packets = []

            async def write(packet):
                packets.append(packet)
                # echo a success response so request() returns
                seq = packet[6]
                smp.feed(make_response(OP_WRITE_RSP, GROUP_IMAGE, ID_IMAGE_UPLOAD, seq, {"rc": 0, "off": 384}))

            smp = SmpClient(write)
            payload = {"off": 0, "data": b"\x00" * 16}
            await smp.request(OP_WRITE, GROUP_IMAGE, ID_IMAGE_UPLOAD, payload)
            await smp.request(OP_WRITE, GROUP_IMAGE, ID_IMAGE_UPLOAD, payload)

            body = cbor_encode(payload)
            first = packets[0]
            assert first[0] == OP_WRITE
            assert first[1] == 0
            assert int.from_bytes(first[2:4], "big") == len(body)
            assert int.from_bytes(first[4:6], "big") == GROUP_IMAGE
            assert first[6] == 0
            assert first[7] == ID_IMAGE_UPLOAD
            assert first[8:] == body
            # sequence number increments per request
            assert packets[1][6] == 1

        asyncio.run(run())

    def test_response_reassembled_across_chunks(self):
        async def run():
            async def write(packet):
                response = make_response(OP_READ_RSP, GROUP_IMAGE, ID_IMAGE_STATE, packet[6],
                                         {"images": [{"slot": 1, "hash": b"\xab" * 32}]})
                # deliver in two notification chunks, split mid-header
                smp.feed(response[:5])
                smp.feed(response[5:])

            smp = SmpClient(write)
            rsp = await smp.request(OP_READ, GROUP_IMAGE, ID_IMAGE_STATE, {})
            assert rsp["images"][0]["hash"] == b"\xab" * 32

        asyncio.run(run())

    def test_nonzero_rc_raises(self):
        async def run():
            async def write(packet):
                smp.feed(make_response(OP_WRITE_RSP, GROUP_OS, ID_OS_RESET, packet[6], {"rc": 3}))

            smp = SmpClient(write)
            with pytest.raises(OtaError, match="rc=3"):
                await smp.request(OP_WRITE, GROUP_OS, ID_OS_RESET, {})

        asyncio.run(run())

    def test_unexpected_op_raises(self):
        async def run():
            async def write(packet):
                # respond with a read-response op to a write request
                smp.feed(make_response(OP_READ_RSP, GROUP_IMAGE, ID_IMAGE_STATE, packet[6], {}))

            smp = SmpClient(write)
            with pytest.raises(OtaError, match="Unexpected SMP op"):
                await smp.request(OP_WRITE, GROUP_IMAGE, ID_IMAGE_STATE, {"confirm": True})

        asyncio.run(run())

    def test_timeout_raises(self):
        async def run():
            async def write(packet):
                pass  # never respond

            smp = SmpClient(write)
            with pytest.raises(OtaError, match="timed out"):
                await smp.request(OP_READ, GROUP_IMAGE, ID_IMAGE_STATE, {}, timeout=0.05)

        asyncio.run(run())

    def test_unsolicited_response_ignored(self):
        async def run():
            async def write(packet):
                # a stale response with a different sequence number arrives first
                smp.feed(make_response(OP_READ_RSP, GROUP_IMAGE, ID_IMAGE_STATE, (packet[6] + 1) & 0xFF, {"images": []}))
                smp.feed(make_response(OP_READ_RSP, GROUP_IMAGE, ID_IMAGE_STATE, packet[6], {"images": [1]}))

            smp = SmpClient(write)
            rsp = await smp.request(OP_READ, GROUP_IMAGE, ID_IMAGE_STATE, {})
            assert rsp == {"images": [1]}

        asyncio.run(run())
