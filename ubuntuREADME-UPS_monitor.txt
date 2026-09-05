UPS Monitor - README
====================

This UPS Monitor script provides:
- A system tray icon showing UPS status (AC power, battery, unknown)
- A TCP JSON server for remote UPS status queries
- Automatic icon color changes based on UPS state

------------------------------------------------------------
1. REQUIREMENTS
------------------------------------------------------------
Install the required packages:

    sudo apt update
    sudo apt install gir1.2-ayatanaappindicator3-0.1 \
                     libayatana-appindicator3-1 \
                     python3-pil \
                     python3-gi \
                     python3-dbus \
                     dbus-x11

Package descriptions:
- gir1.2-ayatanaappindicator3-0.1 : Python GObject bindings for Ayatana AppIndicator3
- libayatana-appindicator3-1      : GLib-based AppIndicator library
- python3-pil                     : Pillow image library for icon generation
- python3-gi                      : Python GObject introspection
- python3-dbus                    : Python D-Bus bindings
- dbus-x11                        : Provides dbus-launch for session bus startup

------------------------------------------------------------
2. CONFIGURING UPOWER FOR CRITICAL POWER ACTION
------------------------------------------------------------
To make the system power off automatically when the UPS battery reaches a critical level:

1. Edit the UPower configuration file:
       sudo nano /etc/UPower/UPower.conf

2. Find the line:
       #CriticalPowerAction=PowerOff
   and uncomment it so it reads:
       CriticalPowerAction=PowerOff

3. Save and exit (Ctrl+O, Enter, Ctrl+X).

4. Restart UPower:
       sudo systemctl restart upower

------------------------------------------------------------
3. RUNNING THE UPS MONITOR
------------------------------------------------------------
Make the script executable:
    chmod +x /path/to/ups_monitor.py

Run it:
    /path/to/ups_monitor.py

Change TCP port:
    /path/to/ups_monitor.py --port 60000

------------------------------------------------------------
4. CREATING A DESKTOP LAUNCHER
------------------------------------------------------------
1. Create a .desktop file:
       nano ~/.local/share/applications/ups-monitor.desktop

2. Paste:
       [Desktop Entry]
       Type=Application
       Name=UPS Monitor
       Comment=UPS status tray icon and TCP server
       Exec=/home/youruser/ups_monitor.py
       Icon=/home/youruser/.local/share/icons/ups_icon.png
       Terminal=false
       Categories=Utility;

3. Make it executable:
       chmod +x ~/.local/share/applications/ups-monitor.desktop

4. (Optional) Copy to desktop:
       cp ~/.local/share/applications/ups-monitor.desktop ~/Desktop/
       chmod +x ~/Desktop/ups-monitor.desktop
   On GNOME, right-click → Allow Launching.

------------------------------------------------------------
5. AUTOSTART ON LOGIN
------------------------------------------------------------
    mkdir -p ~/.config/autostart
    cp ~/.local/share/applications/ups-monitor.desktop ~/.config/autostart/

------------------------------------------------------------
6. NOTES
------------------------------------------------------------
- Tray icon requires a running desktop session with D-Bus session bus.
- TCP server works in both desktop and headless modes.
- UPower must detect your UPS for accurate data.
