#!/usr/bin/env python
#-*- coding: utf-8 -*-
#
# Started from : https://github.com/SpotlightKid/python-rtmidi
# https://github.com/SpotlightKid/python-rtmidi/tree/master/examples/midi2command
#
# midi2command.py
#
# Execute external commands when specific MIDI messages are received.

# configuration (in YAML syntax)::
#
#   - name: My Backingtracks
#     description: Play audio file with filename matching <data1>-playback.mp3
#       when program change on channel 16 is received
#     status: programchange
#     channel: 16
#     command: plaympeg %(data1)03i-playback.mp3
#   - name: My Lead Sheets
#     description: Open PDF with filename matching <data2>-sheet.pdf
#       when control change 14 on channel 16 is received
#     status: controllerchange
#     channel: 16
#     data: 14
#     command: evince %(data2)03i-sheet.pdf
#
#

import argparse
import logging
import shlex
import subprocess
import sys
import time
import picamera
import uuid
import random

from os.path import exists

try:
    from functools import lru_cache
except ImportError:
    # Python < 3.2
	lru_cache = lambda func: func

import yaml

import rtmidi
from rtmidi.midiutil import open_midiport
from rtmidi.midiconstants import *

log = logging.getLogger('midi2command')
STATUS_MAP = {
    'noteon': NOTE_ON,
    'noteoff': NOTE_OFF,
    'programchange': PROGRAM_CHANGE,
    'controllerchange': CONTROLLER_CHANGE,
    'pitchbend': PITCH_BEND,
    'polypressure': POLY_PRESSURE,
    'channelpressure': CHANNEL_PRESSURE
}

class InternalCommand(object):
    def __init__(self, args=None, data1=None, data2=None):
    
        for arg in args:
            print arg
        print data1
        print data2

class Command(object):
    def __init__(self, name='', description='', status=0xB0, channel=None,
            data=None, command=None):
        self.name = name
        self.description = description
        self.status = status
        self.channel = channel
        self.command = command

        if data is None or isinstance(data, int):
            self.data = data
        elif hasattr(data, 'split'):
            self.data = map(int, data.split())
        else:
            raise TypeError("Could not parse 'data' field.")

class MidiInputHandler(object):
    def __init__(self, port, config, camera):
        self.port = port
        self._wallclock = time.time()
        self.commands = dict()
        self.load_config(config)
        if camera is not None:
            self.camera = camera

    def __call__(self, event, data=None):
        event, deltatime = event
        self._wallclock += deltatime
        log.debug("[%s] @%0.6f %r", self.port, self._wallclock, event)

        if event[0] < 0xF0:
            channel = (event[0] & 0xF) + 1
            status = event[0] & 0xF0
        else:
            status = event[0]
            channel = None

        data1 = data2 = None
        num_bytes = len(event)

        if num_bytes >= 2:
            data1 = event[1]
        if num_bytes >= 3:
            data2 = event[2]

        # Look for matching command definitions
        # XXX: use memoize cache here
        if status in self.commands:
            for cmd in self.commands[status]:
                if channel is not None and cmd.channel != channel:
                    continue

                found = False
                if num_bytes == 1 or cmd.data is None:
                    found = True
                elif isinstance(cmd.data, int) and cmd.data == data1:
                    found = True
                elif (isinstance(cmd.data, (list, tuple)) and
                        cmd.data[0] == data1 and cmd.data[1] == data2):
                    found = True

                if found:
                    cmdline = cmd.command % dict(
                        channel=channel,
                        data1=data1,
                        data2=data2,
                        status=status)
                    self.do_command(cmdline, data1, data2)
            else:
                return

    def do_command(self, cmdline, data1, data2):
        try:
            args = shlex.split(cmdline)
            if args[0] == "internal":
                log.info("Calling INTERNAL command: %s", cmdline)
                self.do_internal_command(args, data1, data2)
            else:
                log.info("Calling EXTERNAL command: %s", cmdline)
                self.do_external_command(args)
        except:
            log.exception("Error calling external/internal command.")

    def do_external_command(self, args):
        subprocess.Popen(args)

    def do_internal_command(self, args, data1, data2):
        #ic = InternalCommand(args, data1, data2)
        if args[1] == "camera" and self.camera is not None:
            self.camera.execute(data1, data2)

    def load_config(self, filename):
        if not exists(filename):
            raise IOError("Config file not found: %s" % filename)

        with open(filename) as patch:
            data = yaml.load(patch)

        for cmdspec in data:
            print(cmdspec)
            try:
                if isinstance(cmdspec, dict) and 'command' in cmdspec:
                    cmd = Command(**cmdspec)
                elif len(cmdspec) >= 2:
                    cmd = Command(*cmdspec)
            except (TypeError, ValueError) as exc:
                log.debug(cmdspec)
                raise IOError("Invalid command specification: %s" % exc)
            else:
                status = STATUS_MAP.get(cmd.status.strip().lower())

                if status is None:
                    try:
                        int(cmd.status)
                    except:
                        log.error("Unknown status '%s'. Ignoring command",
                            cmd.status)

                log.debug("Config: %s\n%s\n", cmd.name, cmd.description)
                self.commands.setdefault(status, []).append(cmd)

class Camera(object):
    def __init__(self):

        print "Initializing camera..."
        self.camera = picamera.PiCamera()
        #self.effects = dict({0:"none", 1:"sketch", 2:"negative", 3:"colorswap" })
        self.effects = dict({0:"none", 1:"negative", 2:"solarize", 3:"sketch", 4:"denoise", 
            5:"emboss", 6:"oilpaint", 7:"hatch", 8:"gpen", 9:"pastel", 10:"watercolor", 11:"film", 
            12:"blur", 13:"saturation", 14:"colorswap",15:"washedout", 16:"posterise", 17:"colorpoint", 
            18:"colorbalance", 19:"cartoon", 20:"deinterlace1", 21:"deinterlace2" })
        self.rotation = dict({0:0, 1:90, 2:180, 3:270, 99:-1 })
        self.camera.image_effect = 'none'
        self.camera.zoom = (0.0,0.0,1.0,1.0)
        self.index = -1

    def start_preview(self):
        self.camera.image_effect = 'none'
        self.camera.zoom = (0.0,0.0,1.0,1.0)
        self.camera.start_preview() 

    def stop_preview(self):
        self.camera.stop_preview()

    def zoom_width(self, value):
        h = self.camera.zoom[3]
        w = float(value)/100
        self.camera.zoom = (0.0,0.0,w,h)

    def zoom_height(self, value):
        w = self.camera.zoom[2]
        h = float(value)/100
        self.camera.zoom = (0.0,0.0,w,h)

    def zoom_x(self, value):
        z = self.camera.zoom
        x = float(value)/100
        zoom = (x,z[1],x,z[3])
        #print zoom
        self.camera.zoom = zoom

    def zoom_y(self, value):
        z = self.camera.zoom
        x = float(value)/100
        zoom = (z[0],x,z[2],x)
        #print zoom
        self.camera.zoom = zoom
        
    def flip(self):
        self.camera.vflip = bool(random.getrandbits(1))
        self.camera.hflip = bool(random.getrandbits(1))

    def capture(self):
        filename = str(uuid.uuid4()) + '.jpg'
        self.camera.capture(filename)

    def set_rotation(self, index):
        if index != 99:
            self.camera.rotation = self.rotation[index]
        else:
            if self.camera.rotation == 270:
                self.camera.rotation = 0
            else:
                self.camera.rotation += 90

    def set_effect(self, index):
        self.camera.image_effect = 'none'
        if index >= 0 and index <= 21:
            self.camera.image_effect = self.effects[index]
        else:
            self.index += 1
            if self.index > 21:
                self.index = 0
            self.camera.image_effect = self.effects[self.index]

    def execute(self, data1, data2):
        if data1 == 20:
            if data2 == 1:
                self.start_preview()
            elif data2 == 2:
                self.stop_preview()
            else:
                pass
        elif data1 == 21:
            self.set_effect(data2)
        elif data1 == 22:
            self.set_rotation(data2)
        elif data1 == 23:
            self.capture()
        elif data1 == 25:
            self.zoom_width(data2)
        elif data1 == 26:
            self.zoom_height(data2)
        elif data1 == 27:
            self.zoom_x(data2)
        elif data1 == 28:
            self.zoom_y(data2)
        elif data1 == 29:
            self.flip()
        else:
            pass
        
    def dispose(self):
        self.camera.stop_preview()
        self.camera.close()
        del self.camera


def main(args=None):
#    """Main program function.
#
#    Parses command line (parsed via ``args`` or from ``sys.argv``), detects
#    and optionally lists MIDI input ports, opens given MIDI input port,
#    and attaches MIDI input handler object.
#
#    """

    parser = argparse.ArgumentParser(description='midi2command')

    parser.add_argument('-p',  '--port', dest='port', 
        help='MIDI input port name or number (default: open virtual input)')

    parser.add_argument('-v',  '--verbose', action="store_true",
        help='verbose output')

    parser.add_argument('-d', '--device', dest="device",
            help='device name : default = MidiDeviceBase')

    parser.add_argument('-c', '--camera', action="store_true",
        help='enable camera')

    parser.add_argument(dest='config', metavar="CONFIG",
        help='Configuration file in YAML syntax.')

    args = parser.parse_args(args if args is not None else sys.argv[1:])

    logging.basicConfig(format="%(name)s: %(levelname)s - %(message)s",
		level=logging.DEBUG if args.verbose else logging.WARNING)

    try:
        midiin1, port_name = open_midiport(args.port, use_virtual=False)
    except (EOFError, KeyboardInterrupt):
        sys.exit()

    if args.camera:
        log.debug("Starting RPI Camera Module...")
        camera = Camera()
    else:
        camera = None

    log.debug("Attaching MIDI input callback handler.")
    midiin1.set_callback(MidiInputHandler(port_name, args.config, camera))

    log.info("Entering main loop. Press Control-C to exit.")
    try:
        # just wait for keyboard interrupt in main thread
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('')
    finally:
        midiin1.close_port()
        del midiin1
        if camera is not None:
            camera.dispose()
            del camera

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]) or 0)