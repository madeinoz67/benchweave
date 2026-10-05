/********************************** (C) COPYRIGHT *******************************
 * File Name          : main.c
 * Author             : Stephen Eaton
 * Version            : V0.3.0
 * Date               : 2026-10-05
 * Description        : BenchWeave ADC board firmware (protocol v2):
 *                      6-channel 12-bit ADC streaming at the negotiated baud;
 *                      with master-driven command/control.
 *
 * Wire protocol (see BenchWeave spec
 *   docs/superpowers/specs/2026-09-11-adc-board-uart-driver-design.md):
 *
 *   Frame = [0xAA 0x55][type][seq][len][payload(0..len-1)][crc16 LE]
 *   CRC16 = CCITT-FALSE (poly 0x1021, init 0xFFFF) over type..payload.
 *
 * ADC GPIO (canonical channel order):
 *   [0] PA2 = A0   [1] PA6 = A1   [2] PC4 = A2
 *   [3] PD2 = A3   [4] PD3 = A4   [5] PD4 = A7
 *
 * Other GPIO:
 *   PC1 = green LED   PA3 = trigger in (reserved)   PC2 = trigger out (reserved)
 *
 * Hardware: USART1 TX=PD5, RX=PD6, connected to the CH343G USB-UART bridge.
 *********************************************************************************
 * Copyright (c) Open Source
 *******************************************************************************/

#include "debug.h"
#include <stdint.h>

#include "ws2812.h"

/* ── Frame types ─────────────────────────────────────────────────────────── */
#define TYPE_SET_AVERAGING   0x01
#define TYPE_SET_CHANNELS    0x02
#define TYPE_SET_SAMPLE_MODE 0x03
#define TYPE_START_STREAM    0x04
#define TYPE_STOP_STREAM     0x05
#define TYPE_SAMPLE_ONCE     0x06
#define TYPE_RESET           0x07
#define TYPE_IDENTIFY        0x08
#define TYPE_ARM_TRIGGER     0x09 /* reserved: external trigger not implemented */
#define TYPE_SET_BAUD        0x0A /* v2: u32 LE baud */
#define TYPE_SET_FRAME_FORMAT 0x0B /* v2: u8 0 = legacy, 1 = mask-sized */
#define TYPE_ACK             0x81
#define TYPE_NAK             0x82
#define TYPE_IDENTIFY_RSP    0x83
#define TYPE_SAMPLE          0x90

/* ── Error codes ─────────────────────────────────────────────────────────── */
#define ERR_BAD_COMMAND     0x01
#define ERR_BAD_PARAMETER   0x02
#define ERR_BUSY            0x03
#define ERR_UNSUPPORTED     0x04

/* ── Protocol constants ──────────────────────────────────────────────────── */
#define SYNC0               0xAA
#define SYNC1               0x55
#define N_CHANNELS          6
#define MAX_RX_PAYLOAD      16
#define PROTOCOL_VERSION    2
#define FW_MINOR            3
/* capability bits in the v2 IDENTIFY_RSP caps field */
#define CAP_SET_BAUD        0x0001
#define CAP_SLIM_FRAME      0x0002
#define DEVICE_CAPS         (CAP_SET_BAUD | CAP_SLIM_FRAME)
/* the qualified baud set: CH32V006 USART ceiling 3 Mbps, USARTDIV = 1.0
 * exact at 48 MHz PCLK2 / 16 (wire-protocol.md). */
#define BAUD_2M             2000000u
#define BAUD_3M             3000000u
static const uint32_t SUPPORTED_BAUDS[2] = {BAUD_2M, BAUD_3M};
/* T_revert: after a baud switch, no CRC-valid frame within this window
 * reverts the device to boot state (2 Mbps + legacy). Spec hint value;
 * commissioned per bench per A02. */
#define T_REVERT_MS         250u

#define FW_MAJOR            0

/* ── GPIO ────────────────────────────────────────────────────────────────── */
#define LED_PIN             GPIO_Pin_1 /* PC1 green LED */

/* ── Sampling state ──────────────────────────────────────────────────────── */
#define STREAM_IDLE         0
#define STREAM_STREAMING    1

/* ADC channel numbers in canonical order. */
static const uint8_t ADC_CHANNELS[N_CHANNELS] = {0, 1, 2, 3, 4, 7};

static uint8_t stream_state = STREAM_IDLE;
static uint8_t sample_once_pending = 0;
static uint16_t avg_count = 0;      /* 0 (raw), 4, 8, 16, 32, 64, 128, 256 */
static uint8_t avg_shift = 0;       /* log2(avg_count); 0 when raw */
static uint8_t channel_mask = 0x3F; /* all 6 channels */
static uint8_t slim_format = 0;     /* v2 mask-sized frames when 1 */
static uint32_t sample_counter = 0; /* SAMPLE frame sequence (gap detection) */

/* ── TX sequence ─────────────────────────────────────────────────────────── */
static uint8_t tx_seq = 0;

/* ── RX ring buffer (USART ISR -> main loop) ────────────────────────────── */
#define RX_BUF_SIZE 64
static volatile uint8_t rx_buf[RX_BUF_SIZE];
static volatile uint8_t rx_head = 0;
static volatile uint8_t rx_tail = 0;

static uint8_t rx_available(void) {
    return rx_head != rx_tail;
}

static uint8_t rx_pop(void) {
    uint8_t b = rx_buf[rx_tail];
    rx_tail = (uint8_t)((rx_tail + 1) % RX_BUF_SIZE);
    return b;
}

/* Called from the USART1 ISR. Single producer (ISR), single consumer (main). */
void adc_rx_push(uint8_t b) {
    uint8_t next = (uint8_t)((rx_head + 1) % RX_BUF_SIZE);
    if (next != rx_tail) {
        rx_buf[rx_head] = b;
        rx_head = next;
    }
    /* else: ring full -> drop (commands are small and rare). */
}

/* ── CRC16 CCITT-FALSE through the 16-entry nibble table ────────────────── */
/* table[n] = the poly applied four shifting rounds to (n << 12); the host
 * codec (adc_wire/codec.py CRC_NIBBLE) derives and pins these constants. */
static const uint16_t CRC_NIBBLE[16] = {
    0x0000, 0x1021, 0x2042, 0x3063,
    0x4084, 0x50A5, 0x60C6, 0x70E7,
    0x8108, 0x9129, 0xA14A, 0xB16B,
    0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
};
static uint16_t crc16_nibble(uint16_t crc, uint8_t n) {
    return (uint16_t)((crc << 4) ^ CRC_NIBBLE[((crc >> 12) ^ n) & 0x0F]);
}
static uint16_t crc16_byte(uint16_t crc, uint8_t b) {
    crc = crc16_nibble(crc, (uint8_t)(b >> 4));
    return crc16_nibble(crc, (uint8_t)(b & 0x0F));
}

/* ── Millisecond tick (TIM2) for the revert guard ───────────────────────── */
static volatile uint32_t ms_ticks = 0;
static uint32_t ms_now(void) { return ms_ticks; }

void TIM2_IRQHandler(void) {
    if (TIM_GetITStatus(TIM2, TIM_IT_Update) != RESET) {
        TIM_ClearITPendingBit(TIM2, TIM_IT_Update);
        ms_ticks++;
    }
}

/* ── USART TX via DMA1_Channel4 (double-buffered) ───────────────────────── */
/* USART1_TX rides DMA1 Channel 4 and ADC1 rides Channel 1 (CH32V00X RM
 * V1.5, the DMA request map). Two staging buffers alternate: the CPU
 * builds frame N+1 into the free one while the DMA transmits frame N. */
#define TX_BUF_LEN 40 /* >= the largest frame: 5 + 16 + 2 = 23 B */
static uint8_t tx_buf[2][TX_BUF_LEN];
static uint8_t tx_active = 0;

static void dma_tx_wait(void) {
    uint32_t guard = 0;
    while (!DMA_GetFlagStatus(DMA1_FLAG_TC4)) {
        if (++guard > 4800000u) { /* ~100 ms bounded spin at 48 MHz */
            break;
        }
    }
    DMA_ClearFlag(DMA1_FLAG_TC4);
}

static void dma_tx_kick(const uint8_t *data, uint8_t len) {
    DMA_InitTypeDef d = {0};
    DMA_Cmd(DMA1_Channel4, DISABLE);
    DMA_ClearFlag(DMA1_FLAG_TC4);
    d.DMA_PeripheralBaseAddr = (uint32_t) & (USART1->DATAR);
    d.DMA_MemoryBaseAddr = (uint32_t)data;
    d.DMA_DIR = DMA_DIR_PeripheralDST;
    d.DMA_BufferSize = len;
    d.DMA_PeripheralDataSize = DMA_PeripheralDataSize_Byte;
    d.DMA_MemoryDataSize = DMA_MemoryDataSize_Byte;
    d.DMA_PeripheralInc = DMA_PeripheralInc_Disable;
    d.DMA_MemoryInc = DMA_MemoryInc_Enable;
    d.DMA_Mode = DMA_Mode_Normal;
    d.DMA_Priority = DMA_Priority_High;
    d.DMA_M2M = DMA_M2M_Disable;
    DMA_Init(DMA1_Channel4, &d);
    DMA_Cmd(DMA1_Channel4, ENABLE);
}

/* ── Frame encoder + DMA TX ──────────────────────────────────────────────── */
/* Commands wait for the transfer (an ACK must fully leave before a switch
 * applies); stream SAMPLE frames pipeline: build into the free staging
 * buffer while the previous frame is on the wire. */
static void send_frame(uint8_t type, const uint8_t *payload, uint8_t len) {
    uint8_t *out = tx_buf[tx_active];
    uint8_t i = 0;
    uint16_t crc = 0xFFFF;
    out[i++] = SYNC0;
    out[i++] = SYNC1;
    out[i++] = type;
    out[i++] = tx_seq++;
    out[i++] = len;
    for (uint8_t k = 0; k < len; k++) {
        out[i++] = payload[k];
    }
    crc = crc16_byte(crc, type);
    crc = crc16_byte(crc, out[3]);
    crc = crc16_byte(crc, len);
    for (uint8_t k = 0; k < len; k++) {
        crc = crc16_byte(crc, payload[k]);
    }
    out[i++] = (uint8_t)(crc & 0xFF);
    out[i++] = (uint8_t)(crc >> 8);
    dma_tx_kick(out, i);
    dma_tx_wait();
}

/* ── Response builders ────────────────────────────────────────────────── */
static void send_identify(void) {
    uint8_t p[7];
    p[0] = PROTOCOL_VERSION;
    p[1] = FW_MAJOR;
    p[2] = FW_MINOR;
    p[3] = N_CHANNELS;
    p[4] = 12; /* resolution bits */
    p[5] = (uint8_t)(DEVICE_CAPS & 0xFF);
    p[6] = (uint8_t)(DEVICE_CAPS >> 8);
    send_frame(TYPE_IDENTIFY_RSP, p, 7);
}
static void send_ack(uint8_t echo_type, uint16_t value) {
    uint8_t p[3];
    p[0] = echo_type;
    p[1] = (uint8_t)(value & 0xFF);
    p[2] = (uint8_t)(value >> 8);
    send_frame(TYPE_ACK, p, 3);
}

static void send_nak(uint8_t echo_type, uint8_t error) {
    uint8_t p[2];
    p[0] = echo_type;
    p[1] = error;
    send_frame(TYPE_NAK, p, 2);
}







/* The SAMPLE frame builder: u32 LE counter + the mask's channels (u16 LE
 * each). Legacy always sends the fixed six (disabled channels zero); slim
 * sends exactly the mask's active channels in canonical order. */
static uint8_t send_sample(uint32_t counter, const uint16_t ch6[]) {
    uint8_t *out = tx_buf[tx_active];
    uint8_t i = 0;
    uint16_t crc = 0xFFFF;
    uint8_t n_active = 0;
    out[i++] = SYNC0;
    out[i++] = SYNC1;
    out[i++] = TYPE_SAMPLE;
    out[i++] = tx_seq++;
    out[i++] = 0; /* LEN patched after the channel loop */
    out[i++] = (uint8_t)(counter & 0xFF);
    out[i++] = (uint8_t)((counter >> 8) & 0xFF);
    out[i++] = (uint8_t)((counter >> 16) & 0xFF);
    out[i++] = (uint8_t)((counter >> 24) & 0xFF);
    for (uint8_t c = 0; c < N_CHANNELS; c++) {
        if (slim_format && !(channel_mask & (1u << c))) {
            continue;
        }
        out[i++] = (uint8_t)(ch6[c] & 0xFF);
        out[i++] = (uint8_t)((ch6[c] >> 8) & 0xFF);
        n_active++;
    }
    out[4] = (uint8_t)(4 + 2 * n_active);
    crc = crc16_byte(crc, TYPE_SAMPLE);
    crc = crc16_byte(crc, out[3]);
    crc = crc16_byte(crc, out[4]);
    for (uint8_t k = 5; k < i; k++) {
        crc = crc16_byte(crc, out[k]);
    }
    out[i++] = (uint8_t)(crc & 0xFF);
    out[i++] = (uint8_t)(crc >> 8);
    dma_tx_kick(out, i);
    tx_active ^= 1; /* stream path pipelines; the next kick of THIS buffer waits */
    return i;
}

/* ── Revert guard (T_revert after a baud switch) ────────────────────────── */
static uint32_t revert_deadline_ms = 0; /* 0 = disarmed */
static void usart_set_baud(uint32_t baud);
static void revert_guard_arm(void) {
    revert_deadline_ms = ms_now() + T_REVERT_MS;
}
static void revert_guard_disarm(void) {
    revert_deadline_ms = 0;
}
static void revert_to_boot_state(void) {
    slim_format = 0;
    revert_guard_disarm();
    usart_set_baud(BAUD_2M);
}


/* ── RX state machine ────────────────────────────────────────────────────── */
typedef enum {
    RX_SYNC0,
    RX_SYNC1,
    RX_TYPE,
    RX_SEQ,
    RX_LEN,
    RX_PAYLOAD,
    RX_CRC_LO,
    RX_CRC_HI
} rx_state_t;

static rx_state_t rx_state = RX_SYNC0;
static uint8_t frame_type = 0;
static uint8_t frame_len = 0;
static uint8_t frame_payload[MAX_RX_PAYLOAD];
static uint8_t frame_payload_idx = 0;
static uint16_t rx_crc = 0;
static uint8_t frame_crc_lo = 0;

static uint8_t valid_averaging(uint16_t n) {
    switch (n) {
    case 0:
    case 4:
    case 8:
    case 16:
    case 32:
    case 64:
    case 128:
    case 256:
        return 1;
    default:
        return 0;
    }
}

static uint8_t log2_shift(uint16_t n) {
    uint8_t s = 0;
    while (n > 1) {
        n >>= 1;
        s++;
    }
    return s;
}

static void handle_frame(uint8_t type, const uint8_t *payload, uint8_t len);

static void rx_byte(uint8_t b) {
    switch (rx_state) {
    case RX_SYNC0:
        if (b == SYNC0)
            rx_state = RX_SYNC1;
        break;

    case RX_SYNC1:
        if (b == SYNC1)
            rx_state = RX_TYPE;
        else if (b != SYNC0)
            rx_state = RX_SYNC0;
        break;

    case RX_TYPE:
        frame_type = b;
        rx_crc = crc16_byte(0xFFFF, b);
        rx_state = RX_SEQ;
        break;

    case RX_SEQ:
        /* seq is not echoed, but it is part of the CRC. */
        rx_crc = crc16_byte(rx_crc, b);
        rx_state = RX_LEN;
        break;

    case RX_LEN:
        frame_len = b;
        rx_crc = crc16_byte(rx_crc, b);
        if (frame_len > MAX_RX_PAYLOAD) {
            rx_state = RX_SYNC0; /* corrupt length -> resync */
        } else if (frame_len == 0) {
            rx_state = RX_CRC_LO;
        } else {
            frame_payload_idx = 0;
            rx_state = RX_PAYLOAD;
        }
        break;

    case RX_PAYLOAD:
        frame_payload[frame_payload_idx++] = b;
        rx_crc = crc16_byte(rx_crc, b);
        if (frame_payload_idx == frame_len)
            rx_state = RX_CRC_LO;
        break;

    case RX_CRC_LO:
        frame_crc_lo = b;
        rx_state = RX_CRC_HI;
        break;

    case RX_CRC_HI: {
        uint16_t received = (uint16_t)(((uint16_t)b << 8) | frame_crc_lo);
        rx_state = RX_SYNC0;
        if (received == rx_crc) {
            handle_frame(frame_type, frame_payload, frame_len);
        }
        /* else: bad CRC -> silently drop (resync). */
        break;
    }
    }
}

static void handle_frame(uint8_t type, const uint8_t *payload, uint8_t len) {
    switch (type) {
    case TYPE_IDENTIFY:
        send_identify();
        break;
    case TYPE_SET_BAUD: {
        uint32_t baud;
        if (len < 4) {
            send_nak(type, ERR_BAD_PARAMETER);
            break;
        }
        baud = (uint32_t)payload[0] | ((uint32_t)payload[1] << 8) |
               ((uint32_t)payload[2] << 16) | ((uint32_t)payload[3] << 24);
        if (baud != SUPPORTED_BAUDS[0] && baud != SUPPORTED_BAUDS[1]) {
            send_nak(type, ERR_BAD_PARAMETER);
            break;
        }
        /* ACK first, at the CURRENT baud; the switch applies after the ACK
         * has fully left the wire (send_frame waits for the DMA TC). */
        send_ack(type, (uint16_t)(baud & 0xFFFF));
        usart_set_baud(baud);
        if (baud != BAUD_2M) {
            revert_guard_arm();
        }
        break;
    }

    case TYPE_SET_FRAME_FORMAT:
        if (len < 1 || payload[0] > 1) {
            send_nak(type, ERR_BAD_PARAMETER);
            break;
        }
        send_ack(type, payload[0]);
        slim_format = payload[0];
        revert_guard_disarm();
        break;

    case TYPE_SET_AVERAGING:
        if (len >= 2) {
            uint16_t n = (uint16_t)(payload[0] | ((uint16_t)payload[1] << 8));
            if (valid_averaging(n)) {
                avg_count = n;
                avg_shift = log2_shift(n);
                send_ack(type, n);
            } else {
                send_nak(type, ERR_BAD_PARAMETER);
            }
        } else {
            send_nak(type, ERR_BAD_PARAMETER);
        }
        break;

    case TYPE_SET_CHANNELS:
        if (len >= 1 && payload[0] <= 0x3F) {
            channel_mask = payload[0];
            ws2812_set_channels(channel_mask);
            send_ack(type, (uint16_t)payload[0]);
        } else {
            send_nak(type, ERR_BAD_PARAMETER);
        }
        break;

    case TYPE_SET_SAMPLE_MODE:
        if (len >= 1 && payload[0] == 0) {
            send_ack(type, 0); /* free-run */
        } else if (len >= 1) {
            send_nak(type, ERR_UNSUPPORTED); /* cycle/timer reserved */
        } else {
            send_nak(type, ERR_BAD_PARAMETER);
        }
        break;

    case TYPE_START_STREAM:
        stream_state = STREAM_STREAMING;
        send_ack(type, 0);
        break;

    case TYPE_STOP_STREAM:
        stream_state = STREAM_IDLE;
        send_ack(type, 0);
        break;

    case TYPE_SAMPLE_ONCE:
        sample_once_pending = 1;
        send_ack(type, 0);
        break;

    case TYPE_RESET:
        send_ack(type, 0);
        Delay_Ms(10);
        NVIC_SystemReset();
        break;

    default:
        send_nak(type, ERR_BAD_COMMAND);
        break;
    }
}

static void gpio_analog_init(void) {
    GPIO_InitTypeDef g = {0};
    RCC_PB2PeriphClockCmd(RCC_PB2Periph_GPIOA | RCC_PB2Periph_GPIOC | RCC_PB2Periph_GPIOD, ENABLE);

    g.GPIO_Mode = GPIO_Mode_AIN;
    g.GPIO_Pin = GPIO_Pin_2 | GPIO_Pin_6; /* PA2=A0, PA6=A1 */
    GPIO_Init(GPIOA, &g);
    g.GPIO_Pin = GPIO_Pin_4; /* PC4=A2 */
    GPIO_Init(GPIOC, &g);
    g.GPIO_Pin = GPIO_Pin_2 | GPIO_Pin_3 | GPIO_Pin_4; /* PD2=A3, PD3=A4, PD4=A7 */
    GPIO_Init(GPIOD, &g);
}

static void adc_init_base(void) {
    RCC_PB2PeriphClockCmd(RCC_PB2Periph_ADC1, ENABLE);
    RCC_ADCCLKConfig(RCC_PCLK2_Div8);
    ADC_DeInit(ADC1);
}

/* ── ADC: rule-group scan + DMA ──────────────────────────────────────────── */
#define ADC_RAW_LEN 8
static volatile uint16_t adc_raw[ADC_RAW_LEN];
static volatile uint8_t scan_done = 0;

void DMA1_Channel1_IRQHandler(void) {
    if (DMA_GetITStatus(DMA1_IT_TC1)) {
        DMA_ClearITPendingBit(DMA1_IT_TC1);
        scan_done++; /* one complete rule-group scan landed in adc_raw */
    }
}

static void adc_scan_reconfigure(void) {
    ADC_InitTypeDef a = {0};
    DMA_InitTypeDef d = {0};
    uint8_t n_active = 0;
    for (uint8_t c = 0; c < N_CHANNELS; c++) {
        if (channel_mask & (1u << c)) {
            ADC_RegularChannelConfig(ADC1, ADC_CHANNELS[c], (uint8_t)(n_active + 1),
                                     ADC_SampleTime_CyclesMode5);
            n_active++;
        }
    }
    if (n_active == 0) {
        n_active = 1; /* an all-zero mask still scans channel 0 */
        ADC_RegularChannelConfig(ADC1, ADC_CHANNELS[0], 1, ADC_SampleTime_CyclesMode5);
    }
    DMA_Cmd(DMA1_Channel1, DISABLE);
    DMA_ClearFlag(DMA1_FLAG_TC1);
    d.DMA_PeripheralBaseAddr = (uint32_t) & (ADC1->RDATAR);
    d.DMA_MemoryBaseAddr = (uint32_t)adc_raw;
    d.DMA_DIR = DMA_DIR_PeripheralSRC;
    d.DMA_BufferSize = n_active;
    d.DMA_PeripheralDataSize = DMA_PeripheralDataSize_HalfWord;
    d.DMA_MemoryDataSize = DMA_MemoryDataSize_HalfWord;
    d.DMA_PeripheralInc = DMA_PeripheralInc_Disable;
    d.DMA_MemoryInc = DMA_MemoryInc_Enable;
    d.DMA_Mode = DMA_Mode_Circular;
    d.DMA_Priority = DMA_Priority_High;
    d.DMA_M2M = DMA_M2M_Disable;
    DMA_Init(DMA1_Channel1, &d);
    DMA_ITConfig(DMA1_Channel1, DMA_IT_TC, ENABLE);
    DMA_Cmd(DMA1_Channel1, ENABLE);
    a.ADC_Mode = ADC_Mode_Independent;
    a.ADC_ScanConvMode = ENABLE;
    a.ADC_ContinuousConvMode = ENABLE;
    a.ADC_ExternalTrigConv = ADC_ExternalTrigConv_None;
    a.ADC_DataAlign = ADC_DataAlign_Right;
    a.ADC_NbrOfChannel = n_active;
    ADC_Init(ADC1, &a);
    ADC_DMACmd(ADC1, ENABLE);
    ADC_SoftwareStartConvCmd(ADC1, ENABLE);
}

/* Waits one frame's worth of scans (avg_count scans when averaging, else
 * one), folds them, and emits the six-wide array. ADC DMA circular mode
 * keeps adc_raw current; the TC interrupt counts completed scans. */
static void wait_scan(uint16_t out[N_CHANNELS]) {
    static uint32_t sum[N_CHANNELS];
    static uint16_t scans = 0;
    uint16_t scans_needed = (avg_count == 0) ? 1 : avg_count;
    for (;;) {
        uint8_t last = scan_done;
        uint32_t guard = 0;
        while (scan_done == last) {
            if (++guard > 480000u) {
                break; /* ~10 ms bounded: no live scan */
            }
        }
        uint8_t slot = 0;
        for (uint8_t c = 0; c < N_CHANNELS; c++) {
            if (channel_mask & (1u << c)) {
                sum[c] += adc_raw[slot++];
            } else {
                out[c] = 0;
            }
        }
        scans++;
        if (scans >= scans_needed) {
            for (uint8_t c = 0; c < N_CHANNELS; c++) {
                if (channel_mask & (1u << c)) {
                    out[c] = (uint16_t)(sum[c] >> avg_shift);
                    sum[c] = 0;
                }
            }
            scans = 0;
            return;
        }
    }
}

/* TIM2 as the 1 ms tick (48 MHz APB1; prescaler 48-1, period 1000-1). */
static void tim2_init(void) {
    TIM_TimeBaseInitTypeDef t = {0};
    RCC_PB1PeriphClockCmd(RCC_PB1Periph_TIM2, ENABLE);
    t.TIM_Prescaler = 48 - 1;
    t.TIM_Period = 1000 - 1;
    t.TIM_ClockDivision = TIM_CKD_DIV1;
    t.TIM_CounterMode = TIM_CounterMode_Up;
    TIM_TimeBaseInit(TIM2, &t);
    TIM_ClearITPendingBit(TIM2, TIM_IT_Update);
    TIM_ITConfig(TIM2, TIM_IT_Update, ENABLE);
    NVIC_EnableIRQ(TIM2_IRQn);
    TIM_Cmd(TIM2, ENABLE);
}

/* ── USART: boot at 2 Mbps, negotiable to 3 Mbps ────────────────────────── */
static void usart_init(void) {
    GPIO_InitTypeDef g = {0};
    USART_InitTypeDef u = {0};
    RCC_PB2PeriphClockCmd(RCC_PB2Periph_GPIOD | RCC_PB2Periph_USART1, ENABLE);
    RCC_HBPeriphClockCmd(RCC_HBPeriph_DMA1, ENABLE);
    g.GPIO_Pin = GPIO_Pin_5; /* TX PD5 */
    g.GPIO_Speed = GPIO_Speed_30MHz;
    g.GPIO_Mode = GPIO_Mode_AF_PP;
    GPIO_Init(GPIOD, &g);
    g.GPIO_Pin = GPIO_Pin_6; /* RX PD6 */
    g.GPIO_Mode = GPIO_Mode_IN_FLOATING;
    GPIO_Init(GPIOD, &g);
    u.USART_BaudRate = BAUD_2M;
    u.USART_WordLength = USART_WordLength_8b;
    u.USART_StopBits = USART_StopBits_1;
    u.USART_Parity = USART_Parity_No;
    u.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
    u.USART_Mode = USART_Mode_Tx | USART_Mode_Rx;
    USART_Init(USART1, &u);
    USART_DMACmd(USART1, USART_DMAReq_Tx, ENABLE);
    USART_ITConfig(USART1, USART_IT_RXNE, ENABLE);
    NVIC_EnableIRQ(USART1_IRQn);
    NVIC_EnableIRQ(DMA1_Channel1_IRQn);
    USART_Cmd(USART1, ENABLE);
}

/* The vendor divider arithmetic (ch32v00X_usart.c): mantissa in BRR[15:4],
 * fraction in 16ths in BRR[3:0]; 48 MHz PCLK2. USARTDIV = 1.0 at 3 Mbps. */
static void usart_set_baud(uint32_t baud) {
    uint32_t div = (25u * 48000000u) / (4u * baud);
    uint32_t mantissa = div / 100u;
    uint32_t fraction = ((div - (100u * mantissa)) * 16u + 50u) / 100u;
    dma_tx_wait(); /* nothing mid-frame across the switch */
    USART1->BRR = (mantissa << 4) | (fraction & 0x0Fu);
}

/* ── Green LED (PC1): solid on while streaming, slow blink when idle ────── */
static uint8_t led_state = 0;

static void led_init(void) {
    GPIO_InitTypeDef g = {0};
    RCC_PB2PeriphClockCmd(RCC_PB2Periph_GPIOC, ENABLE);
    g.GPIO_Pin = LED_PIN;
    g.GPIO_Mode = GPIO_Mode_Out_PP;
    g.GPIO_Speed = GPIO_Speed_30MHz;
    GPIO_Init(GPIOC, &g);
    GPIO_WriteBit(GPIOC, LED_PIN, Bit_RESET);
}

static void led_on(void) {
    led_state = 1;
    GPIO_WriteBit(GPIOC, LED_PIN, Bit_SET);
}

static void led_off(void) {
    led_state = 0;
    GPIO_WriteBit(GPIOC, LED_PIN, Bit_RESET);
}

static void led_toggle(void) {
    led_state = (uint8_t)(led_state ^ 1);
    GPIO_WriteBit(GPIOC, LED_PIN, led_state ? Bit_SET : Bit_RESET);
}

static void led_boot_blink(void) {
    for (uint8_t i = 0; i < 3; i++) {
        led_on();
        Delay_Ms(80);
        led_off();
        Delay_Ms(80);
    }
}

/* ── Main ────────────────────────────────────────────────────────────────── */
/* Approximate idle heartbeat period (loop-iteration counter). */
#define HEARTBEAT_TICKS 100000

int main(void) {
    uint16_t samples[N_CHANNELS];
    uint32_t idle_ticks = 0;
    NVIC_PriorityGroupConfig(NVIC_PriorityGroup_1);
    SystemCoreClockUpdate();
    Delay_Init();
    Delay_Ms(100);
    GPIO_PinRemapConfig(GPIO_Remap_PA1_2, DISABLE);
    led_init();
    gpio_analog_init();
    adc_init_base();
    adc_scan_reconfigure();
    usart_init();
    tim2_init();
    ws2812_init();
    led_boot_blink();
    ws2812_set_all(WS2812_BRIGHT, 0, 0);
    Delay_Ms(300);
    ws2812_set_all(0, WS2812_BRIGHT, 0);
    Delay_Ms(300);
    ws2812_set_all(0, 0, WS2812_BRIGHT);
    Delay_Ms(300);
    ws2812_set_all(WS2812_BRIGHT, WS2812_BRIGHT * 2 / 3, 0);
    while (1) {
        while (rx_available()) {
            rx_byte(rx_pop());
        }
        if (revert_deadline_ms != 0 && ms_now() >= revert_deadline_ms) {
            revert_to_boot_state();
        }
        if (stream_state == STREAM_STREAMING) {
            led_on();
            wait_scan(samples);
            send_sample(sample_counter++, samples);
        } else if (sample_once_pending) {
            sample_once_pending = 0;
            wait_scan(samples);
            send_sample(sample_counter++, samples);
        } else {
            if (++idle_ticks >= HEARTBEAT_TICKS) {
                idle_ticks = 0;
                led_toggle();
            }
        }
    }
}

