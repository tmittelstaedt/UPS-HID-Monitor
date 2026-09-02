#!/usr/bin/env python3
"""
macOS Menu Bar UPS Monitor with Vertical Stats Menu
- Green = Online
- Red   = On Battery
- Gray  = No Connection
Shows multiple UPS stats in menu and shuts down if OB > threshold.
"""

import socket
import sys
import time
import threading
import subprocess
from AppKit import NSStatusBar, NSImage, NSApplication, NSApp, NSMenu, NSMenuItem
import AppKit
import objc

# ---------------- NUT Client ---------------- #
def get_ups_status(
    nut_server="172.16.16.20",
    ups_name="nutdev-usb1",
    port=3493,
    timeout_seconds=5,
    username="",
    password=""
):
    vars_dict = {}
    try:
        with socket.create_connection((nut_server, port), timeout_seconds) as sock:
            sock.settimeout(timeout_seconds)

            def send_cmd(cmd):
                sock.sendall((cmd + "\n").encode("utf-8"))

            def recv_line():
                data = b""
                while not data.endswith(b"\n"):
                    chunk = sock.recv(1)
                    if not chunk:
                        break
                    data += chunk
                return data.decode("utf-8", errors="replace").strip()

            if username and password:
                send_cmd(f"USERNAME {username}")
                if not recv_line().startswith("OK"):
                    return None
                send_cmd(f"PASSWORD {password}")
                if not recv_line().startswith("OK"):
                    return None

            send_cmd(f"LIST VAR {ups_name}")
            while True:
                line = recv_line()
                if not line:
                    break
                if line.startswith("END LIST VAR"):
                    break
                if line.startswith("VAR "):
                    parts = line.split(" ", 3)
                    if len(parts) == 4:
                        var_name = parts[2]
                        var_value = parts[3].strip('"')
                        vars_dict[var_name] = var_value
        return vars_dict
    except Exception:
        return None

# ---------------- Menu Bar App ---------------- #
class UPSMenuBarApp(AppKit.NSObject):
    def init(self):
        self = objc.super(UPSMenuBarApp, self).init()
        if self is None:
            return None

        # Configurable settings
        self.poll_interval = 5       # seconds between polls
        self.ob_threshold = 60       # seconds on battery before shutdown
        self.nut_server = "172.16.16.20"
        self.ups_name = "nutdev-usb1"
        self.username = ""
        self.password = ""

        self.ob_start_time = None
        self.ups_data = {}

        # Create status bar item
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(AppKit.NSVariableStatusItemLength)
        self.status_item.setHighlightMode_(False)

        # Create menu with multiple stat items
        self.menu = NSMenu.alloc().init()
        self.status_item.setMenu_(self.menu)

        self.menu_items = {
            "status": NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Status: --", None, ""),
            "charge": NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Charge: --%", None, ""),
            "runtime": NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Runtime: --s", None, ""),
            "model": NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Model: --", None, ""),
            "voltage": NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Input Voltage: --V", None, ""),
            "battdate": NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Battery Date: --", None, "")
        }

        for key in self.menu_items:
            self.menu.addItem_(self.menu_items[key])

        self.menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", "terminate:", "")
        self.menu.addItem_(quit_item)

        self.update_status_icon("gray")
        self.start_polling()  # <-- This will now work
        return self

    def make_colored_ball(self, color):
        size = 16
        img = NSImage.alloc().initWithSize_((size, size))
        img.lockFocus()
        if color == "green":
            NSColor = objc.lookUpClass("NSColor").greenColor()
        elif color == "red":
            NSColor = objc.lookUpClass("NSColor").redColor()
        else:
            NSColor = objc.lookUpClass("NSColor").grayColor()
        NSColor.set()
        path = objc.lookUpClass("NSBezierPath").bezierPathWithOvalInRect_(((0, 0), (size, size)))
        path.fill()
        img.unlockFocus()
        return img

    def update_status_icon(self, color):
        self.status_item.button().setImage_(self.make_colored_ball(color))

    def update_menu_stats(self):
        d = self.ups_data or {}
        self.menu_items["status"].setTitle_(f"Status: {d.get('ups.status', '--')}")
        self.menu_items["charge"].setTitle_(f"Charge: {d.get('battery.charge', '--')}%")
        self.menu_items["runtime"].setTitle_(f"Runtime: {d.get('battery.runtime', '--')}s")
        self.menu_items["model"].setTitle_(f"Model: {d.get('device.model', '--')}")
        self.menu_items["voltage"].setTitle_(f"Input Voltage: {d.get('input.voltage', '--')}V")
        self.menu_items["battdate"].setTitle_(f"Battery Date: {d.get('battery.date', '--')}")

    def shutdown_mac(self):
        try:
            print("UPS on battery too long — initiating shutdown...")
            subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
        except Exception as e:
            print(f"Failed to shutdown: {e}", file=sys.stderr)

    def poll_ups(self):
        self.ups_data = get_ups_status(
            nut_server=self.nut_server,
            ups_name=self.ups_name,
            username=self.username,
            password=self.password
        )
        if self.ups_data and "ups.status" in self.ups_data:
            status = self.ups_data["ups.status"]
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] UPS Status: {status}")

            if status == "OL":
                self.update_status_icon("green")
                self.ob_start_time = None
            elif status == "OB":
                self.update_status_icon("red")
                if self.ob_start_time is None:
                    self.ob_start_time = time.time()
                elif time.time() - self.ob_start_time >= self.ob_threshold:
                    self.shutdown_mac()
            else:
                self.update_status_icon("gray")
                self.ob_start_time = None
        else:
            self.update_status_icon("gray")
            self.ob_start_time = None

        self.update_menu_stats()

    def start_polling(self):
        """Start background polling thread."""
        def loop():
            while True:
                self.poll_ups()
                time.sleep(self.poll_interval)
        threading.Thread(target=loop, daemon=True).start()

# ---------------- Main ---------------- #
if __name__ == "__main__":
    app = NSApplication.sharedApplication()
    delegate = UPSMenuBarApp.alloc().init()
    NSApp.setDelegate_(delegate)
    app.run()



