# Klipper Frontend
The Klipper frontend is designed to act as a Klipper MCU. It interfaces with
the Klipper host using the [Klipper MCU protocol](/docs/Klipper/KlipperProtocol.md).

It accepts and responds to commands according to the configuration of the
controller used by the emulation.

> **WARNING**
>
> Please note that using the Klipper frontend with an emulator update frequency of
> less than 1MHz may lead to Klipper errors.
>
> Klipper heavily relies on MCU timers to execute the MCU commands and provide
> responses. Some responses contain the current MCU time when the response gets
> generate. Also, some responses have to come back within a certain time window.
>
> For better timeing performance, see the [Core Timing](/docs/UserGuide.md#core-timing)
> section of the User Guide.
>
> The timer mechanism built into Vortex relies on the update thread to update the
> timer state and call timer callback. If the update frequency is too low, the
> timer thread updates the timers' state at too low of a frequency. This results
> in response being sent or contain clock times that are out of the windows that
> the Klipper host expects.

## Generating Emulator Configuration
Virtually all MCU hardware that Klipper uses is controlled by either manipulating
pin states or reading pins. Therefore, Klipper
[configures controller pins to be associated with OIDs (Object IDs)](/docs/Klipper/KlipperProtocol.md#controller-configuration).

Therefore, the Vortex emulator configuration has to define the emulator objects in
a way so the Vortex object pin assignment matches that of Klipper's configuration.
To help with this, the Vortex code base contains a [tool](/tools//config_from_klipper.py)
that will read in a Klipper configuration file and generate a matching Vortex
configuration file. This tool is also installed as part of the emulator wheel.

Please note that the tool will generate default values for some of the Vortex
configuration settings as there is no way to infer the correct values from the
Klipper configuration. Therefore, it is advisable that the generated configurtion is
checked for accuracy before use.

## klipper_print_file.py

The emulator includes a tool designed to makes printing a GCode file directly from
the Klipper firmware (without Moonraker or a frontend like Fluidd or Mainsail)
easier. It reads a Klipper configuration file looking for the `[virtual_sdcard]`
section and extracts the gcode file path from there. It will then display all
available GCode files and ask the user which one should be printed. After the user
has made a selection, it sends the necessary commands to Klipper through the
Klipper domain socket to start the printing process.