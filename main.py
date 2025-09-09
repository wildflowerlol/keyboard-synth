import os
import sys
import numpy as np
import pygame
from dewa import Block, Sine, Square, Sawtooth

# --- WAVETABLE GENERATION WITH DEWA ---
def dewa_generate_wavetable(length, waveform, frequency=440, sample_rate=44100):
    duration_seconds = length / sample_rate
    block = Block(duration=length)
    if waveform == "sine":
        block += Sine(sample_rate / frequency)
    elif waveform == "triangle":
        block += Sawtooth(sample_rate / frequency, 0.5)
    elif waveform == "square":
        block += Square(sample_rate / frequency)
    elif waveform == "sawtooth":
        block += Sawtooth(sample_rate / frequency)
    else:
        raise ValueError(f"Unknown waveform type: {waveform}")
    wavetable = block.samples[:length]
    wavetable = wavetable / np.max(np.abs(wavetable))
    return wavetable.astype(np.float32)

# --- WAVETABLE SYNTH CODE (unchanged) ---
class LinearInterpolator():
    def __call__(self, values, index):
        low = int(index)
        high = int(np.ceil(index))
        if low == high:
            return values[low]
        return (index - low) * values[high % values.shape[0]] + (high - index) * values[low]

class WavetableOscillator:
    def __init__(self, wavetable, sampling_rate, interpolator):
        self.wavetable = wavetable
        self.sampling_rate = sampling_rate
        self.interpolator = interpolator
        self.wavetable_index = 0.0
        self.__frequency = 0

    def get_sample(self):
        sample = self.interpolator(self.wavetable, self.wavetable_index)
        self.wavetable_index = (self.wavetable_index + self.wavetable_increment) % self.wavetable.shape[0]
        return sample

    @property
    def frequency(self):
        return self.__frequency

    @frequency.setter
    def frequency(self, value):
        self.__frequency = value
        self.wavetable_increment = self.wavetable.shape[0] * self.frequency / self.sampling_rate
        if self.frequency <= 0:
            self.wavetable_index = 0.0

class Voice:
    def __init__(self, sampling_rate, gain=-20):
        self.sampling_rate = sampling_rate
        self.gain = gain
        self.oscillators = []

    def synthesize(self, frequency, duration_seconds):
        buffer = np.zeros((int(duration_seconds * self.sampling_rate),))
        if np.isscalar(frequency):
            frequency = np.ones_like(buffer) * frequency
        for i in range(len(buffer)):
            for oscillator in self.oscillators:
                oscillator.frequency = frequency[i]
                buffer[i] += oscillator.get_sample()
        amplitude = 10 ** (self.gain / 20)
        buffer *= amplitude
        buffer = fade_in_out(buffer)
        return buffer

def fade_in_out(signal, fade_length=1000):
    fade_length = min(fade_length, len(signal)//2)
    fade_out_envelope = (1 - np.cos(np.linspace(0, np.pi, fade_length))) * 0.5
    signal[-fade_length:] *= fade_out_envelope
    return signal

# --- KEYBOARD MAPPINGS & UTILITIES (unchanged) ---
KEY_TO_NOTE = {
    pygame.K_a: 0,  # C
    pygame.K_s: 2,  # D
    pygame.K_d: 4,  # E
    pygame.K_f: 5,  # F
    pygame.K_g: 7,  # G
    pygame.K_h: 9,  # A
    pygame.K_j: 11, # B
    pygame.K_k: 12, # C (next octave)
}
BLACK_KEY_TO_NOTE = {
    pygame.K_w: 1,   # C#
    pygame.K_e: 3,   # D#
    pygame.K_t: 6,   # F#
    pygame.K_y: 8,   # G#
    pygame.K_u: 10,  # A#
}
OCTAVE_KEYS = {
    pygame.K_z: -1,
    pygame.K_x: 1,
}
WAVEFORM_KEYS = {
    pygame.K_1: "sine",
    pygame.K_2: "triangle",
    pygame.K_3: "square",
    pygame.K_4: "sawtooth",
}
WAVEFORM_DISPLAY = {
    "sine": "SINE",
    "triangle": "TRIANGLE",
    "square": "SQUARE",
    "sawtooth": "SAWTOOTH"
}

def midi_to_freq(midi_note):
    return 440.0 * 2 ** ((midi_note - 69) / 12)

def make_sound_obj(note_audio):
    stereo_audio = np.stack([note_audio, note_audio], axis=-1)
    return pygame.sndarray.make_sound((stereo_audio * 32767).astype(np.int16))

def show_instruction_screen(screen):
    font = pygame.font.SysFont("Arial", 28)
    smallfont = pygame.font.SysFont("Arial", 20)
    screen.fill((20, 20, 20))
    lines = [
        "Hold A S D F G H J K for white notes (C D E F G A B C)",
        "Hold W E   T Y U for black notes (C# D#   F# G# A#)",
        "Z/X to change octave, 1/2/3/4 to change waveform (sine/triangle/square/sawtooth), ESC to exit.",
        "",
        "Press any key to continue..."
    ]
    y = 80
    for i, line in enumerate(lines):
        text = font.render(line, True, (240,240,240) if i<3 else (180,180,180))
        rect = text.get_rect(center=(screen.get_width()//2, y + i*60))
        screen.blit(text, rect)
    pygame.display.flip()
    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN or event.type == pygame.MOUSEBUTTONDOWN:
                waiting = False
            elif event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

def get_piano_img():
    cwd = os.path.dirname(os.path.abspath(__file__))
    piano_path = os.path.join(cwd, "Piano.png")
    if not os.path.exists(piano_path):
        raise FileNotFoundError("Could not find Piano.png in the script directory.")
    return piano_path

def main():
    pygame.init()
    sampling_rate = 44100
    wavetable_size = 64
    base_octave = 3
    current_octave = base_octave

    # --- DEWA WAVETABLES ---
    wavetables = {
        "sine": dewa_generate_wavetable(wavetable_size, "sine", 440, sampling_rate),
        "triangle": dewa_generate_wavetable(wavetable_size, "triangle", 440, sampling_rate),
        "square": dewa_generate_wavetable(wavetable_size, "square", 440, sampling_rate),
        "sawtooth": dewa_generate_wavetable(wavetable_size, "sawtooth", 440, sampling_rate),
    }
    current_waveform = "sine"
    synth = Voice(sampling_rate, gain=-10)
    synth.oscillators = [WavetableOscillator(wavetables[current_waveform], sampling_rate, LinearInterpolator())]

    pygame.mixer.init(frequency=sampling_rate, size=-16, channels=2, buffer=1024)
    screen = pygame.display.set_mode((960, 540)) # 16:9

    # Instruction page
    show_instruction_screen(screen)

    # Main piano screen
    piano_img = pygame.image.load(get_piano_img())
    piano_rect = piano_img.get_rect()
    scale_ratio = min(
        screen.get_width()/piano_rect.width,
        screen.get_height()/piano_rect.height
    ) * 0.95
    piano_img = pygame.transform.smoothscale(
        piano_img,
        (int(piano_rect.width*scale_ratio), int(piano_rect.height*scale_ratio))
    )
    piano_rect = piano_img.get_rect(center=(screen.get_width()//2, screen.get_height()//2))

    font = pygame.font.SysFont("Arial", 32, bold=True)
    held_notes = {}

    running = True
    while running:
        screen.fill((30,30,30))
        screen.blit(piano_img, piano_rect)
        octave_text = font.render(f"OCTAVE : {current_octave}", True, (255,255,255))
        screen.blit(octave_text, (20, 18))
        wf_text = font.render(f"WAVE : {WAVEFORM_DISPLAY[current_waveform]}", True, (255,255,255))
        wf_rect = wf_text.get_rect(topright=(screen.get_width()-20, 18))
        screen.blit(wf_text, wf_rect)
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN:
                if event.key in OCTAVE_KEYS:
                    current_octave += OCTAVE_KEYS[event.key]
                    current_octave = max(1, min(7, current_octave))
                elif event.key in WAVEFORM_KEYS:
                    current_waveform = WAVEFORM_KEYS[event.key]
                    synth.oscillators = [WavetableOscillator(
                        wavetables[current_waveform], sampling_rate, LinearInterpolator())]
                elif event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in KEY_TO_NOTE and event.key not in held_notes:
                    note_number = 12 * current_octave + KEY_TO_NOTE[event.key]
                    freq = midi_to_freq(note_number)
                    note_audio = synth.synthesize(frequency=freq, duration_seconds=5)
                    sound = make_sound_obj(note_audio)
                    sound.play(fade_ms=5)
                    held_notes[event.key] = sound
                elif event.key in BLACK_KEY_TO_NOTE and event.key not in held_notes:
                    note_number = 12 * current_octave + BLACK_KEY_TO_NOTE[event.key]
                    freq = midi_to_freq(note_number)
                    note_audio = synth.synthesize(frequency=freq, duration_seconds=5)
                    sound = make_sound_obj(note_audio)
                    sound.play(fade_ms=5)
                    held_notes[event.key] = sound
            elif event.type == pygame.KEYUP:
                if event.key in held_notes:
                    held_notes[event.key].fadeout(150)
                    del held_notes[event.key]
            elif event.type == pygame.QUIT:
                running = False
    pygame.quit()

if __name__ == "__main__":
    main()
