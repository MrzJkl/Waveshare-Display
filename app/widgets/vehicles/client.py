"""Client for the Feuer Software Connect public API (vehicle list with status).

GET /interfaces/public/vehicle returns a list of SharedVehicleExtendedModel;
per vehicle we keep the short name and the FMS status. The request blocks for
the duration of the HTTPS round trip (TLS handshake included), so the caller
polls sparingly. Certificates are not verified (MicroPython requests default).
"""

import requests


class Vehicle:
    def __init__(self, name, status, radio_id):
        self.name = name            # e.g. "1-24-1"
        self.status = status        # 0..9 or None
        self.radio_id = radio_id

    def label(self, with_location=True):
        """Display name; without the location number "1-24-1" becomes "24-1"."""
        parts = self.name.split("-")
        if with_location or len(parts) != 3:
            return self.name
        return parts[1] + "-" + parts[2]


def short_name(item):
    """LocationIdentificationNumber-VehicleIdentifier-Subdivision, e.g. "1-24-1".

    Entries without these fields (containers) use the last word of the CallSign.
    """
    parts = [item.get("LocationIdentificationNumber"), item.get("VehicleIdentifier"), item.get("Subdivision")]
    if all(part is not None and part != "" for part in parts):
        return "-".join(str(part) for part in parts)
    call_sign = item.get("CallSign") or item.get("RadioId") or "?"
    return str(call_sign).split(" ")[-1]


class ConnectClient:
    def __init__(self, url, token, timeout_s):
        self.url = url
        self.timeout_s = timeout_s
        self._headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}

    def fetch(self):
        """Return a list of Vehicle; raises OSError/ValueError on failure."""
        response = requests.get(self.url, headers=self._headers, timeout=self.timeout_s)
        try:
            if response.status_code != 200:
                raise OSError("HTTP %d" % response.status_code)
            items = response.json()
        finally:
            response.close()
        vehicles = []
        for item in items:
            status = item.get("Status") or {}
            vehicles.append(Vehicle(short_name(item), status.get("Status"), item.get("RadioId")))
        return vehicles
