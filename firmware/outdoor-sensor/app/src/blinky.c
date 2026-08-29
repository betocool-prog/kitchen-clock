#include "blinky.h"

#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

/*
 * P0.26 is the green on-board LED on the Seeed XIAO nRF52840
 * (board name `xiao_ble` in Zephyr 3.7). 250 ms on / 250 ms off
 * → 2 Hz blink, a clear "I'm running" heartbeat that doesn't risk
 * running inside a BLE radio window or the BME280 forced-mode
 * conversion window.
 */
#define BLINK_PERIOD_MS  250u

#if DT_NODE_HAS_STATUS(DT_NODELABEL(green), okay)
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(DT_NODELABEL(green), gpios);
#else
/* Fallback if the overlay haven't been loaded (defensive only —
 * the overlay should make DT_NODELABEL(green) exist).
 */
#error "DT node `green` is not defined in the devicetree overlay"
#endif

static struct k_thread blinky_thread;
K_THREAD_STACK_DEFINE(blinky_stack, 512);

static void blinky_entry(void *p1, void *p2, void *p3)
{
    (void)p1; (void)p2; (void)p3;
    while (1) {
        (void)gpio_pin_toggle_dt(&led);
        k_msleep(BLINK_PERIOD_MS);
    }
}

int kclock_blinky_init(void)
{
    int err;

    if (!device_is_ready(led.port)) {
        printk("blinky: gpio device not ready\n");
        return -ENODEV;
    }

    err = gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);
    if (err) {
        printk("blinky: gpio_pin_configure_dt failed: %d\n", err);
        return err;
    }

    k_tid_t tid = k_thread_create(&blinky_thread, blinky_stack,
                                  K_THREAD_STACK_SIZEOF(blinky_stack),
                                  blinky_entry, NULL, NULL, NULL,
                                  K_LOWEST_APPLICATION_THREAD_PRIO, 0,
                                  K_FOREVER);
    k_thread_name_set(tid, "blinky");
    k_thread_start(tid);

    printk("blinky: thread running (P0.26, %u ms period)\n",
           (unsigned)BLINK_PERIOD_MS);
    return 0;
}
