"""SDL controller normalization for DualShock/DualSense and Xbox pads."""
import os


class GamepadReader:
    def __init__(self):
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
        import pygame
        from pygame._sdl2 import controller
        self.pygame, self.api = pygame, controller
        pygame.display.init()
        pygame.joystick.init()
        controller.init()
        self.device = None
        self.name = "No controller connected"
        self.buttons = {
            pygame.CONTROLLER_BUTTON_A: "cross", pygame.CONTROLLER_BUTTON_B: "circle",
            pygame.CONTROLLER_BUTTON_X: "square", pygame.CONTROLLER_BUTTON_Y: "triangle",
            pygame.CONTROLLER_BUTTON_LEFTSHOULDER: "l", pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: "r",
            pygame.CONTROLLER_BUTTON_DPAD_UP: "up", pygame.CONTROLLER_BUTTON_DPAD_DOWN: "down",
            pygame.CONTROLLER_BUTTON_DPAD_LEFT: "left", pygame.CONTROLLER_BUTTON_DPAD_RIGHT: "right",
            pygame.CONTROLLER_BUTTON_BACK: "select",
        }

    def poll(self):
        self.pygame.event.pump()
        # Drain hotplug/button events; polling reads the current simultaneous state.
        self.pygame.event.clear()
        if self.device and not self.device.attached():
            self.device.quit()
            self.device = None
        if self.device is None:
            for index in range(self.api.get_count()):
                if self.api.is_controller(index):
                    self.device = self.api.Controller(index)
                    self.name = self.device.name or "Controller"
                    break
        if self.device is None:
            self.name = "No controller connected"
            return None
        return {name for code, name in self.buttons.items() if self.device.get_button(code)}

    def close(self):
        if self.device:
            self.device.quit()
            self.device = None
        self.api.quit()
        self.pygame.joystick.quit()
        self.pygame.display.quit()
