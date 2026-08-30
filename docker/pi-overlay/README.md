# Pi image overlay (Path A)

Customisations applied on top of `pi-gen`'s `lite` Trixie image:

- Install `python3-pygame`, `libsdl2-image-2.0-0`, `libsdl2-ttf-2.0-0`,
  `libfreetype6`, `bluez` via apt.
- Drop `/etc/systemd/system/kitchen-clock.service`.
- Drop `/etc/systemd/system/kitchen-clock-suppressor.service` to
  inhibit the screen-saver / idle sleep on the framebuffer.
- Create `/opt/kitchen-clock-venv` with `pip install` of the
  `$WORKSPACE/firmware/main-unit/` package plus `dbus-python` and
  `bleak` (apt has no `bleak` for Trixie).
- The boot cmdline is rewritten in `scripts/prep-sdcard.sh` to
  `loglevel=3 console=tty3` so the kernel printk doesn't repaint
  the framebuffer that PyGame is bound to.

The directory structure here mirrors what pi-gen expects
(`stage2/`, `stage3/`, etc.). The actual machine is at
`stage2/00-kclock-runtime/`; numbers ahead of file names give
pi-gen a stable invocation order.
