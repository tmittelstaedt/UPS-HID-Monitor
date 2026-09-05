#!/usr/bin/env python3
import dbus

def get_ups_info():
    try:
        # Connect to the system bus
        bus = dbus.SystemBus()

        # Connect to UPower service
        upower = bus.get_object('org.freedesktop.UPower', '/org/freedesktop/UPower')
        upower_iface = dbus.Interface(upower, 'org.freedesktop.UPower')

        # Get list of all power devices
        devices = upower_iface.EnumerateDevices()

        ups_devices = []
        for dev_path in devices:
            if "ups" in dev_path.lower():
                dev_obj = bus.get_object('org.freedesktop.UPower', dev_path)
                props_iface = dbus.Interface(dev_obj, 'org.freedesktop.DBus.Properties')
                props = props_iface.GetAll('org.freedesktop.UPower.Device')

                ups_devices.append({
                    "path": dev_path,
                    "model": str(props.get("Model", "")),
                    "vendor": str(props.get("Vendor", "")),
                    "serial": str(props.get("Serial", "")),
                    "state": str(props.get("State", "")),
                    "percentage": float(props.get("Percentage", 0.0)),
                    "time_to_empty": float(props.get("TimeToEmpty", 0.0)),  # seconds
                    "time_to_full": float(props.get("TimeToFull", 0.0)),    # seconds
                    "energy": float(props.get("Energy", 0.0)),              # Wh
                    "energy_full": float(props.get("EnergyFull", 0.0)),     # Wh
                    "energy_rate": float(props.get("EnergyRate", 0.0)),     # W
                    "online": bool(props.get("Online", False)),
                    "is_present": bool(props.get("IsPresent", False)),
                })

        return ups_devices

    except dbus.DBusException as e:
        print(f"Error accessing UPower via D-Bus: {e}")
        return []

if __name__ == "__main__":
    ups_list = get_ups_info()
    if not ups_list:
        print("No UPS devices found.")
    else:
        for ups in ups_list:
            print(f"UPS Path: {ups['path']}")
            print(f"  Vendor: {ups['vendor']}")
            print(f"  Model: {ups['model']}")
            print(f"  Serial: {ups['serial']}")
            print(f"  State: {ups['state']}")
            print(f"  Charge: {ups['percentage']}%")
            print(f"  Time to Empty: {ups['time_to_empty']/60:.1f} min")
            print(f"  Time to Full: {ups['time_to_full']/60:.1f} min")
            print(f"  Energy: {ups['energy']} Wh / {ups['energy_full']} Wh")
            print(f"  Energy Rate: {ups['energy_rate']} W")
            print(f"  Online: {ups['online']}")
            print(f"  Present: {ups['is_present']}")
            print()
