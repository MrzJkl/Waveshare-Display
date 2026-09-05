class Widget:
    """Base class for everything that appears on the panel.

    Lifecycle, driven by the runtime:
      service(now_ticks, ctx)  called for every widget on every loop pass, also
                               while another widget is on screen. Fetch or
                               update data here, never block, and bump
                               self.revision when what you would draw changed.
      is_ready(ctx)            conditional visibility. Return False and the
                               rotation skips the widget entirely, so a widget
                               can appear only while it has something to say (a
                               warning is active, data has arrived, a threshold
                               is exceeded). The answer may change at any time:
                               the runtime switches away from a widget that
                               stops being ready and picks it up again once it
                               returns True. At least one widget has to stay
                               ready at all times, which is what the clock does.
      draw(display, ctx)       draw a complete frame on display.fb and return
                               the milliseconds until the next draw (the clock
                               returns the time to the next second boundary).
                               The runtime redraws earlier when revision or the
                               time sync changed.

    ctx carries the shared services: ctx.net (WifiService), ctx.time (TimeSync),
    ctx.mqtt (MqttClient) and ctx.hass (HomeAssistant).

    Exceptions from these three methods do not take the display down: the
    runtime logs them, sets self.failed and leaves the widget out of the
    rotation until the next restart.
    """

    name = "widget"

    def __init__(self):
        self.revision = 0
        self.failed = False

    def service(self, now_ticks, ctx):
        pass

    def is_ready(self, ctx):
        return True

    def draw(self, display, ctx):
        display.clear()
        return 1000
