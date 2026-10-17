"""Exercise the real SDL backend with a virtual controller, without user input."""
import ctypes
from pathlib import Path
import os
import unittest


@unittest.skipUnless(os.name == 'nt', 'Windows SDL DLL test')
class GamepadTests(unittest.TestCase):
    def test_normalized_psp_buttons_and_simultaneous_chord(self):
        os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
        import pygame
        from bloodpsp_launcher.gamepad import GamepadReader
        reader = GamepadReader()
        sdl = ctypes.CDLL(str(Path(pygame.__file__).parent / 'SDL2.dll'))
        sdl.SDL_JoystickAttachVirtual.argtypes = [ctypes.c_int] * 4
        sdl.SDL_JoystickOpen.argtypes = [ctypes.c_int]
        sdl.SDL_JoystickOpen.restype = ctypes.c_void_p
        sdl.SDL_JoystickClose.argtypes = [ctypes.c_void_p]
        sdl.SDL_JoystickSetVirtualButton.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint8]
        sdl.SDL_JoystickDetachVirtual.argtypes = [ctypes.c_int]
        index = sdl.SDL_JoystickAttachVirtual(1, 6, 15, 1)
        self.assertGreaterEqual(index, 0)
        handle = sdl.SDL_JoystickOpen(index)
        try:
            self.assertTrue(reader.api.is_controller(index))
            reader.device = reader.api.Controller(index)
            reader.name = reader.device.name
            self.assertEqual(reader.poll(), set())
            # Standard SDL A = PlayStation Cross, right shoulder = R1 / PSP R.
            self.assertEqual(sdl.SDL_JoystickSetVirtualButton(handle, pygame.CONTROLLER_BUTTON_A, 1), 0)
            self.assertEqual(reader.poll(), {'cross'})
            self.assertEqual(sdl.SDL_JoystickSetVirtualButton(handle, pygame.CONTROLLER_BUTTON_RIGHTSHOULDER, 1), 0)
            self.assertEqual(reader.poll(), {'cross', 'r'})
            self.assertEqual(sdl.SDL_JoystickSetVirtualButton(handle, pygame.CONTROLLER_BUTTON_A, 0), 0)
            self.assertEqual(reader.poll(), {'r'})
            self.assertEqual(sdl.SDL_JoystickSetVirtualButton(handle, pygame.CONTROLLER_BUTTON_RIGHTSHOULDER, 0), 0)
            self.assertEqual(reader.poll(), set())
        finally:
            if reader.device:
                reader.device.quit()
                reader.device = None
            sdl.SDL_JoystickClose(handle)
            sdl.SDL_JoystickDetachVirtual(index)
            reader.close()
