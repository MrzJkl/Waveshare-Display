# Raspberry Pi Pico C/C++ Getting Started

URL: https://docs.waveshare.com/Raspberry-Pi-Pico-C-Tutorials

> This tutorial will introduce how to use the Pico VS Code extension for C/C++ development and guide you through configuring a C/C++ development environment based on the Pico SDK.

> **Important Note: Development Board Compatibility**
>
> The core logic of this tutorial applies to all RP2040 and RP2350 series boards, but all steps are demonstrated using the [**Raspberry Pi Pico 2**](https://www.waveshare.com/raspberry-pi-pico-2.htm?sku=28568) as an example. If you are using a development board of another model, please modify the corresponding settings according to the actual situation.

## 1. What is Pico C/C++ Development

Raspberry Pi Pico C/C++ development is based on the official **[Pico SDK](https://www.raspberrypi.com/documentation/microcontrollers/c_sdk.html)** , a C/C++ software development kit designed for RP2040, RP2350, and other series chips. The Pico SDK provides a rich set of API libraries for controlling peripherals such as GPIO, I2C, SPI, PWM, and ADC, as well as advanced features like multi-core processing, timers, and DMA.

To simplify the setup and use of the C/C++ development environment, the Raspberry Pi team has released the **Pico VS Code extension** . This extension integrates the following features:

- **One-Click Installation:** Automatically installs and manages development dependencies such as the Pico SDK, CMake, and compiler toolchain.
- **Project Management:** Quickly create, import, and configure C/C++ projects through a graphical wizard.
- **Compilation and Building:** Integrates CMake and Ninja build systems for one-click compilation and UF2 firmware generation.
- **Flashing and Debugging:** Supports UF2 firmware flashing and enables breakpoint debugging, single-step execution, and variable inspection via OpenOCD.
- **Cross-Platform Support:** Provides a unified development experience on Windows, macOS, and Linux.

> **Scope of application**
>
> - This tutorial is applicable to the Raspberry Pi Pico, Pico 2, and all RP series development boards developed by Waveshare Electronics.
> - The installation tutorial uses Windows 11 as the default example. For other operating systems, please refer to the [official Raspberry Pi tutorial](https://www.raspberrypi.com/news/pico-vscode-extension/) .

## 2. Installing the Visual Studio Code Editor

1. Download and install [Visual Studio Code](https://code.visualstudio.com/) .
2. During installation, it is recommended to check the option **Add "Open with Code" action to Windows Explorer file context menu** to easily open project folders.

> **tip**
>
> If VS Code is already installed, please check if the version is v1.87.0 or higher.

![](https://docs.waveshare.com/assets/images/01-VSCode-Install-2-2837d7a2952346fff32695f017e5f032.webp)

![](https://docs.waveshare.com/assets/images/01-VSCode-Install-3-908b13278c1869773d2b1f9f24803437.webp)

## 3. Installing the Pico Extension

1. Download and extract the [pico-vscode installation package](https://drive.google.com/file/d/15UXWTwxse9XLQJYCpXNQidMHAMnC5ELF/view) .
2. Open VS Code, go to the Extensions view, and select "Install from VSIX".

![](https://docs.waveshare.com/assets/images/01-VSCode-Install-4-6880defc3b879c1e4f01757fe39252b4.webp)
3. Select the `.vsix` file from the pico-vscode package and click "Install".

![](https://docs.waveshare.com/assets/images/01-VSCode-Install-5-9211e6117847e47ebaea92862867947f.webp)
4. VS Code will then automatically install the Raspberry Pi Pico extension and its dependencies. You can click the refresh icon to view the installation progress.

![](https://docs.waveshare.com/assets/images/01-VSCode-Install-6-c336d290ac8c2d84f572e0280daa015c.webp)
5. After installation completes, a notification will appear in the lower-right corner.

![](https://docs.waveshare.com/assets/images/01-VSCode-Install-7-e215eb28e672a611546fae313ae2d6b2.webp)
6. The provided extension version is 0.21.0; you can update it to the latest version as needed.

![](https://docs.waveshare.com/assets/images/01-VSCode-Import-Update-03a8157db2823b0b2d0f3c280b05240b.webp)

## 4. Configuring the C/C++ Development Environment

1. Navigate to `C:\Users\username` and copy the entire `.pico-sdk` folder from the installation package into this directory.

![](https://docs.waveshare.com/assets/images/01-VSCode-Configuration-1-2cfb9a6be8aaffa43b37b4b18d7ca0da.webp)
2. After copying, the directory should appear as follows:

![](https://docs.waveshare.com/assets/images/01-VSCode-Configuration-2-5767262f1ed247bba73c444497c0b7d1.webp)
3. Open VS Code and configure the various paths in the Raspberry Pi Pico extension settings.

![](https://docs.waveshare.com/assets/images/01-VSCode-Configuration-3-5c8b30d3063317c5194cacdd19d679d6.webp)

The configuration is as follows:

```text
Cmake Path:
${HOME}/.pico-sdk/cmake/v3.28.6/bin/cmake.exe

Git Path:
${HOME}/.pico-sdk/git/cmd/git.exe

Ninja Path:
${HOME}/.pico-sdk/ninja/v1.12.1/ninja.exe

Python3 Path:
${HOME}/.pico-sdk/python/3.12.1/python.exe
```

## 5. Creating a New Project

1. After the configuration is complete, you can create a new project for testing. Enter the project name, select the save path, and then click **Create** to create the project. If you want to use the official example code, you can click **Example** next to the project name to select it.

![](https://docs.waveshare.com/assets/images/01-VSCode-New-Project-1-7f683a661926cf7013dbc0f7e2f7c248.webp)
2. A project successfully created.

![](https://docs.waveshare.com/assets/images/01-VSCode-New-Project-2-e01f515b4e6068e6a2281b6094abee15.webp)

## 6. Compiling the C/C++ Project

1. On first compilation, you need to select the Pico SDK version. The installation package includes Pico SDK versions 2.0, 2.2, and 2.3.

![](https://docs.waveshare.com/assets/images/01-VSCode-Compile-1-8730347e79eefd5b941bdabca8b8146b.webp)
2. Select **Yes** for advanced configuration.
3. Select the cross-compilation toolchain:

- ARM core toolchains (support RP2040 and RP2350 series boards):
- 13.2.Rel1
- 14_2_Rel1
- 15_2_Rel1
- RISC-V core toolchains (support RP2350 series boards):
- RISCV.13.3
- RISCV_ZCB_RPI_2_2_0_3
- RISCV_ZCB_RPI_2_3_0_0
Choose the appropriate toolchain based on your development board and requirements.

![](https://docs.waveshare.com/assets/images/01-VSCode-Compile-3-b40dcc6f0c312f8ecb814afa5b8eada4.webp)
4. ARM core toolchains (support RP2040 and RP2350 series boards):
- 13.2.Rel1
- 14_2_Rel1
- 15_2_Rel1
5. 13.2.Rel1
6. 14_2_Rel1
7. 15_2_Rel1
8. RISC-V core toolchains (support RP2350 series boards):
- RISCV.13.3
- RISCV_ZCB_RPI_2_2_0_3
- RISCV_ZCB_RPI_2_3_0_0
9. RISCV.13.3
10. RISCV_ZCB_RPI_2_2_0_3
11. RISCV_ZCB_RPI_2_3_0_0
12. For the CMake version, select **Default** (using the path configured earlier).

![](https://docs.waveshare.com/assets/images/01-VSCode-Compile-4-60e4ac18b35f545c5e06d1d564f7f109.webp)
13. For the Ninja build tool version, select **Default** (using the path configured earlier).

![](https://docs.waveshare.com/assets/images/01-VSCode-Compile-5-dba628b7dc3c11c348ce1816aad2308e.webp)
14. Select the development board.

![](https://docs.waveshare.com/assets/images/01-VSCode-Compile-6-1ef3d3daca77e44a5785ace295ac8502.webp)
15. After completing the configuration, click the **Compile** button to start compiling.

![](https://docs.waveshare.com/assets/images/01-VSCode-Compile-7-5552722104051690f31753d4f54ff6a7.webp)
16. After successful compilation, a firmware file in `uf2` format will be generated in the `build` directory of the project.

![](https://docs.waveshare.com/assets/images/01-VSCode-Compile-8-ef5d60f85bcbf2341c18b54a61757bac.webp)

## 7. Flashing the Firmware

Two methods are available for flashing the compiled firmware onto the development board:

1. **Flashing using the Pico VS Code plugin**

Connect the board to your computer via USB, then click the **Run** button to flash the firmware directly.

![](https://docs.waveshare.com/assets/images/01-VSCode-Run-bf6b049e2c66ecbd4cefb5969af5f5c0.webp)
2. **Manually flashing the firmware**

```text
1. Press and hold the BOOT button on the board.
2. Connect the board to your computer via USB.
3. The computer will recognize the development board as a USB device.
4. Drag and drop the `.uf2` firmware file into the USB drive.
5. The device will automatically reboot and complete the firmware flashing.
```

## 8. Importing a C/C++ Project

1. In the Pico VS Code extension, select "Import Project", then choose the directory where your project is located.

![](https://docs.waveshare.com/assets/images/01-VSCode-Import-1-98cd2e2287ee9b4682cbf9061a48946c.webp)
2. **Important Note:** The `CMakeLists.txt` file in the imported project must not contain any Chinese characters (including in comments), otherwise the import may fail.
3. **Development Board Configuration:** After importing the project, you need to check if the `CMakeLists.txt` file contains the development board configuration code. The following configuration is required for proper switching between Pico and Pico 2:

![](https://docs.waveshare.com/assets/images/01-VSCode-Import-2-ec1bb0ba3c4041fcd6fb40945b9308fa.webp)

```text
set(PICO_BOARD pico2 CACHE STRING "Board type")
```

> **tip**
>
> If this configuration is not present in `CMakeLists.txt` , even if Pico 2 is selected in VS Code, the compiled firmware will still be for the original Pico.

## 9. Debugging a C/C++ Project

The Pico/Pico 2 supports an external debugger for program flashing and debugging, allowing breakpoint analysis and runtime status inspection. Debugging the Pico/Pico 2 requires using the SWD (Serial Wire Debug) interface together with an external debugger.

You can use an [**RP2350-GEEK**](https://www.waveshare.com/rp2350-geek.htm) , [**Raspberry Pi Debug Probe**](https://www.waveshare.com/raspberry-pi-debug-probe.htm) , or another [**Pico**](https://www.waveshare.com/rp2040-plus.htm?sku=23504) / [**Pico 2**](https://www.waveshare.com/rp2350-plus.htm?sku=29414) board as an external debugger. Below we describe the steps for connecting the different debuggers to the Pico/Pico 2 debugging interface for program flashing and debugging.

1. Hardware connection

- RP2350-GEEK
- Raspberry Pi Debug Probe
- Pico/Pico 2
The RP2350-GEEK is a development board designed by Waveshare for geeks. It features a USB-A male connector, a 1.14inch LCD screen, a TF card slot, and other peripherals, and breaks out SWD, UART, and I2C interfaces. After flashing the corresponding [**Debugprobe firmware**](https://files.waveshare.com/wiki/common/Debugprobe_pico.zip) , the RP2350-GEEK becomes a USB → SWD and UART bridge. Connect it to the Pico/Pico 2 for debugging as shown below.

![](https://docs.waveshare.com/assets/images/01-VSCode-Debugger-1-428d2de86d1eeffb8e556347fe0b9376.webp)

RP2350-GEEK (left) to Pico (right). Detailed connections:

```text
RP2350-GEEK GND -> Pico GND
RP2350-GEEK GP2 -> Pico SWCLK
RP2350-GEEK GP3 -> Pico SWDIO
RP2350-GEEK GP4/UART1 TX -> Pico GP1/UART0 RX
RP2350-GEEK GP5/UART1 RX -> Pico GP0/UART0 TX
```
2. RP2350-GEEK
3. Raspberry Pi Debug Probe
4. Pico/Pico 2
5. Importing the project

When creating or importing a project, select the DebugProbe debugging method.

![](https://docs.waveshare.com/assets/images/01-VSCode-Debug-1-48b1ea805d8f6366656e41afc2938ad0.webp)
6. Flashing the program

After connecting the debugger, you can directly use the debugger to flash the program.

![](https://docs.waveshare.com/assets/images/01-VSCode-Debug-2-58bebc062ddeb6a49303c79699480e1f.webp)

- ① Go to the Pico VS Code extension page
- ② Click SWD to flash the program
7. ① Go to the Pico VS Code extension page
8. ② Click SWD to flash the program
9. Debugging the program

![](https://docs.waveshare.com/assets/images/01-VSCode-Debug-3-c0f5233ad624298384ff1a637036ecf7.webp)

- ① Click Debug Project
- ② Select Pico Debug
10. ① Click Debug Project
11. ② Select Pico Debug
12. Interface description

![](https://docs.waveshare.com/assets/images/01-VSCode-Debug-4-9a74c53036b405c6b76730f2729c13c4.webp)

- ① Restart the device
- ② Continue running the program
- ③ Step over
- ④ Step into
- ⑤ Step out
- ⑥ Restart debugging
- ⑦ Stop debugging
- ⑧ Serial monitor
- ⑨ Variables window
- ⑩ Watch window
13. ① Restart the device
14. ② Continue running the program
15. ③ Step over
16. ④ Step into
17. ⑤ Step out
18. ⑥ Restart debugging
19. ⑦ Stop debugging
20. ⑧ Serial monitor
21. ⑨ Variables window
22. ⑩ Watch window
23. Breakpoint debugging

![](https://docs.waveshare.com/assets/images/01-VSCode-Debug-5-2af9cefffbc70f28e1e70ed9b2a760e3.webp)

- ① Click in front of a line number to add/remove a breakpoint
- ② Breakpoints can be added or removed at any time during debugging
- ③ In multicore debugging, breakpoints can be used to switch between cores
24. ① Click in front of a line number to add/remove a breakpoint
25. ② Breakpoints can be added or removed at any time during debugging
26. ③ In multicore debugging, breakpoints can be used to switch between cores

## 10. Reference Links

- [Raspberry Pi Pico VS Code Extension Notes](https://www.raspberrypi.com/news/pico-vscode-extension/)
- [Pico VS Code GitHub](https://github.com/raspberrypi/pico-vscode)
- [Pico Debug Manual](https://datasheets.raspberrypi.com/pico/getting-started-with-pico.pdf)
- [Debugprobe GitHub](https://github.com/raspberrypi/debugprobe)

[Give Feedback](https://docs.google.com/forms/d/e/1FAIpQLSfayJEZ5J-dp-3Wq_dkWsVRhNuQ6C79_GNV62mYuFW8Mj6U8Q/viewform?entry.803599728=https%3A%2F%2Fdocs.waveshare.com%2FRaspberry-Pi-Pico-C-Tutorials)