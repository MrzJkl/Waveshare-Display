# Working with Raspberry Pi Pico

URL: https://docs.waveshare.com/RGB-Matrix-Px-64x32/Rasberry-Pico

## Working with Raspberry Pi Pico

For environment setup, refer to: [https://docs.waveshare.com/Raspberry-Pi-Pico-C-Tutorials](https://docs.waveshare.com/Raspberry-Pi-Pico-C-Tutorials)

### Hardware Connection

#### Required Components

- RGB-Matrix-P4-64x32 (included in this product)
- 2 × 8PIN 2.54mm pitch cable (included in this product)
- Raspberry Pi Pico (must be purchased separately)

#### Hardware Connection

![](https://docs.waveshare.com/assets/images/HUB75-GPIO-define-4fcc7f8b11b60a490cceddd451d7ec8f.webp)

![](https://docs.waveshare.com/assets/images/Pico-connect-ebba227a937b15efa24ff06053b7095b.webp)

#### Importing the Project

![](https://docs.waveshare.com/assets/images/Pico-setting-01-9031b9ce92428bc0ab6b49b93839657b.webp)

#### Flashing Process

In the terminal shown above, enter the following commands:

resolution switching By changing the `PANEL_PROFILE` parameter in the root `CMakeLists.txt` , you can change the panel size to be displayed.

Currently supported resolution profiles:

- 64X32_1_16
- 64X64_1_32
- 80X40_1_20
- 96X48_1_24
Specify via command line (execute in the project root directory to switch to 64x32):

```bash
cmake -S . -B build -G Ninja -DPANEL_PROFILE=64X32_1_16
cmake --build build
```

After compilation completes, press and hold the BOOT button on the board while powering it on, then click the RUN icon to flash the firmware.

#### Operation Result

|  |  |  |
| --- | --- | --- |
| ![64x32-Pico-01](https://docs.waveshare.com/assets/images/Pico-example-01-a5fd6f79641967a19244115dd94c922e.webp) | ![64x32-Pico-02](https://docs.waveshare.com/assets/images/Pico-example-02-8905c990dcf458c7b8489d8e955df46e.webp) | ![64x32-Pico-03](https://docs.waveshare.com/assets/images/Pico-example-03-a5423a82e400da636ff0d949d4b6c690.webp) |

[Give Feedback](https://docs.google.com/forms/d/e/1FAIpQLSfayJEZ5J-dp-3Wq_dkWsVRhNuQ6C79_GNV62mYuFW8Mj6U8Q/viewform?entry.803599728=https%3A%2F%2Fdocs.waveshare.com%2FRGB-Matrix-Px-64x32%2FRasberry-Pico)