import importlib.util
from pathlib import Path
import tempfile
import unittest
import wave


class DependencyTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('faster_whisper'), 'Optional ASR dependencies not installed')
    def test_faster_whisper_can_decode_wav_with_installed_pyav(self):
        from faster_whisper.audio import decode_audio
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'silence.wav'
            with wave.open(str(path), 'wb') as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(16000)
                stream.writeframes(b'\0\0' * 16000)
            self.assertEqual(len(decode_audio(str(path))), 16000)


if __name__ == '__main__':
    unittest.main()
