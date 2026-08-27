#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UPS Status Menu Bar Monitor for macOS
- Connects to a UPS status server over TCP
- Changes menu bar icon color based on UPS status
- Starts shutdown countdown when on battery
- Cancels shutdown if power returns
- Click menu shows full JSON data in selectable text
"""

import socket
import json
import os
import sys
import time
from datetime import datetime
from AppKit import (
    NSStatusBar, NSImage, NSVariableStatusItemLength, NSApplication, NSApp,
    NSColor, NSBezierPath, NSMenu, NSMenuItem
)
from Foundation import NSObject, NSTimer

# ===== CONFIGURATION =====
SERVER_IP = "172.16.100.29"   # IP of UPS server
SERVER_PORT = 50000          # TCP port
CHECK_INTERVAL = 30          # Seconds between checks
SHUTDOWN_DELAY = 300         # Seconds to wait before shutdown after going on battery
ENABLE_LOG = True
LOG_FILE = os.path.expanduser("~/Library/Logs/ups-shutdown-monitor.log")
# =========================

shutdown_pending = False
shutdown_start_time = None
last_json_data = "{}"  # Store last JSON string for menu display

# === Logging ===
def log_message(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"{timestamp} {message}"
    print(log_entry)
    if ENABLE_LOG:
        try:
            os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
            with open(LOG_FILE, "a") as f:
                f.write(log_entry + "\n")
        except PermissionError:
            print(f"[WARN] Cannot write to log file {LOG_FILE} (permission denied)")

# === Network ===
def get_ups_status(ip, port):
    """Connect to UPS server and retrieve JSON status."""
    try:
        with socket.create_connection((ip, port), timeout=5) as sock:
            data = sock.recv(4096).decode("utf-8").strip()
            if data:
                return json.loads(data)
    except (socket.error, json.JSONDecodeError) as e:
        log_message(f"Failed to get UPS status: {e}")
    return None

# === Icon Drawing ===
def create_icon(color):
    """Create a small colored circle icon."""
    size = 16
    img = NSImage.alloc().initWithSize_((size, size))
    img.lockFocus()
    if color == "green":
        NSColor.greenColor().set()
    elif color == "red":
        NSColor.redColor().set()
    elif color == "yellow":
        NSColor.yellowColor().set()
    else:
        NSColor.grayColor().set()
    path = NSBezierPath.bezierPathWithOvalInRect_(((0, 0), (size, size)))
    path.fill()
    img.unlockFocus()
    return img

# === Shutdown ===
def shutdown_system():
    """Shutdown the macOS system."""
    log_message("Shutting down system now...")
    os.system("osascript -e 'tell app \"System Events\" to shut down'")

# === App Delegate ===
class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.status_item.setToolTip_("UPS Status Monitor")

        # Create menu
        self.menu = NSMenu.alloc().init()
        self.json_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "No data yet", None, ""
        )
        self.json_menu_item.setEnabled_(False)  # Make it read-only
        self.menu.addItem_(self.json_menu_item)
        self.menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit", "terminate:", ""
        )
        self.menu.addItem_(quit_item)

        self.status_item.setMenu_(self.menu)

        self.update_status()
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            CHECK_INTERVAL, self, 'update_status', None, True
        )

    def update_status(self):
        global shutdown_pending, shutdown_start_time, last_json_data

        status_obj = get_ups_status(SERVER_IP, SERVER_PORT)
        if status_obj:
            current_status = status_obj.get("Status", "Unknown")
            log_message(f"UPS Status: {current_status}")

            # Store JSON for menu
            last_json_data = json.dumps(status_obj, indent=2)
            self.json_menu_item.setTitle_(last_json_data)

            # Tooltip is short status
            self.status_item.setToolTip_(f"UPS Status: {current_status}")

            if current_status.lower() == "online":
                self.status_item.setImage_(create_icon("green"))
                if shutdown_pending:
                    log_message("Power restored. Cancelling shutdown countdown.")
                    shutdown_pending = False
                    shutdown_start_time = None

            elif current_status.lower() == "onbattery":
                self.status_item.setImage_(create_icon("red"))
                if not shutdown_pending:
                    shutdown_pending = True
                    shutdown_start_time = time.time()
                    log_message(f"UPS on battery. Shutdown in {SHUTDOWN_DELAY} seconds if power not restored.")
                else:
                    elapsed = time.time() - shutdown_start_time
                    if elapsed >= SHUTDOWN_DELAY:
                        shutdown_system()

            else:
                self.status_item.setImage_(create_icon("yellow"))

        else:
            self.status_item.setImage_(create_icon("gray"))
            self.status_item.setToolTip_("UPS Status Unreachable")
            self.json_menu_item.setTitle_("UPS Status Unreachable")

# === Main ===
if __name__ == "__main__":
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    NSApp().setDelegate_(delegate)
    app.run()
