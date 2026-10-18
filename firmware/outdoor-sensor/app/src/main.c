#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include "ble.h"
#include "blinky.h"
#include "mac.h"
#include "power.h"
#include "sensor.h"

#ifndef KCLOCK_SENSOR_FW_VERSION
#define KCLOCK_SENSOR_FW_VERSION "v10"
#endif

/* Periodic measurement cadence (ADR 0012): every 15 s the firmware
 * re-samples the BME280 + SAADC and refreshes the advertising
 * payload (T/H/B ride as ESS 0x181A service data) so a passively
 * scanning central sees fresh values without a GATT connection.
 * The GATT service remains advertised connectable for debugging;
 * on connect ble.c still schedules a self-disconnect after 5 s
 * to keep BlueZ state clean for the next debug client.
 */
#define KCLOCK_MEASUREMENT_PERIOD_S  15

static struct k_timer measurement_timer;
static struct k_work  measurement_work;

static void do_sample_and_publish(void)
{
    int16_t  temp_centi = 0;
    uint16_t hum_centi   = 0;
    uint16_t batt_mv    = 0;

    if (kclock_sensor_read(&temp_centi, &hum_centi) == 0) {
        printk("sample: %d.%02d C, %u.%02u %%RH\n",
               temp_centi / 100, temp_centi % 100,
               hum_centi   / 100, hum_centi   % 100);
    } else {
        printk("sample: BME280 read failed; pushing 0.0 values to GATT\n");
    }
    kclock_sensor_read_battery_mv(&batt_mv);
    printk("sample: battery = %u mV\n", batt_mv);
    kclock_ble_set_readings(temp_centi, hum_centi, batt_mv);
}

static void on_measurement_work(struct k_work *work)
{
    do_sample_and_publish();
    int err = kclock_ble_arm_advertising();
    if (err == -EALREADY) {
        printk("periodic wake: advertising already on\n");
    } else if (err) {
        printk("periodic wake: arm advertising err=%d\n", err);
    }
}

static void on_measurement_timer(struct k_timer *t)
{
    k_work_submit(&measurement_work);
}

int main(void)
{
    printk("kitchen-clock sensor firmware: boot %s\n",
           KCLOCK_SENSOR_FW_VERSION);

    kclock_mac_print();

    int err = kclock_sensor_init();
    if (err) {
        printk("sensor init failed: %d (continuing — BLE works anyway)\n",
               err);
    }

    err = kclock_ble_init();
    if (err) {
        printk("BLE init failed: %d\n", err);
        return 0;
    }

    /* Boot-time sample so a connect at startup still hits a populated
     * GATT database before the first periodic wake fires (every
     * KCLOCK_MEASUREMENT_PERIOD_S).
     */
    do_sample_and_publish();

    kclock_power_init();

    int blinky_err = kclock_blinky_init();
    if (blinky_err) {
        printk("blinky init failed: %d (continuing without LED)\n",
               blinky_err);
    }

    /* Periodic measurement: timer fires every 15 s on the system
     * work queue. Each wake re-samples BME280 + SAADC and refreshes
     * the broadcast payload so passive scanners see fresh data.
     */
    k_work_init(&measurement_work, on_measurement_work);
    k_timer_init(&measurement_timer, on_measurement_timer, NULL);
    k_timer_start(&measurement_timer,
                  K_SECONDS(KCLOCK_MEASUREMENT_PERIOD_S),
                  K_SECONDS(KCLOCK_MEASUREMENT_PERIOD_S));

    printk("kitchen-clock sensor firmware: idle "
           "(periodic measurement every %d s, broadcast payload "
           "+ auto-disconnect)\n",
           KCLOCK_MEASUREMENT_PERIOD_S);

    /* Idle forever; the periodic timer and BLE connection callbacks
     * drive subsequent work from here. */
    while (1) {
        k_msleep(1000);
    }

    return 0;
}
