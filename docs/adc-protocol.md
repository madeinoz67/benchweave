# ADC 6-channel 12-bit board — protocol

The canonical protocol documents live with the device project at
`plugins/benchweave/adc_6ch_12bit/`. Read
`plugins/benchweave/adc_6ch_12bit/docs/wire-protocol.md` for the v2 wire
family (mask-sized frames, baud/frame-format negotiation) and
`plugins/benchweave/adc_6ch_12bit/docs/rate-model.md` for the modelled
rate table, which the project's own tests regenerate. The v2 firmware
builds from the project's Makefile; see
`plugins/benchweave/adc_6ch_12bit/docs/flashing-and-recovery.md`.
