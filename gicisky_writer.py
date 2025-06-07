#!/usr/bin/env python3
"""
Standalone Gicisky E-ink Tag Writer
Adapted from https://github.com/eigger/hass-gicisky/blob/master/custom_components/gicisky/gicisky_ble/writer.py
This script allows you to connect to a Gicisky e-ink tag via Bluetooth Low Energy (BLE)
"""

from __future__ import annotations
from enum import Enum
import logging
import struct
import traceback
from typing import Any, Callable, TypeVar
from asyncio import Event, wait_for, sleep
from PIL import Image
from bleak import BleakClient, BleakError, BleakScanner
from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)

# Device configuration class
class DeviceConfig:
    def __init__(self, width=296, height=128, red=True, tft=False, rotation=0, 
                 mirror_x=False, mirror_y=True, compression=False):
        self.width = width
        self.height = height
        self.red = red
        self.tft = tft
        self.rotation = rotation
        self.mirror_x = mirror_x
        self.mirror_y = mirror_y
        self.compression = compression

# Exception definitions
class BleakCharacteristicMissing(BleakError):
    """Characteristic Missing"""

class BleakServiceMissing(BleakError):
    """Service Missing"""

WrapFuncType = TypeVar("WrapFuncType", bound=Callable[..., Any])

def disconnect_on_missing_services(func: WrapFuncType) -> WrapFuncType:
    """Missing services"""
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except (BleakServiceMissing, BleakCharacteristicMissing):
            if self.client.is_connected:
                await self.client.clear_cache()
                await self.client.disconnect()
            raise
    return wrapper  # type: ignore

async def update_image(
    ble_device: BLEDevice,
    device: DeviceConfig,
    image: Image,
    threshold: int = 128,
    red_threshold: int = 128
) -> bool:
    """Update image on e-ink tag"""
    client: BleakClient | None = None
    try:
        client = BleakClient(ble_device.address)
        await client.connect()
        
        services = client.services
        char_uuids = [
            c.uuid
            for svc in services if svc.uuid.lower().startswith("0000f")
            for c in svc.characteristics
        ]
        if len(char_uuids) < 2:
            raise BleakServiceMissing(f"UUID Len: {len(char_uuids)}")
        
        sorted_uuids = sorted(char_uuids, key=lambda x: int(x[4:8], 16))
        gicisky = GiciskyClient(client, sorted_uuids, device)
        await gicisky.start_notify()
        success = await gicisky.write_image(image, threshold, red_threshold)
        await gicisky.stop_notify()
        return success
    except Exception as e:
        _LOGGER.error(f"Fail update: {e}")
        _LOGGER.error(traceback.format_exc())
        return False
    finally:
        if client:
            try:
                if client.is_connected:
                    await client.disconnect()
            except Exception as e:
                _LOGGER.warning(f"{ble_device.address} Already disconnected: {e}")

class GiciskyClient:
    class Status(Enum):
        START = 0
        SIZE_DATA = 1
        IMAGE = 2
        IMAGE_DATA = 3
        
    def __init__(
        self,
        client: BleakClient,
        uuids: list[str],
        device: DeviceConfig
    ) -> None:
        self.client = client
        self.cmd_uuid, self.img_uuid = uuids[:2]
        self.width = device.width
        self.height = device.height
        self.support_red = device.red
        self.tft = device.tft
        self.rotation = device.rotation
        self.mirror_x = device.mirror_x
        self.mirror_y = device.mirror_y
        self.compression = device.compression
        self.packet_size = 0
        self.event: Event = Event()
        self.command_data: bytes | None = None
        self.image_packets: list[int] = []

    @disconnect_on_missing_services
    async def start_notify(self) -> None:
        await self.client.start_notify(self.cmd_uuid, self._notification_handler)
        await sleep(1.0)

    @disconnect_on_missing_services
    async def stop_notify(self) -> None:
        await self.client.stop_notify(self.cmd_uuid)

    @disconnect_on_missing_services
    async def write(self, uuid: str, data: bytes) -> None:
        _LOGGER.debug("Write UUID=%s data=%s", uuid, len(data))
        chunk = len(data)
        for i in range(0, len(data), chunk):
            await self.client.write_gatt_char(uuid, data[i : i + chunk])

    def _notification_handler(self, _: Any, data: bytearray) -> None:
        if self.command_data == None:
            self.command_data = bytes(data)
            self.event.set()

    async def read(self, timeout: float = 30.0) -> bytes:
        await wait_for(self.event.wait(), timeout)
        data = self.command_data or b""
        _LOGGER.debug("Received: %s", data.hex())
        return data

    async def write_with_response(self, uuid, packet: bytes) -> bytes:
        last_exception = None
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                self.command_data = None
                self.event.clear()
                await self.write(uuid, packet)
                return await self.read()
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    _LOGGER.warning(f"Write retry (attempt {attempt}/{max_retries})")
                    await sleep(0.5)
                    continue
                raise last_exception

    async def write_start_with_response(self) -> bytes:
        return await self.write_with_response(self.cmd_uuid, self._make_cmd_packet(0x01))

    async def write_size_with_response(self) -> bytes:
        return await self.write_with_response(self.cmd_uuid, self._make_cmd_packet(0x02))

    async def write_start_image_with_response(self) -> bytes:
        return await self.write_with_response(self.cmd_uuid, self._make_cmd_packet(0x03))

    async def write_image_with_response(self, part: int) -> bytes:
        return await self.write_with_response(self.img_uuid, self._make_size_packet(part))
    
    async def write_image(self, image: Image, threshold: int, red_threshold: int) -> bool:
        part = 0
        count = 0
        status = self.Status.START
        self.image_packets = self._make_image_packet(image, threshold, red_threshold)
        self.packet_size = len(self.image_packets)
        try:
            while True:
                if status == self.Status.START:
                    data = await self.write_start_with_response()
                    if len(data) < 3 or data[0] != 0x01 or data[1] != 0xF4 or data[2] != 0x00:
                        raise Exception(f"Packet Error: {data}")
                    status = self.Status.SIZE_DATA
                
                elif status == self.Status.SIZE_DATA:  
                    data = await self.write_size_with_response()
                    if len(data) < 1 or data[0] != 0x02:
                        raise Exception(f"Packet Error: {data}")
                    status = self.Status.IMAGE

                elif status == self.Status.IMAGE:  
                    data = await self.write_start_image_with_response()
                    if len(data) < 6 or data[0] != 0x05 or data[1] != 0x00:
                        raise Exception(f"Packet Error: {data}")
                    status = self.Status.IMAGE_DATA

                elif status == self.Status.IMAGE_DATA:  
                    data = await self.write_image_with_response(part)
                    if len(data) < 6 or data[0] != 0x05 or data[1] != 0x00:
                        break
                    part = int.from_bytes(data[2:6], "little")
                    count += 1
                    if part != count:
                        raise Exception(f"Count Error: {part} {count}")
                else:
                    raise Exception(f"Status Error: {status}")
            return True
        except Exception as e:
            _LOGGER.error("Fail write: %s", e)
            return False
        finally:
            _LOGGER.debug("Finish")

    def _overlay_images(
        self,
        base: Image,
        overlay: Image,
        position: tuple[int, int] = (0, 0),
        center: bool = False
    ) -> Image:
        if base.mode != 'RGB':
            base_rgb = base.convert('RGB')
        else:
            base_rgb = base.copy()

        w_base, h_base = base_rgb.size

        ov = overlay.convert('RGB')
        if ov.width > w_base or ov.height > h_base:
            ov = ov.crop((0, 0, w_base, h_base))

        if center:
            x = (w_base - ov.width) // 2
            y = (h_base - ov.height) // 2
            position = (x, y)

        base_rgb.paste(ov, position)

        return base_rgb

    def _make_image_packet(self, image: Image, threshold: int, red_threshold: int) -> list[int]:
        img = Image.new('RGB', (self.width, self.height), color='white')
        img = self._overlay_images(img, image)
        tft = self.tft
        rotation = self.rotation
        width, height = img.size
        
        if tft:
            img = img.resize((width // 2, height * 2), resample=Image.BICUBIC)

        if rotation != 0:
            img = img.rotate(rotation, expand=True)

        width, height = img.size
        pixels = img.load()

        byte_data = []
        byte_data_red = []
        current_byte = 0
        current_byte_red = 0
        bit_pos = 7

        for y in range(height - 1, -1, -1) if self.mirror_y else range(height):
            for x in range(width - 1, -1, -1) if self.mirror_x else range(width):
                px = (x, y)
                r, g, b = pixels[px]

                luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
                if self.compression:
                    if luminance < threshold:
                        current_byte |= (1 << bit_pos)
                else:
                    if luminance > threshold:
                        current_byte |= (1 << bit_pos)
                if (r > red_threshold) and (g < red_threshold):
                    current_byte_red |= (1 << bit_pos)

                bit_pos -= 1
                if bit_pos < 0:
                    byte_data.append(current_byte)
                    byte_data_red.append(current_byte_red)
                    current_byte = 0
                    current_byte_red = 0
                    bit_pos = 7

        if bit_pos != 7:
            byte_data.append(current_byte)
            byte_data_red.append(current_byte_red)

        if self.compression:
            return self._compress_byte_data(byte_data, byte_data_red)
        
        combined = byte_data + byte_data_red if self.support_red else byte_data
        return list(bytearray(combined))

    def _compress_byte_data(self, byte_data, byte_data_red) -> list[int]:
        byte_per_line = self.height // 8
        buf = [0x00, 0x00, 0x00, 0x00]
        pos = 0
        for _ in range(self.width):
            buf.extend([
                0x75,
                byte_per_line + 7,
                byte_per_line,
                0x00, 0x00, 0x00, 0x00
            ])
            buf.extend(byte_data[pos:pos + byte_per_line])
            pos += byte_per_line

        if byte_data_red is not None:
            pos = 0
            for _ in range(self.width):
                buf.extend([
                    0x75,
                    byte_per_line + 7,
                    byte_per_line,
                    0x00, 0x00, 0x00, 0x00
                ])
                buf.extend(byte_data_red[pos:pos + byte_per_line])
                pos += byte_per_line

        total_len = len(buf)
        buf[0] =  total_len        & 0xFF
        buf[1] = (total_len >>  8) & 0xFF
        buf[2] = (total_len >> 16) & 0xFF
        buf[3] = (total_len >> 24) & 0xFF

        return list(bytearray(buf))

    def _make_cmd_packet(self, cmd: int) -> bytes:
        if cmd == 0x02:
            packet = bytearray(8)
            packet[0] = cmd
            struct.pack_into("<I", packet, 1, self.packet_size)
            packet[-3:] = b"\x00\x00\x00"
            return bytes(packet)
        return bytes([cmd])

    def _make_size_packet(self, part: int) -> bytes:
        start = part * 240
        chunk = self.image_packets[start : start + min(240, self.packet_size - start)]
        packet = bytearray(4 + len(chunk))
        struct.pack_into("<I", packet, 0, part)
        packet[4:] = bytes(chunk)
        return bytes(packet)


# Convenience function for testing
async def write_image_to_tag(device_address: str, image_path: str, 
                           threshold: int = 128, red_threshold: int = 128,
                           device_config: DeviceConfig = None) -> bool:
    """
    Write an image to an e-ink tag.
    
    Args:
        device_address: BLE device address
        image_path: Path to image file
        threshold: Black/white threshold (0-255)
        red_threshold: Red color threshold (0-255)
        device_config: Device configuration (uses default 2.9" config if None)
    
    Returns:
        True if successful, False otherwise
    """
    if device_config is None:
        device_config = DeviceConfig()  # Default 2.9" config
    
    # Load image
    image = Image.open(image_path)
    
    # Create mock BLE device
    class MockBLEDevice:
        def __init__(self, address):
            self.address = address
            self.name = f"PICKSMART-{address}"
    
    ble_device = MockBLEDevice(device_address)
    
    return await update_image(ble_device, device_config, image, threshold, red_threshold)


if __name__ == "__main__":
    import asyncio
    import argparse
    
    async def main():
        parser = argparse.ArgumentParser(description="Write image to Gicisky e-ink tag")
        parser.add_argument("image", help="Path to image file")
        parser.add_argument("--device", required=True, help="BLE device address")
        parser.add_argument("--threshold", type=int, default=128, help="Black/white threshold (0-255)")
        parser.add_argument("--red-threshold", type=int, default=128, help="Red threshold (0-255)")
        parser.add_argument("--width", type=int, default=296, help="Display width")
        parser.add_argument("--height", type=int, default=128, help="Display height")
        parser.add_argument("--rotation", type=int, default=0, help="Rotation in degrees")
        parser.add_argument("--mirror-x", action="store_true", help="Mirror X axis")
        parser.add_argument("--mirror-y", action="store_true", default=True, help="Mirror Y axis")
        parser.add_argument("--compression", action="store_true", help="Use compression")
        parser.add_argument("--no-red", action="store_true", help="Disable red channel")
        
        args = parser.parse_args()
        
        # Configure logging
        logging.basicConfig(level=logging.INFO)
        
        # Create device config
        device_config = DeviceConfig(
            width=args.width,
            height=args.height,
            red=not args.no_red,
            rotation=args.rotation,
            mirror_x=args.mirror_x,
            mirror_y=args.mirror_y,
            compression=args.compression
        )
        
        success = await write_image_to_tag(
            args.device, 
            args.image,
            args.threshold,
            args.red_threshold,
            device_config
        )
        
        if success:
            print("✅ Image written successfully!")
        else:
            print("❌ Failed to write image")
    
    asyncio.run(main())
