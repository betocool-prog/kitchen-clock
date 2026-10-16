#include "sensor.h"

#include <zephyr/device.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#if DT_NODE_HAS_STATUS(DT_ALIAS(bme280), okay)
static const struct device *const bme280 = DEVICE_DT_GET(DT_ALIAS(bme280));
#endif

/* zephyr,user io-channel: see boards/xiao_ble.overlay for the
 * pinctrl mapping. We pull the chosen phandle there so the SAADC
 * initialiser doesn't need to know which pin we're using.
 */
#if DT_NODE_HAS_STATUS(DT_PATH(zephyr_user), okay)
static const struct adc_dt_spec adc_batt = ADC_DT_SPEC_GET(DT_PATH(zephyr_user));
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
#else
    printk("No bme280 alias in devicetree — sensor reads return zeros\n");
#endif

#if DT_NODE_HAS_STATUS(DT_PATH(zephyr_user), okay)
    if (!adc_is_ready_dt(&adc_batt)) {
        printk("SAADC device not ready — battery reads will return 0\n");
        printk("  expected divider wiring on the XIAO nRF52840:\n");
        printk("    AIN7 / P0.31 (XIAO D7) <- divider tap (-)\n");
        printk("    divider hi  <- V_BATT_PIN   (user-chosen sense rail)\n");
        printk("    divider lo  <- GND\n");
        return 0;     /* non-fatal: BLE still works */
    }
    int err = adc_channel_setup_dt(&adc_batt);
    if (err < 0) {
        printk("SAADC channel setup failed (%d) — battery reads return 0\n",
               err);
        return 0;
    }
    printk("SAADC ready: %s, channel %u, gain 1 reference VDD\n",
           adc_batt.dev->name, (unsigned)adc_batt.channel_id);
#else
    printk("No zephyr,user io-channels in devicetree — battery reads "
           "return 0\n");
#endif

    return 0;
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

int kclock_sensor_read_battery_raw(uint16_t *raw_out)
{
#if DT_NODE_HAS_STATUS(DT_PATH(zephyr_user), okay)
    int16_t sample = 0;
    struct adc_sequence seq = {
        .buffer      = &sample,
        /* buffer_size is in BYTES, not samples. */
        .buffer_size = sizeof(sample),
        .channels    = BIT(adc_batt.channel_id),
        .resolution  = 12,
        .oversampling = 0,
    };

    int err = adc_read_dt(&adc_batt, &seq);
    if (err < 0) {
        printk("SAADC read failed (%d) — battery reads return 0\n", err);
        *raw_out = 0;
        return 0;        /* non-fatal: BLE still works */
    }

    /* SAADC returns a signed 12-bit sample centred at 0. We clamp
     * negative noise to the floor at 0 so the host-side decoder
     * keeps its sentinel behaviour (0 means "no data" in Python).
     */
    if (sample < 0) {
        sample = 0;
    }
    if (sample > 4095) {
        sample = 4095;
    }

    *raw_out = (uint16_t)sample;
    return 0;
#else
    *raw_out = 0;
    return 0;
#endif
}
