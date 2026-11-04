/* Host adapter only: all control decisions are generated from line.xml. */
#include <stdint.h>
#include <stdlib.h>
#include <time.h>
#include "iec_std_lib.h"
TIME __CURRENT_TIME;
BOOL __DEBUG = 0;
#include "iec_std_FB.h"
#include "POUS.h"
#include "POUS.c"

void *plc_new(void) {
    FILLINGLINE *line = calloc(1, sizeof(FILLINGLINE));
    if (line) FILLINGLINE_init__(line, 0);
    return line;
}
void plc_free(void *line) { free(line); }

void plc_scan(FILLINGLINE *line, uint64_t millis, uint32_t inputs) {
    __CURRENT_TIME.tv_sec = millis / 1000;
    __CURRENT_TIME.tv_nsec = (millis % 1000) * 1000000;
#define INPUT(field, bit) __SET_VAR(line->, field, , (inputs >> bit) & 1)
    INPUT(START, 0);
    INPUT(STOP, 1);
    INPUT(RESET, 2);
    INPUT(ESTOPOK, 3);
    INPUT(GUARDCLOSED, 4);
    INPUT(TANKOK, 5);
    INPUT(BOTTLEATFILL, 6);
    INPUT(EXITSENSOR, 7);
    INPUT(JAMSWITCH, 8);
    FILLINGLINE_body__(line);
}

uint32_t plc_outputs(FILLINGLINE *line) {
#define VALUE(field, bit) ((__GET_VAR(line->field) ? 1u : 0u) << bit)
    return VALUE(RUN, 0) | VALUE(CONVEYOR, 1) | VALUE(VALVE, 2) |
           VALUE(ALARM, 3) | VALUE(BATCHDONE, 4) | VALUE(FILLED, 5);
}

int plc_count(FILLINGLINE *line) { return __GET_VAR(line->BATCHCOUNT.CV); }
int plc_fill_ms(FILLINGLINE *line) {
    TIME t = __GET_VAR(line->FILLTIMER.ET);
    return t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
