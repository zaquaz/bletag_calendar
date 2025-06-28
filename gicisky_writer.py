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
import asyncio
import re
from typing import Any, Callable, TypeVar, Optional, List
from asyncio import Event, wait_for, sleep
from PIL import Image
from bleak import BleakClient, BleakError, BleakScanner
from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)

# Device configuration class
class DeviceConfig:
    def __init__(self, width=296, height=128, red=True, tft=False, rotation=0, 
                 mirror_x=False, mirror_y=False, compression=False):
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


# BLE Device Discovery and Scanning Functions

async def scan_for_devices(timeout: int = 10, name_filter: str = None) -> List[BLEDevice]:
    """
    Scan for BLE devices with optional name filtering.
    
    Args:
        timeout: Scan timeout in seconds
        name_filter: Optional filter for device names (case-insensitive)
    
    Returns:
        List of discovered BLE devices
    """
    print(f"🔍 Scanning for BLE devices (timeout: {timeout}s)...")
    
    devices = await BleakScanner.discover(timeout=timeout, return_adv=False)
    
    if name_filter:
        filtered_devices = []
        filter_lower = name_filter.lower()
        for device in devices:
            if device.name and filter_lower in device.name.lower():
                filtered_devices.append(device)
        devices = filtered_devices
        print(f"📱 Found {len(devices)} devices matching '{name_filter}'")
    else:
        print(f"📱 Found {len(devices)} devices total")
    
    return devices


async def find_device_by_address(address: str, timeout: int = 10) -> Optional[BLEDevice]:
    """
    Find a specific device by its BLE address.
    
    Args:
        address: BLE device address (MAC address format)
        timeout: Scan timeout in seconds
    
    Returns:
        BLEDevice if found, None otherwise
    """
    print(f"🎯 Looking for device with address: {address}")
    
    # Normalize address format (handle different separators)
    normalized_address = address.upper().replace('-', ':').replace('_', ':')
    
    devices = await scan_for_devices(timeout=timeout)
    
    for device in devices:
        device_addr = device.address.upper().replace('-', ':').replace('_', ':')
        if device_addr == normalized_address:
            print(f"✅ Found device: {device.name or 'Unknown'} ({device.address})")
            return device
    
    print(f"❌ Device {address} not found")
    return None


async def find_gicisky_devices(timeout: int = 10) -> List[BLEDevice]:
    """
    Find devices that are likely Gicisky e-ink tags.
    
    Args:
        timeout: Scan timeout in seconds
    
    Returns:
        List of potential Gicisky devices
    """
    print("🏷️  Scanning for Gicisky e-ink devices...")
    
    # Common Gicisky device name patterns
    gicisky_patterns = [
        "PICKSMART",
        "GICISKY", 
        "EINK",
        "E-INK",
        "TAG"
    ]
    
    all_devices = await scan_for_devices(timeout=timeout)
    gicisky_devices = []
    
    for device in all_devices:
        if device.name:
            device_name_upper = device.name.upper()
            for pattern in gicisky_patterns:
                if pattern in device_name_upper:
                    gicisky_devices.append(device)
                    break
    
    print(f"🏷️  Found {len(gicisky_devices)} potential Gicisky devices:")
    for i, device in enumerate(gicisky_devices, 1):
        print(f"   {i}. {device.name or 'Unknown'} ({device.address})")
    
    return gicisky_devices


async def interactive_device_selection(timeout: int = 10) -> Optional[BLEDevice]:
    """
    Interactively scan for and select a BLE device.
    
    Args:
        timeout: Scan timeout in seconds
    
    Returns:
        Selected BLEDevice or None if cancelled
    """
    print("\n🔍 INTERACTIVE DEVICE SELECTION")
    print("=" * 40)
    
    # First try to find Gicisky-like devices
    gicisky_devices = await find_gicisky_devices(timeout)
    
    if gicisky_devices:
        print(f"\n🏷️  Found {len(gicisky_devices)} Gicisky-like devices:")
        for i, device in enumerate(gicisky_devices, 1):
            rssi_info = f" (RSSI: {device.rssi})" if hasattr(device, 'rssi') and device.rssi else ""
            print(f"   {i}. {device.name or 'Unknown'} ({device.address}){rssi_info}")
        
        try:
            choice = input(f"\nSelect device (1-{len(gicisky_devices)}) or 'a' for all devices, 'r' to rescan: ").strip().lower()
            
            if choice == 'r':
                return await interactive_device_selection(timeout)
            elif choice == 'a':
                pass  # Fall through to show all devices
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(gicisky_devices):
                    return gicisky_devices[idx]
                else:
                    print("❌ Invalid selection")
                    return None
        except (ValueError, KeyboardInterrupt):
            print("\n❌ Selection cancelled")
            return None
    
    # Show all devices if no Gicisky devices found or user requested all
    if not gicisky_devices:
        print("🔍 No Gicisky-like devices found. Showing all devices...")
    
    all_devices = await scan_for_devices(timeout)
    
    if not all_devices:
        print("❌ No BLE devices found")
        return None
    
    print(f"\n📱 All {len(all_devices)} discovered devices:")
    for i, device in enumerate(all_devices, 1):
        rssi_info = f" (RSSI: {device.rssi})" if hasattr(device, 'rssi') and device.rssi else ""
        print(f"   {i}. {device.name or 'Unknown'} ({device.address}){rssi_info}")
    
    try:
        choice = input(f"\nSelect device (1-{len(all_devices)}) or 'r' to rescan: ").strip().lower()
        
        if choice == 'r':
            return await interactive_device_selection(timeout)
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(all_devices):
                return all_devices[idx]
            else:
                print("❌ Invalid selection")
                return None
    except (ValueError, KeyboardInterrupt):
        print("\n❌ Selection cancelled")
        return None
    
    return None


async def smart_device_discovery(device_address: str, scan_timeout: int = 10, 
                                connection_timeout: int = 30) -> Optional[BLEDevice]:
    """
    Smart device discovery that tries multiple methods to find the device.
    
    Args:
        device_address: Target device address or pattern
        scan_timeout: BLE scan timeout in seconds  
        connection_timeout: Total timeout for discovery process
    
    Returns:
        BLEDevice if found, None otherwise
    """
    start_time = asyncio.get_event_loop().time()
    
    print(f"🎯 Smart discovery for device: {device_address}")
    print(f"   Scan timeout: {scan_timeout}s, Total timeout: {connection_timeout}s")
    
    # Method 1: Direct address lookup
    if re.match(r'^[0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}$', device_address):
        print("🔍 Method 1: Direct address lookup...")
        device = await find_device_by_address(device_address, scan_timeout)
        if device:
            return device
    
    # Check if we have time for more methods
    elapsed = asyncio.get_event_loop().time() - start_time
    if elapsed >= connection_timeout:
        print("⏰ Timeout reached during direct lookup")
        return None
    
    # Method 2: Name pattern matching
    print("🔍 Method 2: Name pattern matching...")
    remaining_time = max(5, connection_timeout - elapsed)
    devices = await scan_for_devices(timeout=min(scan_timeout, remaining_time), name_filter=device_address)
    
    if devices:
        if len(devices) == 1:
            print(f"✅ Found unique match: {devices[0].name} ({devices[0].address})")
            return devices[0]
        else:
            print(f"⚠️  Found {len(devices)} devices matching '{device_address}':")
            for device in devices:
                print(f"   - {device.name} ({device.address})")
            return devices[0]  # Return first match
    
    # Method 3: Find any Gicisky devices if no specific match
    elapsed = asyncio.get_event_loop().time() - start_time
    if elapsed < connection_timeout:
        print("🔍 Method 3: Looking for any Gicisky devices...")
        remaining_time = max(5, connection_timeout - elapsed)
        gicisky_devices = await find_gicisky_devices(timeout=min(scan_timeout, remaining_time))
        
        if gicisky_devices:
            print(f"⚠️  Target device not found, but found {len(gicisky_devices)} Gicisky device(s)")
            return gicisky_devices[0]  # Return first Gicisky device
    
    print(f"❌ Device discovery failed for: {device_address}")
    return None


# Convenience function for testing
async def write_image_to_tag(device_address: str, image_path: str, 
                           threshold: int = 128, red_threshold: int = 128,
                           device_config: DeviceConfig = None,
                           scan_timeout: int = 10, connection_timeout: int = 30) -> bool:
    """
    Write an image to an e-ink tag with smart device discovery.
    
    Args:
        device_address: BLE device address or name pattern
        image_path: Path to image file
        threshold: Black/white threshold (0-255)
        red_threshold: Red color threshold (0-255)
        device_config: Device configuration (uses default 2.9" config if None)
        scan_timeout: BLE scan timeout in seconds
        connection_timeout: Total connection timeout in seconds
    
    Returns:
        True if successful, False otherwise
    """
    if device_config is None:
        device_config = DeviceConfig()  # Default 2.9" config
    
    # Load image
    try:
        image = Image.open(image_path)
        print(f"📷 Loaded image: {image.size} ({image_path})")
    except Exception as e:
        print(f"❌ Failed to load image {image_path}: {e}")
        return False
    
    # Discover device
    print(f"\n🔍 DEVICE DISCOVERY")
    print("=" * 30)
    
    ble_device = await smart_device_discovery(device_address, scan_timeout, connection_timeout)
    
    if not ble_device:
        print(f"\n❌ Could not find device: {device_address}")
        print("💡 Troubleshooting tips:")
        print("   • Make sure the device is powered on and in pairing mode")
        print("   • Check if the device address is correct")
        print("   • Try increasing scan timeout with --scan-timeout")
        print("   • Use --scan-devices to see all available devices")
        return False
    
    print(f"\n📡 CONNECTING TO DEVICE")
    print("=" * 30)
    print(f"Device: {ble_device.name or 'Unknown'}")
    print(f"Address: {ble_device.address}")
    
    return await update_image(ble_device, device_config, image, threshold, red_threshold)


async def test_device_connection(device_address: str, scan_timeout: int = 10, 
                               connection_timeout: int = 30) -> bool:
    """
    Test connection to a specific BLE device without writing any data.
    
    Args:
        device_address: Target device address or pattern
        scan_timeout: BLE scan timeout in seconds
        connection_timeout: Total timeout for connection test
    
    Returns:
        True if connection successful, False otherwise
    """
    print(f"🧪 TESTING CONNECTION TO DEVICE: {device_address}")
    print("=" * 50)
    
    # Discover device
    ble_device = await smart_device_discovery(device_address, scan_timeout, connection_timeout)
    
    if not ble_device:
        print(f"❌ Could not find device: {device_address}")
        return False
    
    print(f"✅ Device found: {ble_device.name or 'Unknown'} ({ble_device.address})")
    
    # Try to connect
    print("🔗 Attempting connection...")
    client = BleakClient(ble_device)
    
    try:
        await client.connect()
        print("✅ Connection successful!")
        
        # Check services
        print("🔍 Checking services...")
        services = client.services
        service_list = list(services)
        print(f"📋 Found {len(service_list)} services:")
        
        for service in service_list:
            print(f"   • {service.uuid}: {service.description}")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"     - {char.uuid} ({props})")
        
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False
        
    finally:
        if client.is_connected:
            await client.disconnect()
            print("🔌 Disconnected")


if __name__ == "__main__":
    import asyncio
    import argparse
    
    async def main():
        parser = argparse.ArgumentParser(description="Write image to Gicisky e-ink tag")
        parser.add_argument("image", nargs='?', help="Path to image file")
        parser.add_argument("--device", help="BLE device address")
        parser.add_argument("--threshold", type=int, default=128, help="Black/white threshold (0-255)")
        parser.add_argument("--red-threshold", type=int, default=128, help="Red threshold (0-255)")
        parser.add_argument("--width", type=int, default=296, help="Display width")
        parser.add_argument("--height", type=int, default=128, help="Display height")
        parser.add_argument("--rotation", type=int, default=0, help="Rotation in degrees")
        parser.add_argument("--mirror-x", action="store_true", help="Mirror X axis")
        parser.add_argument("--mirror-y", action="store_true", help="Mirror Y axis")
        parser.add_argument("--compression", action="store_true", help="Use compression")
        parser.add_argument("--no-red", action="store_true", help="Disable red channel")
        parser.add_argument("--scan-timeout", type=int, default=10, help="BLE scan timeout in seconds")
        parser.add_argument("--connection-timeout", type=int, default=30, help="BLE connection timeout in seconds")
        parser.add_argument("--scan-devices", action="store_true", help="Scan for all BLE devices and exit")
        parser.add_argument("--find-gicisky", action="store_true", help="Find Gicisky-like devices and exit")
        parser.add_argument("--interactive", action="store_true", help="Interactive device selection")
        parser.add_argument("--test-connection", help="Test connection to specific device address/name")
        
        args = parser.parse_args()
        
        # Configure logging
        logging.basicConfig(level=logging.INFO)
        
        # Handle scanning-only commands
        if args.scan_devices:
            print("🔍 Scanning for all BLE devices...")
            devices = await scan_for_devices(timeout=args.scan_timeout)
            if devices:
                print(f"\n📱 Found {len(devices)} devices:")
                for i, device in enumerate(devices, 1):
                    rssi_info = f" (RSSI: {device.rssi})" if hasattr(device, 'rssi') and device.rssi else ""
                    print(f"   {i}. {device.name or 'Unknown'} ({device.address}){rssi_info}")
            else:
                print("❌ No devices found")
            return
        
        if args.find_gicisky:
            devices = await find_gicisky_devices(timeout=args.scan_timeout)
            return
        
        if args.interactive:
            device = await interactive_device_selection(timeout=args.scan_timeout)
            if device:
                print(f"\n✅ Selected device: {device.name or 'Unknown'} ({device.address})")
            return
        
        if args.test_connection:
            success = await test_device_connection(args.test_connection, args.scan_timeout, args.connection_timeout)
            if success:
                print("\n✅ Device connection test PASSED")
            else:
                print("\n❌ Device connection test FAILED")
            return
        
        # Validate required arguments for image writing
        if not args.image or not args.device:
            parser.error("image and --device are required when not using scan-only commands")
        
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
            device_config,
            args.scan_timeout,
            args.connection_timeout
        )
        
        if success:
            print("✅ Image written successfully!")
        else:
            print("❌ Failed to write image")
    
    asyncio.run(main())
