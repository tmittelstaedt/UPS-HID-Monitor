#!/usr/bin/env python3
import hid
import time
from datetime import datetime

UPS_VID = 0x051D  # APC
UPS_PID = 0x0002  # Back-UPS CS 350
POLL_INTERVAL = 10  # seconds between status prints
READ_WINDOW = 10.0  # seconds to collect reports each cycle

# Persistent last-known values
last_status = {}

def open_ups():
    h = hid.device()
    h.open(UPS_VID, UPS_PID)
    print(f"Connected to UPS: {h.get_manufacturer_string()} {h.get_product_string()}")
    return h

def decode_status_flags(flags):
    meanings = []
    if flags & 0x01: meanings.append("On Battery")
    if flags & 0x02: meanings.append("Low Battery")
    if flags & 0x04: meanings.append("Replace Battery")
    if flags & 0x08: meanings.append("Charging")
    if flags & 0x10: meanings.append("Discharging")
    if flags & 0x20: meanings.append("Boost/Trim Active")
    return ", ".join(meanings) if meanings else "Normal"

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
        return "output_freq", raw_val * 5.0  # fixed scaling

    elif report_id == 0x29 and len(payload) >= 2:
        raw_val = payload[0] | (payload[1] << 8)
        return "output_voltage", raw_val / 32.0

    elif report_id == 0x01 and len(payload) >= 1:
        return "status_flags", decode_status_flags(payload[0])

    else:
        return None, None

def read_all_reports(h):
    start_time = time.time()
    while time.time() - start_time < READ_WINDOW:
        data = h.read(64, timeout_ms=500)
        key, value = decode_report(data)
        if key:
            last_status[key] = value

def main():
    try:
        h = open_ups()
        while True:
            read_all_reports(h)
            ts = datetime.now().isoformat()

            line_parts = []
            if "battery_percent" in last_status:
                line_parts.append(f"Battery: {last_status['battery_percent']}%")
            if "runtime_minutes" in last_status:
                line_parts.append(f"Runtime: {last_status['runtime_minutes']} min")
            if "input_voltage" in last_status:
                line_parts.append(f"Input: {last_status['input_voltage']:.1f} V")
            if "output_voltage" in last_status:
                line_parts.append(f"Output: {last_status['output_voltage']:.1f} V")
            if "load_percent" in last_status:
                line_parts.append(f"Load: {last_status['load_percent']}%")
            if "output_freq" in last_status:
                line_parts.append(f"Freq: {last_status['output_freq']:.2f} Hz")
            if "status_flags" in last_status:
                line_parts.append(f"Status: {last_status['status_flags']}")

            print(f"[{ts}] " + " | ".join(line_parts))
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopping UPS monitor.")
    except Exception as e:
        print(f"[ERROR] Could not open UPS: {e}")

if __name__ == "__main__":
    main()
