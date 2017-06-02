#!/usr/bin/env python
# -*- coding: utf-8 -*-
import linphone
import logging
import signal
import time
import daemon
import os
import sys
from button import *
#Setup button with corresponding GPIO
b = Button(25)
#Set SIP adress for the doorbell to call
doorbellToAddress = 'your sip adress goes here'


#-------------------------------------------------
#to start the daemon:
# linphonecsh init -a -C -c ~/.linphonerc
#to stop the daemon:
# linphonecsh exit


class SecurityCamera:
  def __init__(self, whitelist=[]):
    self.quit = False
    self.whitelist = whitelist

    callbacks = linphone.Factory.get().create_core_cbs()
    callbacks.call_state_changed = self.call_state_changed
    callbacks.registration_state_changed = self.call_state_changed
    callbacks.message_received = self.message_received

    path = os.path.dirname(os.path.abspath(__file__))
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    self.logfile = logging.FileHandler(path + '/linphonecam.log')
    logger.addHandler(self.logfile)

    signal.signal(signal.SIGINT, self.signal_handler)
    linphone.set_log_handler(self.log_handler)

    self.quit_when_registered = False
    self.core = linphone.Factory.get().create_core(callbacks, path + '/config.rc', None)
    self.path = path

  def signal_handler(self, signal, frame):
    self.core.terminate_all_calls()
    self.quit = True

  def log_handler(self, level, msg):
    method = getattr(logging, level)
    method(msg)

  def registration_state_changed(self, core, proxy, state, message):
    if self.quit_when_registered:
      if state == linphone.RegistrationState.Ok:
        print 'Account configuration OK'
        self.core.config.sync()
        self.quit = True
      elif state == linphone.RegistrationState.Failed:
        print 'Account configuration failure: {0}'.format(message)
        self.quit = True

  #checks for incoming call, then checks calling sip against whitelist, accepts call if found
  def call_state_changed(self, core, call, state, message):
    if state == linphone.CallState.IncomingReceived:
      if call.remote_address.as_string_uri_only() in self.whitelist:
        params = core.create_call_params(call)
        core.accept_call_with_params(call, params)
      else:
        core.decline_call(call, linphone.Reason.Declined)

  #Waits for button press, on press attempts to call given SIP
  def outcall(self):
    while not self.quit:
      b_pressed = False
      if b_pressed and self.core.current_call is None:
        try:
          params = self.core.create_call_params(None)
          params.audio_enabled = True
          params.video_enables = True
          params.audio_multicast_enabled = False
          params.video_multicast_enabled = False
          address = linphone.Address.new(doorbellToAddress)
          self.current_call = self.core.invite_address_with_params(address, params)
          if None is self.current_call:
            logging.error("Error creating call or inviting with params, call aborted")
        except KeyboardInterrupt:
          self.quit = True
          break
      self.core.iterate()



  #Send SIP message to PI, PI snaps picture and sends in return
  def message_received(self, core, room, message):
    sender = message.from_address
    if sender.as_string_uri_only() in self.whitelist:
        capture_file = self.path + '/capture.jpg'
        self.core.take_preview_snapshot(capture_file)
        time.sleep(2)
        content = self.core.create_content()
        content.name = 'capture.jpg'
        capture = open(capture_file, 'rb')
        content.buffer = bytearray(capture.read())
        msg = room.create_file_transfer_message(content)
        room.send_chat_message(msg)

    #Use commmand to configure account:
    #./linphonecam.py configure_account username password
  def configure_sip_account(self, username, password):
    self.quit_when_registered = True

    proxy_cfg = self.core.create_proxy_config()
    proxy_cfg.identity_address = self.core.create_address('sip:{username}@sip.linphone.org'.format(username=username))
    proxy_cfg.server_addr = 'sip:sip.linphone.org;transport=tls'
    proxy_cfg.register_enabled = True
    proxy_cfg.avpf_mode = 1
    proxy_cfg.publish_enabled = True
    self.core.add_proxy_config(proxy_cfg)
    self.core.default_proxy_config = proxy_cfg

    auth_info = self.core.create_auth_info(username, None, password, None, None, 'sip.linphone.org')
    self.core.add_auth_info(auth_info)

  def run(self):
    while not self.quit:
      self.core.iterate()
      time.sleep(0.03)

if __name__ == '__main__':
    #whitelist hold SIP adresses who are allowed to call your PI
  cam = SecurityCamera(whitelist=['whitelistedSIPadress'])
  if len(sys.argv) == 4 and sys.argv[1] == 'configure_account':
    cam.configure_sip_account(sys.argv[2], sys.argv[3])
    cam.run()
  else:
    context = daemon.DaemonContext(files_preserve = [ cam.logfile.stream, ],)
    context.open()
    cam.run()
