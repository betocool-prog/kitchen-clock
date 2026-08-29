#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include "ble.h"
#include "mac.h"
#include "power.h"
#include "sensor.h"

int main(void)
{
    printk("kitchen-clock sensor firmware: boot\n");

    kclock_mac_print();

    int err = kclock_sensor_init();
    if (err) {
        /* Sensor init failure is non-fatal for the BLE bring-up:
         * the phone can still connect, the ESS characteristics will
         * just read as zero.
         */
        printk("sensor init failed: %d\n", err);
    }

    err = kclock_ble_init();
    if (err) {
        printk("BLE init failed: %d\n", err);
        return 0;
    }

    /* Take one BME280 sample (best effort); push to GATT. */
    int16_t  temp_centi = 0;
    uint16_t hum_centi   = 0;
    uint16_t batt_mV     = 0;

    if (kclock_sensor_read(&temp_centi, &hum_centi) == 0) {
        printk("sensor: %d.%02d C, %u.%02u %%RH\n",
               temp_centi / 100, temp_centi % 100,
               hum_centi   / 100, hum_centi   % 100);
    } else {
        printk("sensor: read failed; pushing 0.0 values to GATT\n");
    }
    kclock_sensor_read_battery_mV(&batt_mV);
    kclock_ble_set_readings(temp_centi, hum_centi, batt_mV);

    kclock_power_init();

    printk("kitchen-clock sensor firmware: idle (awaiting BLE events)\n");

    /* Idle forever; the BLE stack + connection callbacks drive
     * subsequent work. Deep-sleep lands in a follow-up step.
     */
    while (1) {
        k_msleep(1000);
    }

    return 0;
}
