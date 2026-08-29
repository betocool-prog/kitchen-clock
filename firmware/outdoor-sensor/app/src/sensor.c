#include "sensor.h"

#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#if DT_NODE_HAS_STATUS(DT_ALIAS(bme280), okay)
static const struct device *const bme280 = DEVICE_DT_GET(DT_ALIAS(bme280));
#endif

int kclock_sensor_init(void)
{
#if DT_NODE_HAS_STATUS(DT_ALIAS(bme280), okay)
    if (!device_is_ready(bme280)) {
        printk("BME280 device not ready\n");
        printk("  expected wiring on the XIAO nRF52840:\n");
        printk("    SDA -> D2 (P0.04)  [maps to &i2c1 in devicetree]\n");
        printk("    SCL -> D3 (P0.05)  [maps to &i2c1 in devicetree]\n");
        printk("    VDD -> 3V3\n");
        printk("    GND -> GND\n");
        printk("    addr 0x77 (Adafruit STEMMA QT, SDO jumper open)\n");
        return -ENODEV;
    }
    printk("BME280 ready\n");
    return 0;
#else
    printk("No bme280 alias in devicetree — sensor reads return zeros\n");
    return -ENODEV;
#endif
}

int kclock_sensor_read(int16_t *temp_centiC, uint16_t *hum_centi)
{
#if DT_NODE_HAS_STATUS(DT_ALIAS(bme280), okay)
    struct sensor_value t = {0};
    struct sensor_value h = {0};

    if (sensor_sample_fetch(bme280) != 0) {
        return -EIO;
    }
    sensor_channel_get(bme280, SENSOR_CHAN_AMBIENT_TEMP, &t);
    sensor_channel_get(bme280, SENSOR_CHAN_HUMIDITY,   &h);

    /* struct sensor_value: .val1 = integer part, .val2 = 1e-6
     * fractional. Convert to centi-units for our GATT encoding.
     */
    int32_t t_centi = (int32_t)t.val1 * 100 + (t.val2 / 10000);
    if (t_centi > INT16_MAX) t_centi = INT16_MAX;
    if (t_centi < INT16_MIN) t_centi = INT16_MIN;
    *temp_centiC = (int16_t)t_centi;

    int32_t h_centi = (int32_t)h.val1 * 100 + (h.val2 / 10000);
    if (h_centi > UINT16_MAX) h_centi = UINT16_MAX;
    *hum_centi = (uint16_t)h_centi;

    return 0;
#else
    *temp_centiC = 0;
    *hum_centi   = 0;
    return -ENODEV;
#endif
}

int kclock_sensor_read_battery_mV(uint16_t *mv)
{
    /* TODO: read actual cell voltage via the XIAO nRF52840's SAADC +
     * a user-chosen divider. Until then, the BLE characteristic is
     * readable but the value is 0 — a clear placeholder.
     */
    *mv = 0;
    return 0;
}
