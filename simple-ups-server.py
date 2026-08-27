#!/usr/bin/env python3
import sys
import time
import socket
import json
from datetime import datetime

# --- Check for hidapi availability ---
try:
    import hid
except ImportError:
    sys.stderr.write(
        "ERROR: The 'hidapi' Python package is not installed.\n"
        "Install it with:\n"
        "    pip install hidapi\n"
        "On macOS, you may need:\n"
        "    brew install hidapi && pip install hidapi\n"
    )
    sys.exit(1)

UPS_VID = 0x051D  # APC
UPS_PID = 0x0002  # Back-UPS CS 350
READ_WINDOW = 2.0  # seconds to collect reports before serving
RECONNECT_DELAY = 5  # seconds between reconnect attempts

last_status = {}
ups_handle = None


def open_ups():
    """Try to open the UPS HID device."""
    global ups_handle
    try:
        h = hid.device()
        h.open(UPS_VID, UPS_PID)
        print(f"Connected to UPS: {h.get_manufacturer_string()} {h.get_product_string()}")
        ups_handle = h
        return True
    except Exception as e:
        print(f"[WARN] UPS not found: {e}")
        ups_handle = None
        return False


def decode_report(data):
    """Decode a single HID report into a key/value pair."""
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
    else:
        return None, None


def read_all_reports():
    """Read all available HID reports for a short window."""
    if not ups_handle:
        return
    start_time = time.time()
    while time.time() - start_time < READ_WINDOW:
        try:
            data = ups_handle.read(64, timeout_ms=500)
        except Exception as e:
            print(f"[WARN] Lost UPS connection: {e}")
            close_ups()
            return
        key, value = decode_report(data)
        if key:
            last_status[key] = value


def determine_status():
    """Infer AC/Battery status from input voltage."""
    if not ups_handle:
        return "UPS Disconnected"
    if last_status.get("input_voltage", 0) < 10:
        return "On Battery"
    else:
        return "On AC Power"


def close_ups():
    """Close UPS handle if open."""
    global ups_handle
    if ups_handle:
        try:
            ups_handle.close()
        except Exception:
            pass
    ups_handle = None


def serve_tcp():
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
                print(f"Connection from {addr}")

                # Ensure UPS is connected or try reconnect
                if not ups_handle:
                    if not open_ups():
                        last_status.clear()

                # If connected, read data
                if ups_handle:
                    read_all_reports()

                # Build JSON output
                last_status["timestamp"] = datetime.now().isoformat()
                last_status["status"] = determine_status()
                json_data = json.dumps(last_status) + "\n"

                # Send and close
                try:
                    conn.sendall(json_data.encode("utf-8"))
                    print(f"Sent: {json_data.strip()} and closed connection")
                except Exception as e:
                    print(f"[ERROR] Failed to send data: {e}")


def main():
    try:
        open_ups()  # Initial attempt
        serve_tcp()
    except KeyboardInterrupt:
        print("\nStopping UPS TCP server.")
    finally:
        close_ups()


if __name__ == "__main__":
    main()
