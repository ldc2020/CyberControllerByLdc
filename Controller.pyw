import threading
from TcpServer import TcpServer
from KeyboardListener import KeyboardListener
from service import *
from ComputerMonitor import ComputerMonitor
from SystemMonitor import SystemMonitor
from screen_shot import ScreenCapture
from CommandMessage import CommandMessage;
import json
import pyautogui
from KeyboardManager import *
import time


def delayed_play(delay=5):
    """Wait for media player to start then press play"""
    print(f"Waiting {delay}s for media player to initialize...")
    time.sleep(delay)
    print("Executing delayed play command")
    pyautogui.press('playpause')

def on_message_received(data):
	print(f"Received data: {data}")
	try:
		command_message = json.loads(data)
		
		# Handle explicit commands
		if "command" in command_message:
			cmd = command_message["command"]
			msg = command_message.get("message", "")
			
			if cmd == 6: # Media Control
				print(f"Media Control: {msg}")
				if msg == "START":
					# Smart Start: Check if player is running, if not, launch it
					if not is_media_player_running():
						if launch_default_media_player():
							# Launching takes time, so we wait a bit in a separate thread before pressing play
							threading.Thread(target=delayed_play, args=(8,)).start()
					else:
						# If running, only press play if NOT currently playing
						# This prevents pausing (and OSD/volume bar appearance) if already playing
						if not is_media_playing():
							pyautogui.press('playpause')
						else:
							print("Media is already playing, ignoring START command")
				elif msg == "STOP":
					# Only press playpause (to pause) if currently playing
					# Pressing stop usually resets the track, which might not be desired
					if is_media_playing():
						pyautogui.press('playpause')
					else:
						# Optional: ensure it's stopped/paused
						pass
				elif msg == "PREV":
					pyautogui.press('prevtrack')
				elif msg == "NEXT":
					pyautogui.press('nexttrack')
				elif msg == "VOL_UP":
					pyautogui.press('volumeup')
				elif msg == "VOL_DOWN":
					pyautogui.press('volumedown')
				return

		# Handle script execution
		if "script" in command_message:
			script = command_message["script"]
			params = command_message.get("params")
			exec(script)
	except Exception as e:
		print(f"Error executing script/command: {e}")

def on_screen_locked():
	print("screen locked")
	data = json.dumps({"command":2,"message":""})
	print(data)
	tcpServer.send_text(data)

def on_screen_unlocked():
	print("screen unlocked")
	data = json.dumps({"command":3,"message":""})
	print(data)
	tcpServer.send_text(data)

computerMonitor = ComputerMonitor(on_screen_locked, on_screen_unlocked)

def on_tcp_connected():
	if not computerMonitor.started:
		computerMonitor.start()
	systemMonitor.start()


tcpServer = TcpServer()
tcpServer.set_receive_listener(on_message_received)
tcpServer.connected_listener = on_tcp_connected

systemMonitor = SystemMonitor(tcpServer)
keyboardListener = KeyboardListener(tcpServer)

# Initialize ScreenCapture and pass to KeyboardListener
screenCapture = ScreenCapture()
keyboardListener.set_screen_capture(screenCapture)

tcpServer.start()

def onTrans():
	print("need trans")
	content = getClipContent()
	text = json.dumps({"command":1,"message":content})

	tcpServer.send_text(text)

def onRecordStart():
	print("start recording")
	text = json.dumps({"command":100,"message":"开始录音"})
	print(f"Sending to mobile: {text}")
	tcpServer.send_text(text)

def onRecordEnd():
	print("stop recording")
	text = json.dumps({"command":101,"message":"结束录音"})
	print(f"Sending to mobile: {text}")
	tcpServer.send_text(text)

# Start listening (non-blocking now)
keyboardListener.listen_keyboard(onTrans, onRecordStart, onRecordEnd)

# Run Tkinter main loop (blocking)
screenCapture.run_forever()
