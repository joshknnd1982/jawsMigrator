# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Make JAWS sound files playable by NVDA.

NVDA plays sounds with Python's ``wave`` module, which only reads uncompressed
(PCM) files. A few JAWS sounds, and many sounds people add themselves, are
compressed with Microsoft ADPCM or IMA ADPCM. Those are decoded here to 16-bit
PCM so they can be copied and played. Nothing here needs NVDA.
"""

from __future__ import annotations

import os
import shutil
import struct
import wave

from . import safety

WAVE_FORMAT_PCM = 0x0001
WAVE_FORMAT_ADPCM = 0x0002
WAVE_FORMAT_IMA_ADPCM = 0x0011
WAVE_FORMAT_EXTENSIBLE = 0xFFFE
MAX_WAV_BYTES = 25 * 1024 * 1024

_MS_ADAPTATION = (230, 230, 230, 230, 307, 409, 512, 614, 768, 614, 512, 409, 307, 230, 230, 230)
_MS_COEFFICIENTS = ((256, 0), (512, -256), (0, 0), (192, 64), (240, 0), (460, -208), (392, -232))

_IMA_INDEX = (-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8)
_IMA_STEPS = (
	7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97,
	107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
	876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871,
	5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
	27086, 29794, 32767,
)


class WavError(Exception):
	pass


def _clamp16(value: int) -> int:
	return -32768 if value < -32768 else 32767 if value > 32767 else value


def readChunks(data: bytes) -> tuple[dict, bytes]:
	"""Return the ``fmt`` fields and the audio data of a RIFF WAVE file."""
	if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
		raise WavError("not a WAV file")
	offset = 12
	fmt = None
	audio = None
	while offset + 8 <= len(data):
		chunkId = data[offset : offset + 4]
		size = struct.unpack_from("<I", data, offset + 4)[0]
		body = data[offset + 8 : offset + 8 + size]
		if chunkId == b"fmt " and len(body) >= 16:
			formatTag, channels, rate, byteRate, blockAlign, bits = struct.unpack_from("<HHIIHH", body, 0)
			fmt = {
				"format": formatTag,
				"channels": channels,
				"rate": rate,
				"blockAlign": blockAlign,
				"bits": bits,
				"extra": body[18:] if len(body) > 18 else b"",
			}
			if formatTag == WAVE_FORMAT_EXTENSIBLE and len(body) >= 26:
				fmt["format"] = struct.unpack_from("<H", body, 24)[0]
		elif chunkId == b"data":
			audio = body
		offset += 8 + size + (size & 1)
	if fmt is None or audio is None:
		raise WavError("the WAV file has no format or no sound")
	return fmt, audio


def _decodeMsAdpcm(fmt: dict, audio: bytes) -> bytes:
	channels = fmt["channels"]
	blockAlign = fmt["blockAlign"]
	coefficients = list(_MS_COEFFICIENTS)
	extra = fmt["extra"]
	if len(extra) >= 4:
		count = struct.unpack_from("<H", extra, 2)[0]
		if len(extra) >= 4 + count * 4 and count:
			coefficients = [struct.unpack_from("<hh", extra, 4 + i * 4) for i in range(count)]
	output = bytearray()
	headerSize = 7 * channels
	for blockStart in range(0, len(audio), blockAlign):
		block = audio[blockStart : blockStart + blockAlign]
		if len(block) < headerSize:
			break
		predictors = list(block[0:channels])
		deltas = list(struct.unpack_from(f"<{channels}h", block, channels))
		sample1 = list(struct.unpack_from(f"<{channels}h", block, channels * 3))
		sample2 = list(struct.unpack_from(f"<{channels}h", block, channels * 5))
		coefs = [coefficients[min(p, len(coefficients) - 1)] for p in predictors]
		frames = [[sample2[c] for c in range(channels)], [sample1[c] for c in range(channels)]]
		nibbles = []
		for byte in block[headerSize:]:
			nibbles.append(byte >> 4)
			nibbles.append(byte & 0x0F)
		channel = 0
		frame = []
		for nibble in nibbles:
			signed = nibble - 16 if nibble & 0x08 else nibble
			coef1, coef2 = coefs[channel]
			predicted = (sample1[channel] * coef1 + sample2[channel] * coef2) >> 8
			value = _clamp16(predicted + signed * deltas[channel])
			sample2[channel] = sample1[channel]
			sample1[channel] = value
			deltas[channel] = max(16, (_MS_ADAPTATION[nibble] * deltas[channel]) >> 8)
			frame.append(value)
			channel += 1
			if channel == channels:
				frames.append(frame)
				frame = []
				channel = 0
		for values in frames:
			output += struct.pack(f"<{channels}h", *values)
	return bytes(output)


def _decodeImaAdpcm(fmt: dict, audio: bytes) -> bytes:
	channels = fmt["channels"]
	blockAlign = fmt["blockAlign"]
	output = bytearray()
	for blockStart in range(0, len(audio), blockAlign):
		block = audio[blockStart : blockStart + blockAlign]
		if len(block) < 4 * channels:
			break
		predictors = []
		indexes = []
		for c in range(channels):
			sample, index = struct.unpack_from("<hB", block, c * 4)
			predictors.append(sample)
			indexes.append(min(88, index))
		perChannel = [[predictors[c]] for c in range(channels)]
		data = block[4 * channels :]
		for chunkStart in range(0, len(data) - 4 * channels + 1, 4 * channels):
			for c in range(channels):
				word = data[chunkStart + c * 4 : chunkStart + c * 4 + 4]
				for byte in word:
					for nibble in (byte & 0x0F, byte >> 4):
						step = _IMA_STEPS[indexes[c]]
						diff = step >> 3
						if nibble & 1:
							diff += step >> 2
						if nibble & 2:
							diff += step >> 1
						if nibble & 4:
							diff += step
						if nibble & 8:
							diff = -diff
						predictors[c] = _clamp16(predictors[c] + diff)
						indexes[c] = min(88, max(0, indexes[c] + _IMA_INDEX[nibble]))
						perChannel[c].append(predictors[c])
		length = min(len(samples) for samples in perChannel)
		for i in range(length):
			output += struct.pack(f"<{channels}h", *(perChannel[c][i] for c in range(channels)))
	return bytes(output)


def isPlayable(path: str) -> bool:
	"""Whether NVDA can play the file as it is."""
	try:
		with wave.open(path, "rb") as sound:
			return sound.getnframes() >= 0
	except Exception:
		return False


def copyPlayable(source: str, destination: str) -> str:
	"""Copy a WAV file so that NVDA can play it, decoding ADPCM when needed.

	Returns ``"copied"`` or ``"converted"``. Raises WavError when the file can't be used.
	"""
	safety.checkWritable(destination)
	if os.path.getsize(source) > MAX_WAV_BYTES:
		raise WavError("the sound file is larger than 25 MB")
	os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
	if isPlayable(source):
		shutil.copyfile(source, destination)
		return "copied"
	with open(source, "rb") as stream:
		data = stream.read()
	fmt, audio = readChunks(data)
	if fmt["format"] == WAVE_FORMAT_ADPCM:
		pcm = _decodeMsAdpcm(fmt, audio)
	elif fmt["format"] == WAVE_FORMAT_IMA_ADPCM:
		pcm = _decodeImaAdpcm(fmt, audio)
	else:
		raise WavError(f"sound format {fmt['format']} is not supported")
	temporary = destination + ".tmp"
	with wave.open(temporary, "wb") as out:
		out.setnchannels(fmt["channels"])
		out.setsampwidth(2)
		out.setframerate(fmt["rate"])
		out.writeframes(pcm)
	os.replace(temporary, destination)
	return "converted"
