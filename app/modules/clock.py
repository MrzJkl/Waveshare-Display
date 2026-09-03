from app import settings
from app.modules.base import DisplayModule


class ClockModule(DisplayModule):
    name = "clock"

    def render(self, now_tuple, providers, boot_state):
        hour = (now_tuple[3] + settings.UTC_OFFSET_HOURS) % 24
        minute = now_tuple[4]
        return "{:02d}:{:02d}".format(hour, minute)
