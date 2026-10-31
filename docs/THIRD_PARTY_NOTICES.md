# Third-Party Notices

The local collector transport was informed by the protocol research published
in [SmartESS Local](https://github.com/ubombi/ha-smartess-local). Its MIT
license notice is reproduced below.

```text
MIT License

Copyright (c) 2026 Vitalii Kozlovskyi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

The read-only SMG register implementation uses protocol facts from the
published `Modbus_RTU RS232 communication protocol, Version 1.0` distributed
with [syssi/esphome-smg-ii](https://github.com/syssi/esphome-smg-ii). No code or
configuration from that GPL-licensed project is included here.

[EyeBond Local](https://github.com/groove-max/ha-eybond-local) was reviewed as
an architectural and interoperability reference. No MPL-licensed source or
catalog files from that project are included here.

The PI18 field layout and firmware format use protocol facts from
[`PI18_InfiniSolar-V-protocol-20170926`](https://github.com/user-attachments/files/26123288/PI18_InfiniSolar-V-protocol-20170926.pdf),
shared in issue #17. Raw XMODEM CRC interoperability was cross-checked against
[Dess Monitor Local's PI18 codec](https://github.com/Antoxa1081/home-assistant-dess-monitor-local/blob/main/custom_components/dess_monitor_local/api/decoders/pi18.py).
No source code from that codec is included here; regression frames use synthetic
data and Python's independent standard-library CRC implementation.

The cloud time/clock control serialization was informed by the public DessMonitor
web client's `queryDeviceCtrlValue` / `ctrlDevice` string round-trip behavior,
observed on 2026-10-15 in
[`chunk-4eb723b8.221dae61.js`](https://www.dessmonitor.com/js/chunk-4eb723b8.221dae61.js).
Only interface behavior was used; no vendor JavaScript is included. Read formats
for the five devcode 6544 fields were independently observed in hardware logs.
This establishes client serialization, not successful on-device write validation.

The Modbus protocol-number 4 layout uses register addresses, data types, and
scales from `Communication.Protocol.No.3-10.docx`, published in
[PreK/esphome-anenji-11kw-native-modbus](https://github.com/PreK/esphome-anenji-11kw-native-modbus/blob/55a330585846d57b4f24e6467201d8dde8985ee7/Communication.Protocol.No.3-10.docx).
The decoder is independently implemented; the document and that project's
ESPHome configuration are not redistributed here. Regression data consists of
read-only hardware register samples with identifying information removed.
