# Project Description

I am after a kitchen clock with basic weather information. I was not happy so far with the models in the shops, so I'd probable be better off building one from scratch.

The complete project consists of an internal main unit, the kitchen clock, and an external small temperature/humidity sensor.

# Requirements

- Colour screen, 22 cm / 9" diagonal size. Approximate.
- The time display should occupy the left half of the screen, the weather information should display on the right hand side.
- It should expose a Wifi interface to connect daily to the internet to sync time information
- Time should be set to the location, e.g. Perth, WA.
- Weather should be updated, daily, hourly? Not a hard constraint.
- Temperature should record the max and min in the last 24 hours.
- A bluetooth interface (BLE) should connect to an external temperature sensor (outside) with real time updates.
- The unit should have a real time temperature sensor for the location it's at. The sensor should wired to avoid warm bias from the unit.
- The display is strictly a display, no touch screen required.
- A 3D printed frame will hold the tool together.
- The unit shall be supplied by an external 12 DC supply, and optional battery backup (2xAA, 1x 9V).
- The external sensor shall be supplied by 1x 26650 Li-Ion battery per
  sensor unit, charged via the XIAO's onboard BQ25101 over USB-C.
  Power consumption is low (extended deep-sleep between advertisements);
  no boost stage is required.
- As long as the project goes, progress should be written into a README.md file, and updated regularly. 
- The firmware and hardware design shall live in this folder.
- The development environment shall be a docker container defined within this folder.
- Everything should be open source as much as possible!

# Ideas

I'm thinking there must be an ESP32, STM32 or nrf52 dev kit which embeds or can be easily connected to a colour display. The electronics would ideally live behind the display or be connected through a flexible cable.

A small RPI running Linux is a possibility, as well as other Linux capable MPUs with display capability.

For the external sensor I'm also thinking of a low power dev kit that can do BLE and measure temperature and humidity. 

If none is available, I'm happy to design a PCB, however I'd like to exhaust the dev kit possibilities.

# Project steps

## Find available devkits and relevant links

Look online for dev kits that could be suitable to our requirements, both for the internal main unit and the external sensor

## Obtain hardware

That's on me! If nothing is available online, we'll need to sidestep to build PCBs.

## Deploy dev environment

Deploy the necessary dev environment in the docker container, test that it runs.

## Create blinky 

Test the hardware with a blinky project.

## Start firmware development and GUI design

During this step we will consult regularly about the graphics and the functionality of the unit.

