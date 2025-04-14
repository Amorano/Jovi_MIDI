"""
Device -- MIDI

    type 0 (single track): all messages are saved in one track
    type 1 (synchronous): all tracks start at the same time
    type 2 (asynchronous): each track is independent of the others
"""

import time
import threading
from enum import Enum
from math import isclose
from queue import Queue, Empty
from typing import List, Tuple

from cozy_comfyui import \
    EnumConvertType, \
    logger, \
    deep_merge, parse_param

from cozy_comfyui.node import \
    CozyBaseNode

try:
    import mido
    from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo
except:
    logger.warning("MISSING MIDI SUPPORT")

from comfy.utils import ProgressBar

# ==============================================================================
# === ENUMERATION ===
# ==============================================================================

class MIDINoteOnFilter(Enum):
    NOTE_OFF = 0
    NOTE_ON = 1
    IGNORE = -1

# ==============================================================================
# === SUPPORT ===
# ==============================================================================

def midi_save() -> None:
    mid = MidiFile()
    track = MidiTrack()
    mid.tracks.append(track)

    track.append(MetaMessage('key_signature', key='Dm'))
    track.append(MetaMessage('set_tempo', tempo=bpm2tempo(120)))
    track.append(MetaMessage('time_signature', numerator=6, denominator=8))

    track.append(Message('program_change', program=12, time=10))
    track.append(Message('note_on', channel=2, note=60, velocity=64, time=1))
    track.append(Message('note_off', channel=2, note=60, velocity=100, time=2))

    track.append(MetaMessage('end_of_track'))
    mid.save('new_song.mid')

def midi_load(fn) -> None:
    mid = MidiFile(fn, clip=True)
    logger.debug(mid)
    for msg in mid.tracks[0]:
        logger.debug(msg)

def midi_device_names() -> List[str]:
    try:
        return mido.get_input_names()
    except Exception as e:
        logger.error("midi devices are offline")
    return []

# ==============================================================================
# === CLASS - SUPPORT ===
# ==============================================================================

class MIDIServerThread(threading.Thread):
    def __init__(self, q_in, device, callback, *arg, **kw) -> None:
        super().__init__(*arg, **kw)
        self.__q_in = q_in
        self.__device = device
        self.__callback = callback

    def run(self) -> None:
        old_device = None
        while True:
            logger.debug(f"waiting for device")
            while True:
                try:
                    if (cmd := self.__q_in.get_nowait()):
                        old_device = self.__device = cmd
                        break
                except Empty as _:
                    time.sleep(0.01)
                except Exception as e:
                    logger.error(str(e))
                    pass

            # device is not null....
            logger.debug(f"starting device loop {self.__device}")

            failure = 0
            try:
                with mido.open_input(self.__device, callback=self.__callback):
                    while True:
                        if self.__device != old_device:
                            logger.debug(f"device loop ended {old_device}")
                            break
                        time.sleep(0.01)
            except Exception as e:
                if (failure := failure + 1) > 3:
                    logger.exception(e)
                    return
                logger.error(e)
                time.sleep(2)

class MIDIMessage:
    """Snap shot of a message from Midi device."""
    def __init__(self, note_on:bool, channel:int, control:int, note:int, value:int) -> None:
        self.note_on = note_on
        self.channel = channel
        self.control = control
        self.note = note
        self.value = value
        self.normal: float = value / 127.

    @property
    def flat(self) -> Tuple[bool, int, int, int, float, float]:
        return (self.note_on, self.channel, self.control, self.note, self.value, self.normal,)

    def __str__(self) -> str:
        return f"{self.note_on}, {self.channel}, {self.control}, {self.note}, {self.value}, {self.normal}"

# ==============================================================================
# === CLASS ===
# ==============================================================================

class MIDIHeader(CozyBaseNode):
    RETURN_TYPES = ('JMIDIMSG', 'BOOLEAN', 'INT', 'INT', 'INT', 'FLOAT', 'FLOAT', )
    RETURN_NAMES = ("MIDI", "ON", "CHANNEL", "CONTROL", "NOTE", "VALUE", "NORMALIZE", )
    OUTPUT_TOOLTIPS = (
        "MIDI bus that contains the full MIDI message",
        "The state of the note -- either `ON` or `OFF`",
        "MIDI channel sent in the MIDI message",
        "The control number sent in the MIDI message",
        "Note value (0-127) sent in the MIDI message",
        "If this was a control messge, the control value (0-127) sent in the MIDI message",
        "If this was a control messge, the control value normalized to 0-1",
    )

class MIDIMessageNode(MIDIHeader):
    NAME = "MIDI MESSAGE"
    SORT = 10
    DESCRIPTION = """
Processes MIDI messages received from an external MIDI controller or device. It accepts MIDI messages as input and returns various attributes of the MIDI message, including whether the message is valid, the MIDI channel, control number, note number, value, and normalized value. This node is useful for integrating MIDI control into creative projects, allowing users to respond to MIDI input in real-time.
"""

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        d = super().INPUT_TYPES()
        return deep_merge(d, {
            "optional": {
                "MIDI": ('JMIDIMSG', {"default": None})
            }
        })

    def run(self, **kw) -> Tuple[object, bool, int, int, int, float, float]:
        message: MIDIMessage = parse_param(kw, "MIDI", EnumConvertType.ANY, [None])
        results = []
        pbar = ProgressBar(len(message))
        for idx, message in enumerate(message):
            if message is None:
                results.append([False, -1, -1, -1, -1, -1])
            else:
                results.append([message, *message.flat])
            pbar.update_absolute(idx)
        return list(zip(*results))

class MIDIReaderNode(MIDIHeader):
    NAME = "MIDI READER"
    SORT = 5
    DEVICES = midi_device_names()
    CHANGED = False
    DESCRIPTION = """
Captures MIDI messages from an external MIDI device or controller. It monitors MIDI input and provides information about the received MIDI messages, including whether a note is being played, the MIDI channel, control number, note number, value, and a normalized value. This node is essential for integrating MIDI control into various applications, such as music production, live performances, and interactive installations.
"""

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        d = super().INPUT_TYPES()
        return deep_merge(d, {
            "optional": {
                "DEVICE" : (cls.DEVICES, {"default": cls.DEVICES[0] if len(cls.DEVICES) > 0 else None})
            }
        })

    @classmethod
    def IS_CHANGED(cls, **kw) -> float:
        if cls.CHANGED:
            cls.CHANGED = False
            return float('nan')

    def __init__(self, *arg, **kw) -> None:
        super().__init__(*arg, **kw)
        self.__q_in = Queue()
        self.__device = None
        self.__note = 0
        self.__note_on = False
        self.__channel = 0
        self.__control = 0
        self.__value = 0
        self.__SERVER = MIDIServerThread(self.__q_in, None, self.__process, daemon=True)
        self.__SERVER.start()

    def __process(self, data) -> None:
        MIDIReaderNode.CHANGED = True
        self.__channel = data.channel
        self.__note = 0
        self.__control = 0
        self.__note_on = False
        match data.type:
            case "control_change":
                # control=8 value=14 time=0
                self.__control = data.control
                self.__value = data.value
            case "note_on":
                self.__note = data.note
                self.__note_on = True
                self.__value = data.velocity
            case "note_off":
                self.__note = data.note
                self.__value = data.velocity

    def run(self, **kw) -> Tuple[MIDIMessage, bool, int, int, int, int, float]:
        device = parse_param(kw, "DEVICE", EnumConvertType.STRING, None)[0]
        if device != self.__device:
            self.__q_in.put(device)
            self.__device = device
        normalize = self.__value / 127.
        msg = MIDIMessage(self.__note_on, self.__channel, self.__control, self.__note, self.__value)
        return msg, self.__note_on, self.__channel, self.__control, self.__note, self.__value, normalize,

class MIDIFilterNode(CozyBaseNode):
    NAME = "MIDI FILTER"
    RETURN_TYPES = ("JMIDIMSG", "BOOLEAN", )
    RETURN_NAMES = ("MIDI", "TRIGGER",)
    OUTPUT_TOOLTIPS = (
        "The amount of blurriness (0->1.0) of the input image.",
        "The amount of blurriness (0->1.0) of the input image.",
    )
    SORT = 20
    EPSILON = 1e-6
    DESCRIPTION = """
Provides advanced filtering capabilities for MIDI messages based on various criteria, including MIDI mode (such as note on or note off), MIDI channel, control number, note number, value, and normalized value. It allows you to filter out unwanted MIDI events and selectively process only the desired ones. This node offers flexibility in MIDI data processing, enabling precise control over which MIDI messages are passed through for further processing.
"""

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        d = super().INPUT_TYPES()
        return deep_merge(d, {
            "optional": {
                "MIDI": ('JMIDIMSG', {"default": None}),
                "MODE": (MIDINoteOnFilter._member_names_, {"default": MIDINoteOnFilter.IGNORE.name}),
                "CHANNEL": ("STRING", {"default": ""}),
                "CONTROL": ("STRING", {"default": ""}),
                "NOTE": ("STRING", {"default": ""}),
                "VALUE": ("STRING", {"default": ""}),
                "NORMALIZE": ("STRING", {"default": ""}),
            }
        })

    def __filter(self, data:int, value:str) -> bool:
        """Parse strings with number ranges into number ranges.
            Supports:
                - Single numbers: "1, 2" (equals)
                - Closed ranges: "5-10" (between inclusive)
                - Open ranges: "-100" (less than or equal to 100)
                - Open ranges: "50-" (greater than or equal to 50)

            1, 5-10, 2
            Would check == 1, == 2 and 5 <= x <= 10
        """
        value = value.strip()
        if not value:
            return True

        ranges = value.split(',')
        for item in ranges:
            item = item.strip()

            if item.startswith('-'):
                try:
                    bound = float(item[1:])
                    if data <= bound:
                        return True
                except ValueError:
                    continue
            elif item.endswith('-'):
                try:
                    bound = float(item[:-1])
                    if data >= bound:
                        return True
                except ValueError:
                    continue
            elif '-' in item:
                try:
                    a, b = map(float, item.split('-'))
                    if a <= data <= b:
                        return True
                except ValueError:
                    continue
            # Handle single number
            else:
                try:
                    if isclose(data, float(item)):
                        return True
                except ValueError:
                    continue
        return False

    def run(self, **kw) -> Tuple[bool]:
        message: MIDIMessage = kw.get("MIDI", None)
        note_on: str = parse_param(kw, "MODE", MIDINoteOnFilter, MIDINoteOnFilter.IGNORE.name)[0]
        chan: str = parse_param(kw, "CHANNEL", EnumConvertType.STRING, "")[0]
        ctrl: str = parse_param(kw, "CONTROL", EnumConvertType.STRING, "")[0]
        note: str = parse_param(kw, "NOTE", EnumConvertType.STRING, "")[0]
        value: str = parse_param(kw, "VALUE", EnumConvertType.STRING, "")[0]
        normal: str = parse_param(kw, "NORMALIZE", EnumConvertType.STRING, "")[0]

        if note_on != MIDINoteOnFilter.IGNORE:
            if note_on == MIDINoteOnFilter.NOTE_ON and not message.note_on:
                return message, False,
            if note_on == MIDINoteOnFilter.NOTE_OFF and message.note_on:
                return message, False,
        if not self.__filter(message.channel, chan):
            return message, False,
        if not self.__filter(message.control, ctrl):
            return message, False,
        if not self.__filter(message.note, note):
            return message, False,
        if not self.__filter(message.value, value):
            return message, False,
        if not self.__filter(message.normal, normal):
            return message, False,
        return message, True,

class MIDIFilterEZNode(CozyBaseNode):
    NAME = "MIDI FILTER EZ"
    RETURN_TYPES = ("JMIDIMSG", "BOOLEAN", )
    RETURN_NAMES = ("MIDI", "TRIGGER",)
    OUTPUT_TOOLTIPS = (
        "The amount of blurriness (0->1.0) of the input image.",
        "The amount of blurriness (0->1.0) of the input image.",
    )
    SORT = 25
    DESCRIPTION = """
Filter MIDI messages based on various criteria, including MIDI mode (such as note on or note off), MIDI channel, control number, note number, value, and normalized value. This node is useful for processing MIDI input and selectively passing through only the desired messages. It helps simplify MIDI data handling by allowing you to focus on specific types of MIDI events.
"""

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        d = super().INPUT_TYPES()
        return deep_merge(d, {
            "optional": {
                "MIDI": ('JMIDIMSG', {"default": None}),
                "MODE": (MIDINoteOnFilter._member_names_, {"default": MIDINoteOnFilter.IGNORE.name}),
                "CHANNEL": ("INT", {"default": -1, "mij": -1, "maj": 127}),
                "CONTROL": ("INT", {"default": -1, "mij": -1, "maj": 127}),
                "NOTE": ("INT", {"default": -1, "mij": -1, "maj": 127}),
                "VALUE": ("INT", {"default": -1, "mij": -1, "maj": 127}),
            }
        })

    def run(self, **kw) -> Tuple[MIDIMessage, bool]:

        message: MIDIMessage = parse_param(kw, "MIDI", EnumConvertType.ANY, [None])[0]
        note_on = parse_param(kw, "MODE", MIDINoteOnFilter, MIDINoteOnFilter.IGNORE.name)[0]
        chan = parse_param(kw, "CHANNEL", EnumConvertType.INT, -1)[0]
        ctrl = parse_param(kw, "CONTROL", EnumConvertType.INT, -1)[0]
        note = parse_param(kw, "NOTE", EnumConvertType.INT, -1)[0]
        value = parse_param(kw, "VALUE", EnumConvertType.INT, -1)[0]

        if note_on != MIDINoteOnFilter.IGNORE:
            if note_on == MIDINoteOnFilter.NOTE_ON and not message.note_on:
                return message, False,
            if note_on == MIDINoteOnFilter.NOTE_OFF and message.note_on:
                return message, False,
        if chan > -1 and message.channel != chan:
            return message, False,
        if ctrl > -1 and message.control != ctrl:
            return message, False,
        if note > -1 and message.note != note:
            return message, False,
        if value > -1 and message.value != value:
            return message, False,
        return message, True,

class MIDILoader(CozyBaseNode):
    NAME = "MIDI LOADER"
    RETURN_TYPES = ("JMIDIMSG", "BOOLEAN", )
    RETURN_NAMES = ("MIDI", "TRIGGER",)
    SORT = 105
    DESCRIPTION = """
Load MIDI files and convert their events into a ComfyUI parameter list.
"""
