#ifndef KCLOCK_BLINKY_H
#define KCLOCK_BLINKY_H

/*
 * Configure the XIAO nRF52840's green on-board LED (P0.26) as a
 * GPIO output and spawn a Zephyr thread that toggles it every
 * 250 ms.
 *
 * Returns 0 on success, or a negative errno on GPIO/thread setup
 * failure. Failure is non-fatal — main() logs it but does not
 * abort, so the rest of the bring-up still runs.
 */
int kclock_blinky_init(void);

#endif /* KCLOCK_BLINKY_H */
