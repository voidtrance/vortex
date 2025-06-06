# Vortex GCode Emulator
![logo](/docs/images/vortex.png)

## Overview
Vortex is a software-define CNC machine emulator. It provides a set
of emulated objects that can be instanciated to make up any HW
configuration. The objects then emulate the appropriate HW behavior.

Initially, Vortex was meant to be a 3D printer emulator. However, the
ultimate goal is for it to be able to emulate any CNC machine.

## Documentation
1. [Installation Guide](/docs/Installation.md)
2. [Quick Start Guide](/docs/QuickStart.md)
3. Guides
   * [User Guide](/docs/UserGuide.md)
   * [Configuration Guide](/docs/Configuration.md)
   * [Object Reference](/docs/ObjectReference.md)
   * [Klipper Documentation](/docs//Klipper/Klipper.md)
     * [Klipper MCU Protocol](/docs/Klipper/KlipperProtocol.md)
     * [Klipper Command Reference](/docs/Klipper/CommandReference.md)
4. [Emulator Architecture](/docs/Architecture.md)
5. [Development Guide](/docs/Development.md)
6. [Coding Standard](/docs/CodingStandard.md)

## Credits

* **[KevinOConner](http://github.com/Klipper3d)** Creator of the Klipper
firmware which was the trigger for the start of this project.
* **[Paniel Detersson](https://github.com/monkeypangit/thermalemulator)** Creator of
the heat exchange algorithm used in the heater object.
