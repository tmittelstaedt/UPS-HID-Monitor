This Repository contains a mix of Python scripts written for MacOS, Python scripts written for Ubuntu Desktop and Ubuntu Server, and Powershell scripts written for Windows.

These are for monitoring UPS devices that are plugged into these operating systems via USB and they extend the basic monitoring supplied by the operating system

One of the problems with using a UPS on these systems is that the operating systems will detect the UPS on boot and connect a driver to it, if the UPS follows the USB HID standard.
That driver is generally extremely limited.  For example on MacOS it will show that a UPS such as an APC BackUPS CS is connected but it will not show voltage or frequency, it
will only show if the UPS is powered by battery or wall AC power.   Apple also blocks attempts to unload the driver.  Windows will not even show that a UPS is connected instead
it shows a green battery icon in the tray, which will either switch status to on battery or not on battery and if the UPS runs out of power, Windows default is to hibernate the PC
instead of shutting it down - just like a laptop.  While Windows allows a local admin to unload the USB driver for the UPS it will immediately reload it on boot.   Also, these
default drivers do not have any method of communicating UPS status over the network to any other host.   So, a large UPS that multiple PCs are plugged into, cannot be used to
gracefully shut all of those machines down.

Commercial software for UPSes generally takes the approach that control of an individual UPS on an individual computer is free, and often supply manufacturer's software to do this
for free.  But any software that allows for a single PC to communicate status to multiple PCs plugged into the same UPS is considered commercial and costs, and often nowadays
there is subscription fee.   Also manufacturers will not keep their software packages updated for newer operating systems once their model of UPS they wrote it for is no longer
being sold.

All of these programs are scripts so the computer owner can easily modify them to accommodate different models of UPS.  See the documentation files

These were all debugged on the oldest, simplest, cheapest UPSes I could find with UPS monitoring ports that speak UPS USB HID.  There are some very proprietary UPSes that do
have USB monitoring ports that are completely proprietary and use protocols that are alien to USB HID UPS.  These scripts do not support that.  Network parameters available via
the JSON servers are simple, just enough to enable networked shutdown.

The following files are contained here:

simple-ups-server.py    Python server that queries a USB connected UPS for status and makes that status available via a JSON query.  For Macintosh

Shutdown-Monitor-Mac.py   Desktop cient program that queries a JSON server for UPS status and shuts the system down if the UPS loses AC power.  For Macintosh

query-apc-on-usb.py    Diagnostic program to see if a USB-connected UPS is compatible with Monitor-UPS.ps1.  For Macintosh

ups_monitor.py   Desktop program that creates an icon on a Macintosh desktop the user can click on and get status of the UPS, as well as making a JSON server available  For Windows

GetUPSStatusNUT.py  Desktop program for the iMac that creates an icon on an Apple Macintosh desktop that the user can click on and get status of a UPS on a NUT server and will shut down the iMac if the NUT UPS goes on battery.  This is a NUT client

GetUPSStatusNUT.py.README.html  documentation for GetUPSStatusNUT.py

Monitor-UPS.ps1   Desktop program that creates an icon on a Windows desktop the user can click on and get status of the UPS, as well as making a JSON server available.  It can also monitor a remote NUT server  For Windows

Monitor-UPS-ReadInfo.ps1  Command line test diagnostic program that reads a USB-connected UPS to see if it is compatible with Monitor-UPS.ps1.    For Windows
