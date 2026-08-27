#!/usr/bin/env python3
import threading
import socket
import json
import objc
import time
from datetime import datetime

import AppKit
from AppKit import NSApplication, NSStatusBar, NSMenu, NSMenuItem, NSImage, NSBezierPath, NSColor
from Foundation import NSObject, NSTimer

# Handle API constant differences
try:
    STATUS_ITEM_LENGTH = AppKit.NSStatusItemVariableLength
except AttributeError:
    STATUS_ITEM_LENGTH = AppKit.NSVariableStatusItemLength

# HID API
try:
    import hid
except ImportError:
    sys.stderr.write("ERROR: Install hidapi: pip install hidapi\n")
    sys.exit(1)

UPS_VID = 0x051D
UPS_PID = 0x0002
READ_WINDOW = 2.0

ups_handle = None
lock = threading.Lock()
last_status = {}


# ---------------- UPS Functions ----------------
def open_ups():
    global ups_handle
    try:
        h = hid.device()
        h.open(UPS_VID, UPS_PID)
        ups_handle = h
        print("Connected to UPS")
        return True
    except Exception:
        ups_handle = None
        return False

def close_ups():
    global ups_handle
    if ups_handle:
        try:
            ups_handle.close()
        except Exception:
            pass
    ups_handle = None

def decode_report(data):
    if not data:
        return None, None
    report_id = data[0]
    payload = data[1:]
    if report_id == 0x0C and len(payload) >= 1:
        return "battery_percent", payload[0]
    elif report_id == 0x07 and len(payload) >= 2:
        return "runtime_minutes", payload[0] | (payload[1] << 8)
    elif report_id == 0x0D and len(payload) >= 2:
        raw_val = payload[0] | (payload[1] << 8)
        return "input_voltage", raw_val / 32.0
    elif report_id == 0x16 and len(payload) >= 1:
        return "load_percent", payload[0]
    elif report_id == 0x33 and len(payload) >= 2:
        raw_val = payload[0] | (payload[1] << 8)
        return "output_freq", raw_val * 5.0
    return None, None

def read_all_reports():
    if not ups_handle:
        return
    start_time = time.time()
    while time.time() - start_time < READ_WINDOW:
        try:
            data = ups_handle.read(64, timeout_ms=500)
        except Exception:
            close_ups()
            return
        key, value = decode_report(data)
        if key:
            with lock:
                last_status[key] = value

def determine_status():
    if not ups_handle:
        return "UPS Disconnected"
    if last_status.get("input_voltage", 0) < 10:
        return "On Battery"
    return "On AC Power"

# ---------------- TCP Server Thread ----------------
def tcp_server():
    HOST = "0.0.0.0"
    PORT = 50000
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(5)
        print(f"TCP server listening on {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            with conn:
                if not ups_handle:
                    open_ups()
                if ups_handle:
                    read_all_reports()
                with lock:
                    last_status["timestamp"] = datetime.now().isoformat()
                    last_status["status"] = determine_status()
                    json_data = json.dumps(last_status) + "\n"
                conn.sendall(json_data.encode("utf-8"))

# ---------------- AppDelegate ----------------
STATUS_ITEM_LENGTH = 24

class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        """Called when the app finishes launching."""
        self.statusItem = NSStatusBar.systemStatusBar().statusItemWithLength_(STATUS_ITEM_LENGTH)
        self.menu = NSMenu.alloc().init()
        self.statusItem.setMenu_(self.menu)

        # Initial menu update
        self.update_menu(None)

        # Schedule timer to update menu every 5 seconds — explicit selector binding
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            5.0,
            self,
            objc.selector(self.update_menu, selector=b"update_menu:", signature=b'v@:@'),
            None,
            True
        )

    def update_menu(self, timer):
        """Refresh menu and icon."""
        if not ups_handle:
            open_ups()
        if ups_handle:
            read_all_reports()

        with lock:
            status = determine_status()
            battery = last_status.get("battery_percent", "?")
            runtime = last_status.get("runtime_minutes", "?")
            voltage = last_status.get("input_voltage", "?")

        # Update icon
        icon = self.make_icon(status)
        self.statusItem.setImage_(icon)

        # Update menu items
        self.menu.removeAllItems()
        self.menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(f"Status: {status}", None, ""))
        self.menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(f"Battery: {battery}%", None, ""))
        self.menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(f"Runtime: {runtime} min", None, ""))
        self.menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(f"Voltage: {voltage} V", None, ""))
        self.menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit",
            objc.selector(self.quit_app, selector=b"quit_app:", signature=b'v@:@'),
            ""
        )
        self.menu.addItem_(quit_item)

    def make_icon(self, status):
        """Make a colored circle icon based on UPS status."""
        size = 18
        img = NSImage.alloc().initWithSize_((size, size))
        img.lockFocus()

        if status == "On Battery":
            color = (1.0, 0.0, 0.0, 1.0)  # red
        elif status == "On AC Power":
            color = (0.0, 1.0, 0.0, 1.0)  # green
        else:
            color = (0.5, 0.5, 0.5, 1.0)  # gray

        NSColor.colorWithCalibratedRed_green_blue_alpha_(*color).set()
        path = NSBezierPath.bezierPathWithOvalInRect_(((0, 0), (size, size)))
        path.fill()

        img.unlockFocus()
        img.setTemplate_(False)
        return img

    def quit_app(self, sender):
        """Quit the application."""
        close_ups()
        NSApplication.sharedApplication().terminate_(self)

# ---------------- Explicit selector bindings ----------------
AppDelegate.update_menu = objc.selector(AppDelegate.update_menu, selector=b"update_menu:", signature=b'v@:@')
AppDelegate.quit_app = objc.selector(AppDelegate.quit_app, selector=b"quit_app:", signature=b'v@:@')

# ---------------- Main ----------------
if __name__ == "__main__":
    # Start TCP server in background
    threading.Thread(target=tcp_server, daemon=True).start()

    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()
