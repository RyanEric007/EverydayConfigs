"""Small boot-time setup for PinPulse Control Deck."""

import gc
import machine

# The ESP32-S3 supports 240 MHz and the dashboard can change it later.
machine.freq(240_000_000)
gc.collect()
