#ifndef KCLOCK_BLE_H
#define KCLOCK_BLE_H

#include <stdint.h>

int  kclock_ble_init(void);
void kclock_ble_set_readings(int16_t temp_centiC, uint16_t hum_centi, uint16_t batt_mV);
void kclock_ble_print_local_name(void);

#endif /* KCLOCK_BLE_H */
