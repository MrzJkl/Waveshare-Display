class Widget:
    """Base class for everything that appears on the panel.

    Lifecycle, driven by the runtime:
      service(now_ticks, ctx)  called for every widget on every loop pass, also
                               while another widget is on screen. Fetch or
                               update data here, never block, and bump
                               self.revision when what you would draw changed.
      is_ready(ctx)            whether there is something meaningful to show;
                               the rotation skips widgets that are not ready.
      draw(display, ctx)       draw a complete frame on display.fb and return
                               the milliseconds until the next draw (the clock
                               returns the time to the next second boundary).
                               The runtime redraws earlier when revision or the
                               time sync changed.
    ctx gives access to ctx.net (WifiService) and ctx.time (TimeSync).
    """

    name = "widget"

    def __init__(self):
        self.revision = 0

    def service(self, now_ticks, ctx):
        pass

    def is_ready(self, ctx):
        return True

    def draw(self, display, ctx):
        display.clear()
        return 1000
