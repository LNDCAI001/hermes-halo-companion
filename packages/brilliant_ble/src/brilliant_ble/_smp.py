"""
Minimal SMP (MCUmgr) protocol support for OTA firmware updates on Halo devices.

Implements just enough CBOR and SMP framing for the image-management and
OS-reset commands used by `BrilliantBle.ota_flash_firmware()` / `ota_confirm()`.
"""
import asyncio

SMP_SERVICE_UUID = "8d53dc1d-1db7-4cd3-868b-8a527460aa84"
SMP_CHAR_UUID = "da2e7828-fbce-4e01-ae9e-261174997c48"
OP_READ = 0
OP_READ_RSP = 1
OP_WRITE = 2
OP_WRITE_RSP = 3
GROUP_OS = 0
GROUP_IMAGE = 1
ID_IMAGE_STATE = 0
ID_IMAGE_UPLOAD = 1
ID_OS_RESET = 5


class OtaError(Exception):
    """
    Raised when an OTA firmware operation fails, e.g. the connected device
    is not a Halo, the device reports an SMP error, or a response times out.
    """


def _encode_major(major: int, value: int) -> bytes:
    if value < 24:
        return bytes([major << 5 | value])
    if value < 0x100:
        return bytes([major << 5 | 24, value])
    if value < 0x10000:
        return bytes([major << 5 | 25]) + value.to_bytes(2, "big")
    return bytes([major << 5 | 26]) + value.to_bytes(4, "big")


def cbor_encode(value) -> bytes:
    if value is False:
        return b"\xf4"
    if value is True:
        return b"\xf5"
    if isinstance(value, int) and value >= 0:
        return _encode_major(0, value)
    if isinstance(value, (bytes, bytearray)):
        return _encode_major(2, len(value)) + bytes(value)
    if isinstance(value, str):
        data = value.encode("utf-8")
        return _encode_major(3, len(data)) + data
    if isinstance(value, list):
        return _encode_major(4, len(value)) + b"".join(cbor_encode(v) for v in value)
    if isinstance(value, dict):
        entries = [(k, v) for k, v in value.items() if v is not None]
        return _encode_major(5, len(entries)) + b"".join(
            cbor_encode(k) + cbor_encode(v) for k, v in entries
        )
    raise OtaError(f"Cannot CBOR encode {value!r}")


_BREAK = object()


def cbor_decode(data: bytes):
    offset = 0

    def take(count: int) -> bytes:
        nonlocal offset
        if offset + count > len(data):
            raise OtaError("Truncated CBOR data")
        value = data[offset:offset + count]
        offset += count
        return value

    def read_length(additional: int) -> int:
        if additional < 24:
            return additional
        if additional == 24:
            return take(1)[0]
        if additional == 25:
            return int.from_bytes(take(2), "big")
        if additional == 26:
            return int.from_bytes(take(4), "big")
        raise OtaError("Unsupported CBOR length")

    def read_item():
        initial = take(1)[0]
        major = initial >> 5
        additional = initial & 31

        if major == 7:
            if additional == 20:
                return False
            if additional == 21:
                return True
            if additional == 22:
                return None
            if additional == 31:
                return _BREAK
            raise OtaError("Unsupported CBOR simple value")

        if additional == 31:
            if major == 2:
                out = b""
                while (part := read_item()) is not _BREAK:
                    out += part
                return out
            if major == 3:
                out = ""
                while (part := read_item()) is not _BREAK:
                    out += part
                return out
            if major == 4:
                arr = []
                while (item := read_item()) is not _BREAK:
                    arr.append(item)
                return arr
            if major == 5:
                obj = {}
                while (key := read_item()) is not _BREAK:
                    obj[key] = read_item()
                return obj
            raise OtaError("Unsupported indefinite CBOR item")

        length = read_length(additional)

        if major == 0:
            return length
        if major == 1:
            return -1 - length
        if major == 2:
            return take(length)
        if major == 3:
            return take(length).decode("utf-8")
        if major == 4:
            return [read_item() for _ in range(length)]
        if major == 5:
            return {read_item(): read_item() for _ in range(length)}
        raise OtaError("Unsupported CBOR item")

    decoded = read_item()
    if decoded is _BREAK:
        raise OtaError("Unexpected CBOR break")
    return decoded


class SmpClient:
    """
    Sends SMP requests and matches responses by sequence number.

    `write` is an async callable that transmits one packet to the SMP
    characteristic. Incoming notification bytes must be passed to `feed()`.
    """

    def __init__(self, write):
        self._write = write
        self._sequence = 0
        self._rx_buffer = b""
        self._pending: dict[int, tuple[asyncio.Future, int]] = {}

    def feed(self, chunk: bytes):
        """
        Consumes incoming notification bytes, reassembling SMP packets and
        resolving the pending request that matches each packet's sequence number.
        """
        self._rx_buffer += bytes(chunk)

        while len(self._rx_buffer) >= 8:
            length = int.from_bytes(self._rx_buffer[2:4], "big")
            total = 8 + length
            if len(self._rx_buffer) < total:
                return

            packet = self._rx_buffer[:total]
            self._rx_buffer = self._rx_buffer[total:]

            op = packet[0]
            seq = packet[6]
            waiter = self._pending.pop(seq, None)
            if waiter is None:
                # unsolicited or stale response; ignore
                continue
            future, expected_op = waiter
            if future.done():
                continue

            try:
                payload = cbor_decode(packet[8:])
            except OtaError as e:
                future.set_exception(e)
                continue

            if op != expected_op:
                future.set_exception(OtaError(f"Unexpected SMP op {op}"))
            elif isinstance(payload, dict) and payload.get("rc"):
                future.set_exception(OtaError(f"SMP error rc={payload['rc']}"))
            else:
                future.set_result(payload)

    async def request(self, op: int, group: int, id: int, payload: dict, timeout: float = 8.0):
        """
        Sends one SMP request and returns the decoded response payload,
        raising OtaError on an SMP error or timeout.
        """
        body = cbor_encode(payload)
        seq = self._sequence
        self._sequence = (self._sequence + 1) & 0xFF

        packet = (
            bytes([op, 0])
            + len(body).to_bytes(2, "big")
            + group.to_bytes(2, "big")
            + bytes([seq, id])
            + body
        )

        future = asyncio.get_running_loop().create_future()
        expected_op = OP_READ_RSP if op == OP_READ else OP_WRITE_RSP
        self._pending[seq] = (future, expected_op)

        try:
            await self._write(packet)
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            raise OtaError(f"SMP response timed out for group {group}, id {id}")
        finally:
            self._pending.pop(seq, None)
