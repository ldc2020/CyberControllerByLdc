import keyboard
import time
from screen_shot import ScreenCapture
import io
import threading

class KeyboardListener:
	def __init__(self, tcpServer):
		self.tcpServer = tcpServer
		self.t = 0
		self.c = 0
		self.key_state_map={}
		self.screen_capture = None # Expects a ScreenCapture instance
		
	def set_screen_capture(self, screen_capture):
		self.screen_capture = screen_capture

	def listen_keyboard(self, callback, on_record_start=None, on_record_end=None):
		self.callback = callback
		self.on_record_start = on_record_start
		self.on_record_end = on_record_end
		self.recording = False  # Track recording state to avoid repeated events
		keyboard.hook(self.onKeyEvent)
		# Removed keyboard.wait() to allow main thread to run Tkinter loop

	def onImgCapture(self,pic):	
		imgByteArr = io.BytesIO()
		pic.save(imgByteArr, format='JPEG')
		bytes_data = imgByteArr.getvalue()
		self.tcpServer.send_img(bytes_data)
		if self.screen_capture:
			self.screen_capture.trigger_toast("截图已发送至手机")

	def isCtrlHolding(self):
		return ('ctrl' in self.key_state_map and self.key_state_map['ctrl']=='down')\
			or ('left ctrl' in self.key_state_map and self.key_state_map['left ctrl']=='down')\
			or ('right ctrl' in self.key_state_map and self.key_state_map['right ctrl']=='down')

	def isAltHolding(self):
		return ('alt' in self.key_state_map and self.key_state_map['alt']=='down')\
			or ('left alt' in self.key_state_map and self.key_state_map['left alt']=='down')\
			or ('right alt' in self.key_state_map and self.key_state_map['right alt']=='down')

	def isKeyHolding(self,key):
		return (key in self.key_state_map and self.key_state_map[key]=='down')


	def onKeyEvent(self,key):
		#update key_state_map
		self.key_state_map[key.name.lower()]=key.event_type
		
		# Debugging: Print key info for Ctrl or Space (Conditional)
		# if key.name == 'space' or 'ctrl' in key.name.lower():
		# 	print(f"Debug: Key='{key.name}', Event='{key.event_type}', CtrlHolding={self.isCtrlHolding()}")

		#is screenshoot?

		if  self.isAltHolding()\
			and key.event_type=="down"\
			and key.name.lower()=="a":
			if self.screen_capture:
				self.screen_capture.trigger_capture(self.onImgCapture)
			else:
				print("Screen capture module not initialized")

		# print(self.key_state_map) # Reduced logging
		#is triple c?
		if  key.event_type=="down" \
			and key.name.lower()=="c" \
			and self.isCtrlHolding():

			if self.t == 0:
				self.t=time.time()
				self.c += 1
				print("wait for nex c",self.c)
				return

			if (time.time()-self.t<0.5):
				self.t=time.time()
				self.c += 1
				print("wait for nex c:",self.c)

			else:
				self.c = 0
				self.t=0
				print("wait for nex c",self.c)

			if self.c>=2:
				self.c=0
				print("need trans")
				if self.callback:
					self.callback()
		
		# Ctrl + Space Logic for Recording
		# Trigger only when 'space' is pressed/released while Ctrl is held
		if key.name == 'space':
			if key.event_type == "down" and self.isCtrlHolding():
				if not self.recording:
					self.recording = True
					print("Start Recording (Ctrl + Space)")
					if self.on_record_start:
						self.on_record_start()
			elif key.event_type == "up":
				# Note: We check if we were recording, because Ctrl might be released before Space
				# But typically we want to stop when Space is released
				if self.recording:
					self.recording = False
					print("Stop Recording (Ctrl + Space released)")
					if self.on_record_end:
						self.on_record_end()
		
		# Safety: If Ctrl is released while recording, also stop
		if ('ctrl' in key.name.lower()) \
			and key.event_type == "up" and self.recording:
			self.recording = False
			print("Stop Recording (Ctrl released)")
			if self.on_record_end:
				self.on_record_end()
