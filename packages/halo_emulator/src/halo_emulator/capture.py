from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Callable

LOG = logging.getLogger(__name__)


@dataclass
class HaloEvent:
    event_id: str = ""
    timestamp: float = 0.0
    source: str = "halo"
    modality: str = "unknown"
    payload: bytes | dict | None = None
    consent_state: str = "user-confirmed"
    sensitivity: str = "medium"
    retention_class: str = "ephemeral"

    def __post_init__(self) -> None:
        if not self.event_id:
            self.event_id = uuid.uuid4().hex
        if not self.timestamp:
            self.timestamp = time.time()

    def envelope(self) -> dict:
        data = asdict(self)
        payload = data.get("payload")
        if isinstance(payload, (bytes, bytearray)):
            data["payload"] = {"_bytes_hex": payload.hex()}
        return data

    def to_json(self, **json_kwargs) -> str:
        return json.dumps(self.envelope(), **json_kwargs)


_MODALITY_FROM_MSG_CODE = {
    0x04: "tap",
    0x09: "tap",
    0x0A: "imu",
    0x05: "audio",
    0x06: "audio",
    0x07: "photo",
    0x08: "photo",
}


class CaptureListener:
    def __init__(
        self,
        frame: "EmulatorBrilliantMsg",
        *,
        consent_state: str = "user-confirmed",
        sensitivity: str = "medium",
        retention_class: str = "ephemeral",
        on_event: Callable[[HaloEvent], None] | None = None,
    ) -> None:
        self._frame = frame
        self._consent_state = consent_state
        self._sensitivity = sensitivity
        self._retention_class = retention_class
        self._on_event = on_event
        self._events: list[HaloEvent] = []
        frame._emu._bluetooth.add_send_listener(self._on_send)

    def _on_send(self, data: bytes) -> None:
        if not data:
            return
        msg_code = data[0]
        modality = _MODALITY_FROM_MSG_CODE.get(msg_code, "unknown")
        event = HaloEvent(
            source="halo",
            modality=modality,
            consent_state=self._consent_state,
            sensitivity=self._sensitivity,
            retention_class=self._retention_class,
            payload=data,
        )
        self._events.append(event)
        LOG.debug("capture event: %s", event.to_json())
        if self._on_event is not None:
            self._on_event(event)

    @property
    def events(self) -> list[HaloEvent]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()
