"""Halo companion app: host-side controller for the meds feature."""

from halo_companion.controller import (
    CaptureResult,
    MedSchedule,
    MedsController,
    MedsState,
)

__all__ = ["CaptureResult", "MedSchedule", "MedsController", "MedsState"]

# Privacy mode: set controller.privacy_mode = True to suppress med names
# on the device display. Useful in shared/public environments.
#
# Data deletion: call controller.clear_all_data() to wipe all in-memory
# capture records. For persistent Vestige store deletion, use the
# Vestige MCP delete API (vestige-mcp smart_delete tool).
#
# Store isolation: the Vestige store lives at vestige-store/vestige.db
# within this project directory. Set VESTIGE_DATA_DIR to override.
# The VestigeWriter class accepts a data_dir parameter for explicit control.
