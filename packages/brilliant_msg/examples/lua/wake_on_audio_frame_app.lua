local data = require('data.min')
local code = require('code.min')

-- Phone to Frame flags
local AUDIO_DATA_FINAL_MSG = 0x06
local AUDIO_DATA_NON_FINAL_MSG = 0x05

-- 1 byte reserved for flag
local MTU = frame.bluetooth.max_length() - 1
-- data buffer needs to be even for reading from microphone
if MTU % 2 == 1 then MTU = MTU - 1 end

-- Main app loop
function app_loop()
	frame.display.clear()
	frame.display.text('Frame App Started', 50, 50)
	frame.display.show()

	-- tell the host program that the frameside app is ready (waiting on await_print)
	print('Frame app is running')
	--print(frame.time.utc() .. ' Clearing firmware logs on Halo')
	--frame.log.clear()
	--frame.sleep(0.5) -- not sure if the clear is finishing cleanly


	print(frame.time.utc() .. ' Standby, then streaming audio on wake from AAD, tap, Bluetooth')
	pcall(frame.standby)
	print(frame.time.utc() .. ' Woke up from standby: ' .. frame.wakeup_source())
							
	frame.microphone.start{sample_rate=8000, bit_depth=16}
	local start_time = frame.time.utc()
	print(start_time .. ' Microphone started - recording for 3 seconds')

	frame.display.clear()
	frame.display.text("Rec", 50, 50)

	local audio_data = ''
	local first_bytes_time = nil
	local empty_reads = 0
	local last_empty_read_time = nil

	while true do
		audio_data = frame.microphone.read(MTU)

		if audio_data == nil then
			-- send an end-of-stream message back to the host
			print(frame.time.utc() .. ' End of audio stream reached, sending final message to host')
			frame.bluetooth.send(string.char(AUDIO_DATA_FINAL_MSG))
			break

		-- send the data that was read
		elseif audio_data ~= '' then
			if first_bytes_time == nil then
				first_bytes_time = frame.time.utc()
				print(first_bytes_time .. ' First audio data chunk read')
				if empty_reads > 0 then
					print(frame.time.utc() .. ' Warning: ' .. empty_reads .. ' empty reads occurred before first audio data was read: ' .. last_empty_read_time-start_time .. ' seconds after start. ')
					print(frame.time.utc() .. ' First audio sample start time after mic start: ' .. (first_bytes_time-start_time-(string.len(audio_data)/16000)) .. ' seconds')
				end
				print(frame.time.utc() .. ' Sending first audio data chunk of size ' .. string.len(audio_data) .. ' bytes')
			end
			frame.bluetooth.send(string.char(AUDIO_DATA_NON_FINAL_MSG) .. audio_data)
		else
			-- no data read, no data sent
			empty_reads = empty_reads + 1
			last_empty_read_time = frame.time.utc()
		end

		if frame.time.utc() - start_time > 3.0 then
			print(frame.time.utc() .. ' Stopping audio stream after 3 seconds')
			frame.microphone.stop()

			-- dump the firmware logs back to the host
			print(frame.time.utc() .. ' Dumping firmware logs to host')
			frame.log.list()
			print(frame.time.utc() .. ' Log file #0')
			frame.log.show(0)
			print(frame.time.utc() .. ' Log file #1')
			frame.log.show(1)
		end
		--frame.yield()
	end
end

-- run the main app loop
app_loop()
