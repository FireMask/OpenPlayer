"""Botones GPIO (gpio-map.md): botón entre el pin y GND, pull-up interno y debounce."""

from gpiozero import Button


def create_buttons(config, on_press):
    """Un Button por pin; al pulsar solo llama on_press(nombre), que debe volver de inmediato."""
    buttons = []
    for name, pin in config.pins.items():
        button = Button(pin, pull_up=True, bounce_time=config.debounce_seconds)
        button.when_pressed = lambda name=name: on_press(name)
        buttons.append(button)
    return buttons
