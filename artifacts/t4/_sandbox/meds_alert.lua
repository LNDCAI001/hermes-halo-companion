-- meds_alert.lua
-- Halo meds companion app: displays meds capture confirmation and scheduled
-- reminders on the 256x256 display, and invokes the device sound primitive.
--
-- The HOST (Python) owns all stateful logic:
--   * double-dose detection (count of "taking meds" captures per day)
--   * reminder scheduling
-- and pushes text to render via the standard plain_text protocol (TxPlainText,
-- TEXT_FLAG 0x0a) plus reminder/reset cues via MSG_REMINDER / MSG_RESET.
-- The device only renders, fires the (native) sound primitive, and reports back
-- which primitive it ran.
--
-- Pairs with: halo_companion/controller.py  (MedsController)

local data = require('data.min')
local plain_text = require('plain_text.min')

local TEXT_FLAG = 0x0a
local MSG_TAP = 0x20        -- device -> host: user tapped to confirm a capture
local MSG_AUDIO = 0x21      -- device -> host: native sound primitive fired
local MSG_TEXT_ECHO = 0x22  -- device -> host: exact text now on the display
local MSG_REMINDER = 0xFE   -- host -> device: show reminder + play sound
local MSG_RESET = 0xFF      -- host -> device: return to idle

-- data.min registers its own bluetooth.receive_callback on require().

-- ---- display helpers -------------------------------------------------------

local function emit_text(s)
    frame.bluetooth.send(string.char(MSG_TEXT_ECHO) .. s)
end

local function show_text(text)
    frame.display.clear(0)
    local shown = {}
    local line_num = 0
    for line in text:gmatch('([^\n]*)') do
        if line ~= '' then
            frame.display.text(line, 10, line_num * 30 + 30, 0xFFFFFF)
            shown[#shown + 1] = line
            line_num = line_num + 1
        end
    end
    frame.display.show()
    emit_text(table.concat(shown, '\n'))
end

local function show_reminder(med)
    frame.display.clear(0)
    frame.display.text('Reminder', 30, 30, 0xFFC800)            -- amber title
    frame.display.text('Time to take', 20, 80, 0xFFFFFF)
    frame.display.text(med, 30, 120, 0xFFFFFF)                 -- the med name
    frame.display.text('tap = done', 40, 200, 0x969696)        -- grey hint
    frame.display.show()
    emit_text('Time to take ' .. med)
end

-- ---- native sound primitive ------------------------------------------------
-- frame.speaker.* is a no-op stub in the emulator, but the real device plays
-- audio here. We wrap it and emit MSG_AUDIO so the host (and tests) can observe
-- that the native sound primitive was actually invoked.

local function play_tone()
    pcall(frame.speaker.start, { sample_rate = 8000, bit_depth = 8 })
    pcall(frame.speaker.play, 'tone')
    pcall(frame.speaker.stop)
    frame.bluetooth.send(string.char(MSG_AUDIO))
end

-- ---- initial idle screen --------------------------------------------------

show_text('Meds\nready')

-- ---- tap to confirm a "taking meds" capture --------------------------------

frame.imu.tap_callback(function()
    frame.bluetooth.send(string.char(MSG_TAP))
end)

-- ---- main loop: process incoming host messages -----------------------------

while true do
    rc, err = pcall(function()
        local items = data.process_raw_items()

        for i = 1, #items do
            local flag = items[i][1]
            local raw = items[i][2]

            if flag == TEXT_FLAG then
                local parsed = plain_text.parse_plain_text(raw)
                if parsed ~= nil and parsed.string ~= nil then
                    show_text(parsed.string)
                end

            elseif flag == MSG_REMINDER then
                if raw == '' or raw == nil then raw = 'meds' end
                show_reminder(raw)
                play_tone()

            elseif flag == MSG_RESET then
                show_text('Meds\nready')
            end
        end

        frame.sleep(0.1)
    end)
    if rc == false then
        frame.display.clear(0)
        break
    end
end
