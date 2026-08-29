#include "power.h"

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

/* Deep-sleep cadence implementation deferred to a follow-up step.
 * For the BLE bring-up milestone the firmware stays awake; the
 * sleep tuning lands once the phone scanner sees the device and
 * the user confirms the GATT reads.
 *
 * What the eventual implementation will do:
 *   - sleep until next measurement interval (e.g. 30 s)
 *   - on wake: trigger BME280 single-shot, push to GATT, advertise,
 *     return to sleep
 *   - keep BLE in sleep on average; only wake the radio for a brief
 *     advertising window every interval
 * Target average current ~30 µA on a 26650 Li-Ion cell.
 */
void kclock_power_init(void)
{
    printk("power: stub — deep-sleep not implemented yet\n");
}
