import requests, threading, time
from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import StringProperty, BooleanProperty
from kivy.utils import platform

KV = """
BoxLayout:
    orientation: "vertical"
    padding: 16
    spacing: 12
    TextInput:
        id: serial
        hint_text: "Device Serial (e.g. DEV-12345)"
        text: app.serial
        multiline: False
        on_text: app.serial = self.text.strip()
    TextInput:
        id: name
        hint_text: "Device Name"
        text: app.device_name
        multiline: False
        on_text: app.device_name = self.text.strip()
    TextInput:
        id: server
        hint_text: "Server URL (http://ip:5000)"
        text: app.server_url
        multiline: False
        on_text: app.server_url = self.text.strip()
    Label:
        id: status
        text: app.status_text
        size_hint_y: None
        height: self.texture_size[1] + 8
    BoxLayout:
        size_hint_y: None
        height: 48
        spacing: 12
        Button:
            text: "Register"
            on_release: app.register_device()
            disabled: app.tracking
        Button:
            text: "Start"
            on_release: app.start_tracking()
            disabled: app.tracking
        Button:
            text: "Stop"
            on_release: app.stop_tracking()
            disabled: not app.tracking
"""

class ClientApp(App):
    server_url = StringProperty("http://YOUR_SERVER_IP:5000")
    serial = StringProperty("DEV-00001")
    device_name = StringProperty("Android Phone")
    status_text = StringProperty("Idle")
    tracking = BooleanProperty(False)

    def build(self):
        from random import randint
        if self.serial == "DEV-00001":
            self.serial = f"DEV-{randint(10000,99999)}"
        return Builder.load_string(KV)

    # --- GPS setup ---
    def on_start(self):
        self._gps_available = False
        if platform == "android":
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.ACCESS_FINE_LOCATION, Permission.ACCESS_COARSE_LOCATION])
        try:
            from plyer import gps
            self.gps = gps
            self.gps.configure(on_location=self._on_location, on_status=self._on_gps_status)
            self._gps_available = True
        except Exception as e:
            self.log(f"GPS unavailable: {e}")

        self._bg_thread = None

    # --- API calls ---
    def register_device(self):
        if not self._base_ok(): return
        payload = {
            "serial_number": self.serial,
            "name": self.device_name or "Android Device",
            "make": "Android",
            "model": "Kivy/Plyer",
            "device_type": "Phone",
            "current_status": "active",
            "current_location": "Registered",
        }
        try:
            r = requests.post(f"{self.server_url}/api/register_device", json=payload, timeout=8)
            self.log("Registered" if r.ok else f"Register failed: {r.status_code} {r.text[:120]}")
        except Exception as e:
            self.log(f"Register error: {e}")

    def start_tracking(self):
        if not self._base_ok(): return
        if not self.tracking:
            self.tracking = True
            if self._gps_available:
                try:
                    # update every 2s or 1m movement
                    self.gps.start(minTime=2000, minDistance=1)
                    self.log("Tracking started (real GPS)")
                except Exception as e:
                    self.log(f"GPS start error: {e}")
                    self._start_sim()
            else:
                self._start_sim()

    def stop_tracking(self):
        if self.tracking:
            self.tracking = False
            try:
                if self._gps_available:
                    self.gps.stop()
            except Exception:
                pass
            self._bg_thread = None
            self.log("Tracking stopped")

    def _start_sim(self):
        # desktop fallback
        self.log("Tracking started (simulated)")
        if self._bg_thread: return
        def loop():
            lat, lon = -1.286389, 36.817223
            while self.tracking:
                self._send_location(lat, lon)
                lat += 0.0004
                lon += 0.0003
                time.sleep(3)
        self._bg_thread = threading.Thread(target=loop, daemon=True)
        self._bg_thread.start()

    # --- GPS callbacks ---
    def _on_location(self, **kwargs):
        if not self.tracking: return
        lat = kwargs.get("lat") or kwargs.get("latitude")
        lon = kwargs.get("lon") or kwargs.get("longitude")
        if lat is None or lon is None: return
        self._send_location(lat, lon)

    def _on_gps_status(self, stype, status):
        self.log(f"GPS {stype}: {status}")

    # --- Send to server ---
    def _send_location(self, lat, lon):
        data = {
            "serial_number": self.serial,
            "latitude": float(lat),
            "longitude": float(lon),
            "current_status": "active"
        }
        try:
            r = requests.post(f"{self.server_url}/api/report_location", json=data, timeout=6)
            if r.ok:
                self.log(f"Sent {lat:.6f}, {lon:.6f}")
            else:
                self.log(f"Send fail: {r.status_code}")
        except Exception as e:
            self.log(f"Net err: {e}")

    # --- helpers ---
    def _base_ok(self):
        if not self.server_url or not self.serial:
            self.log("Set server URL and serial")
            return False
        return True

    def log(self, msg):
        Clock.schedule_once(lambda dt: setattr(self, "status_text", msg), 0)

if __name__ == "__main__":
    ClientApp().run()
