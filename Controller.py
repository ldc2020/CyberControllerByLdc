import threading
from TcpServer import TcpServer
from KeyboardListener import KeyboardListener
from service import *
from ComputerMonitor import ComputerMonitor
from CommandMessage import CommandMessage;
import json
import pyautogui
from KeyboardManager import *
import time


def on_message_received(data):
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
						launch_default_media_player()
						# Wait a bit for the player to start before sending play command
						# But usually players auto-play or take focus. 
						# We can send playpause anyway after a short delay if needed, 
						# but let's just launch it for now as 'playpause' might close it if it auto-plays.
						# Actually, sending playpause immediately might pause it if it auto-plays.
						# So if we launched it, we might NOT want to send playpause immediately.
						pass 
					else:
						pyautogui.press('playpause')
				elif msg == "STOP":
					pyautogui.press('stop')
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
		print(f"Error processing message: {e}")

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


tcpServer = TcpServer()
tcpServer.set_receive_listener(on_message_received)
tcpServer.connected_listener = on_tcp_connected
tcpServer.start()

keyboardListener = KeyboardListener(tcpServer)

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

keyboardListener.listen_keyboard(onTrans, onRecordStart, onRecordEnd)