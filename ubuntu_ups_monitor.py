#!/usr/bin/env python3
import dbus
import json
import socket
import argparse
import threading
from datetime import datetime, timezone
from collections import OrderedDict
import os
from PIL import Image, ImageDraw
import sys
import subprocess

# ---------------- STDERR FILTER ----------------
class StderrFilter:
    def write(self, msg):
        if "libayatana-appindicator is deprecated" not in msg:
            sys.__stderr__.write(msg)
    def flush(self):
        sys.__stderr__.flush()

sys.stderr = StderrFilter()

# ---------------- GTK / APPINDICATOR ----------------
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import Gtk, AyatanaAppIndicator3 as AppIndicator3, GLib

# ---------------- ICON CREATION ----------------
ICON_DIR = "/tmp/ups_icons"
os.makedirs(ICON_DIR, exist_ok=True)

def create_icon(color, name):
    size = 32
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((2, 2, size-2, size-2), fill=color)
    path = os.path.join(ICON_DIR, f"{name}.png")
    img.save(path)
    return path

ICON_GREEN = create_icon("green", "ups_green")
ICON_RED = create_icon("red", "ups_red")
ICON_GREY = create_icon("grey", "ups_grey")

# ---------------- UPS DATA ----------------
def get_flat_ups_info():
    try:
        bus = dbus.SystemBus()
        upower = bus.get_object('org.freedesktop.UPower', '/org/freedesktop/UPower')
        upower_iface = dbus.Interface(upower, 'org.freedesktop.UPower')
        devices = upower_iface.EnumerateDevices()

        for dev_path in devices:
            if "ups" in dev_path.lower():
                dev_obj = bus.get_object('org.freedesktop.UPower', dev_path)
                props_iface = dbus.Interface(dev_obj, 'org.freedesktop.DBus.Properties')
                props = props_iface.GetAll('org.freedesktop.UPower.Device')

                state_val = int(props.get("State", 0))
                status_str = "On AC Power" if state_val == 4 else "On Battery"

                return OrderedDict([
                    ("vendor", str(props.get("Vendor", ""))),
                    ("model", str(props.get("Model", ""))),
                    ("battery_percent", float(props.get("Percentage", 0.0))),
                    ("runtime_minutes", round(float(props.get("TimeToEmpty", 0.0)) / 60, 1)),
                    ("status", status_str),
                    ("timestamp", datetime.now(timezone.utc).isoformat())
                ])
    except dbus.DBusException as e:
        return OrderedDict([("error", f"DBus error: {str(e)}")])

    return OrderedDict([
        ("vendor", ""),
        ("model", ""),
        ("battery_percent", 0.0),
        ("runtime_minutes", 0.0),
        ("status", "No UPS Found"),
        ("timestamp", datetime.now(timezone.utc).isoformat())
    ])

# ---------------- TCP SERVER ----------------
def start_tcp_server(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(("0.0.0.0", port))
        server_socket.listen(5)
        print(f"[INFO] UPS TCP server listening on port {port}... (Ctrl+C to stop)")

        try:
            while True:
                client_socket, client_addr = server_socket.accept()
                with client_socket:
                    print(f"[INFO] Connection from {client_addr}")
                    ups_data = get_flat_ups_info()
                    json_data = json.dumps(ups_data, separators=(",", ":"))
                    try:
                        client_socket.sendall(json_data.encode("utf-8"))
                    except Exception as e:
                        print(f"[ERROR] Failed to send data to {client_addr}: {e}")
                    print(f"[INFO] Sent UPS data to {client_addr} and closed connection.")
        except KeyboardInterrupt:
            print("\n[INFO] TCP server stopped by user.")

# ---------------- TRAY ICON ----------------
class UPSIndicator:
    def __init__(self, readme_path):
        self.readme_path = readme_path

        self.indicator = AppIndicator3.Indicator.new(
            "ups-status",
            ICON_GREY,
            AppIndicator3.IndicatorCategory.SYSTEM_SERVICES
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        menu = Gtk.Menu()

        # Open README menu item
        readme_item = Gtk.MenuItem(label="Open README")
        readme_item.connect("activate", self.open_readme)
        menu.append(readme_item)

        # Quit menu item
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.quit)
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)

        GLib.timeout_add_seconds(5, self.update_status)

    def update_status(self):
        ups_data = get_flat_ups_info()
        status = ups_data.get("status", "No UPS Found")
        if status == "On AC Power":
            self.indicator.set_icon_full(ICON_GREEN, "UPS on AC power")
        elif status == "On Battery":
            self.indicator.set_icon_full(ICON_RED, "UPS on battery")
        else:
            self.indicator.set_icon_full(ICON_GREY, "UPS status unknown")
        return True

    def open_readme(self, _):
        """Open the ubuntuREADME-UPS_monitor.txt in Text Edit (or default browser)."""
        if os.path.exists(self.readme_path):
            try:
                subprocess.Popen(["xdg-open", self.readme_path])
            except Exception as e:
                print(f"[ERROR] Could not open README: {e}")
        else:
            print(f"[ERROR] README file not found: {self.readme_path}")

    def quit(self, _):
        Gtk.main_quit()

# ---------------- MAIN ----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UPS TCP JSON Server + Tray Icon")
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=50000,
        help="TCP port to listen on (default: 50000)"
    )
    parser.add_argument(
        "-r", "--readme",
        type=str,
        default=os.path.expanduser("~/UPS/ubuntuREADME-UPS_monitor.txt"),
        help="Path to README.html file"
    )
    args = parser.parse_args()

    # Start TCP server in background thread
    tcp_thread = threading.Thread(target=start_tcp_server, args=(args.port,), daemon=True)
    tcp_thread.start()

    # Start tray icon in main GTK loop
    UPSIndicator(args.readme)
    Gtk.main()
