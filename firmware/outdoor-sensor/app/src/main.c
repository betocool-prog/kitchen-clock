#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include "ble.h"
#include "blinky.h"
#include "mac.h"
#include "power.h"
#include "sensor.h"

#ifndef KCLOCK_SENSOR_FW_VERSION
#define KCLOCK_SENSOR_FW_VERSION "v7"
#endif

/* Periodic measurement cadence: every 30 s the firmware re-samples
 * the BME280 + SAADC and re-arms BLE advertising so the central has
 * a fresh window to connect. The connection-window model is owned
 * by ble.c — on connect ble.c schedules a self-disconnect after 5 s,
 * which fires ON_BLE_CHILDREN on the system work queue and tidies up
 * BlueZ state so the next cycle isn't blocked by stale
 * `Connected: yes`.
 */
#define KCLOCK_MEASUREMENT_PERIOD_S  30

static struct k_timer measurement_timer;
static struct k_work  measurement_work;

static void do_sample_and_publish(void)
{
    int16_t  temp_centi = 0;
    uint16_t hum_centi   = 0;
    uint16_t batt_raw    = 0;

    if (kclock_sensor_read(&temp_centi, &hum_centi) == 0) {
        printk("sample: %d.%02d C, %u.%02u %%RH\n",
               temp_centi / 100, temp_centi % 100,
               hum_centi   / 100, hum_centi   % 100);
    } else {
        printk("sample: BME280 read failed; pushing 0.0 values to GATT\n");
    }
    kclock_sensor_read_battery_raw(&batt_raw);
    printk("sample: SAADC raw = %u (panel: 'B: %u ADC')\n",
           batt_raw, batt_raw);
    kclock_ble_set_readings(temp_centi, hum_centi, batt_raw);
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

    /* Periodic measurement: timer fires every 30 s on the system
     * work queue. Each wake re-samples BME280 + SAADC and re-arms
     * advertising so the central has a fresh window.
     */
    k_work_init(&measurement_work, on_measurement_work);
    k_timer_init(&measurement_timer, on_measurement_timer, NULL);
    k_timer_start(&measurement_timer,
                  K_SECONDS(KCLOCK_MEASUREMENT_PERIOD_S),
                  K_SECONDS(KCLOCK_MEASUREMENT_PERIOD_S));

    printk("kitchen-clock sensor firmware: idle "
           "(periodic measurement + auto-disconnect)\n");

    /* Idle forever; the periodic timer and BLE connection callbacks
     * drive subsequent work from here. */
    while (1) {
        k_msleep(1000);
    }

    return 0;
}
