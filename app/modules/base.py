class DisplayModule:
    name = "base"

    def is_ready(self, providers, boot_state):
        return True

    def render(self, now_tuple, providers, boot_state):
        return "-----"
