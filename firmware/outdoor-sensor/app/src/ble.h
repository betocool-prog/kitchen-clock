#ifndef KCLOCK_BLE_H
#define KCLOCK_BLE_H

#include <stdint.h>

int  kclock_ble_init(void);
void kclock_ble_set_readings(int16_t temp_centiC, uint16_t hum_centi, uint16_t batt_raw);
void kclock_ble_print_local_name(void);

/* Re-arm BLE advertising. Used on each periodic wake window from
 * main.c so a fresh central has a chance to connect even immediately
 * after the firmware self-disconnects at the end of a previous
 * connection window.
 */
int kclock_ble_arm_advertising(void);

#endif /* KCLOCK_BLE_H */
