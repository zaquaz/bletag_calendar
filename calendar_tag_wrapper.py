#!/usr/bin/env python3
"""
Calendar Tag Wrapper Script

This script automates the process of:
1. Running outlook_cal_status.py to generate status_output.png
2. Checking if the image was modified within the last 5 minutes
3. If so, sending it to the e-ink tag using gicisky_writer.py with rotation and mirroring
"""

import subprocess
import sys
import os
import argparse
import logging
import json
import configparser
from datetime import datetime, timedelta
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_DEVICE_ADDRESS = "PICKSMART"
DEFAULT_ROTATION = 90
DEFAULT_MIRROR_X = True
DEFAULT_MIRROR_Y = False
STATUS_IMAGE_PATH = "status_output.png"
FRESHNESS_THRESHOLD_MINUTES = 5
DEFAULT_CONFIG_FILE = "calendar_tag_config.ini"


def load_config_file(config_path):
    """Load configuration from file"""
    config = configparser.ConfigParser()
    config_data = {}
    
    if not os.path.exists(config_path):
        logger.info(f"📄 Config file not found: {config_path}")
        return config_data
    
    try:
        config.read(config_path)
        logger.info(f"📋 Loading configuration from: {config_path}")
        
        # Calendar settings
        if config.has_section('calendar'):
            calendar_section = config['calendar']
            if calendar_section.get('ics_url'):
                config_data['ics_url'] = calendar_section.get('ics_url')
                logger.info(f"   ICS URL: {config_data['ics_url'][:50]}...")
            if calendar_section.get('tag_size'):
                config_data['tag_size'] = calendar_section.get('tag_size')
                logger.info(f"   Tag size: {config_data['tag_size']}\"")
            if calendar_section.get('check_window'):
                config_data['check_window'] = calendar_section.getint('check_window')
                logger.info(f"   Check window: {config_data['check_window']} minutes")
        
        # Device settings
        if config.has_section('device'):
            device_section = config['device']
            if device_section.get('address'):
                config_data['device'] = device_section.get('address')
                logger.info(f"   Device address: {config_data['device']}")
            if device_section.get('rotation'):
                config_data['rotation'] = device_section.getint('rotation')
                logger.info(f"   Rotation: {config_data['rotation']}°")
            if device_section.get('mirror_x'):
                config_data['mirror_x'] = device_section.getboolean('mirror_x')
                logger.info(f"   Mirror X: {config_data['mirror_x']}")
            if device_section.get('mirror_y'):
                config_data['mirror_y'] = device_section.getboolean('mirror_y')
                logger.info(f"   Mirror Y: {config_data['mirror_y']}")
        
        # Options settings
        if config.has_section('options'):
            options_section = config['options']
            if options_section.get('freshness_threshold'):
                config_data['freshness_threshold'] = options_section.getint('freshness_threshold')
                logger.info(f"   Freshness threshold: {config_data['freshness_threshold']} minutes")
            if options_section.get('status_file'):
                config_data['status_file'] = options_section.get('status_file')
                logger.info(f"   Status file: {config_data['status_file']}")
        
        logger.info(f"✅ Successfully loaded {len(config_data)} configuration values")
        
    except Exception as e:
        logger.error(f"❌ Error loading config file {config_path}: {e}")
    
    return config_data


def create_example_config(config_path):
    """Create an example configuration file"""
    config_content = """# Calendar Tag Configuration File
# This file contains default settings for the calendar tag wrapper script

[calendar]
# Your Outlook calendar ICS URL (get this from Outlook -> Calendar Settings -> Shared Calendars)
ics_url = https://outlook.live.com/owa/calendar/your-calendar-id/reachableFreeBusy.ics

# Tag size in inches (2.1 or 2.9)
tag_size = 2.9

# Minutes to check ahead for upcoming meetings
check_window = 5

[device]
# Bluetooth device address of your e-ink tag
# You can find this by scanning for BLE devices or checking your device pairing info
address = PICKSMART

# Image rotation in degrees (0, 90, 180, 270)
rotation = 90

# Mirror image horizontally (true/false)
mirror_x = true

# Mirror image vertically (true/false)
mirror_y = false

[options]
# Maximum age in minutes for image to be considered fresh
freshness_threshold = 5

# File to track calendar status changes
status_file = calendar_status.json
"""
    
    try:
        with open(config_path, 'w') as f:
            f.write(config_content)
        logger.info(f"📝 Created example config file: {config_path}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to create config file: {e}")
        return False


def run_command(cmd_args, description):
    """Run a command and return success status"""
    try:
        logger.info(f"🚀 {description}")
        logger.info(f"   Command: {' '.join(cmd_args)}")
        
        result = subprocess.run(
            cmd_args,
            check=True,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        logger.info(f"✅ {description} completed successfully")
        if result.stdout.strip():
            logger.info(f"   Output: {result.stdout.strip()}")
        
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ {description} failed with return code {e.returncode}")
        if e.stdout:
            logger.error(f"   STDOUT: {e.stdout}")
        if e.stderr:
            logger.error(f"   STDERR: {e.stderr}")
        return False
        
    except subprocess.TimeoutExpired:
        logger.error(f"⏰ {description} timed out after 5 minutes")
        return False
        
    except Exception as e:
        logger.error(f"💥 {description} failed: {e}")
        return False


def check_file_freshness(file_path, threshold_minutes=FRESHNESS_THRESHOLD_MINUTES):
    """Check if file was modified within the threshold time"""
    try:
        if not os.path.exists(file_path):
            logger.warning(f"📄 File not found: {file_path}")
            return False
            
        file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
        current_time = datetime.now()
        time_diff = current_time - file_mtime
        
        logger.info(f"📅 File modification time: {file_mtime.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"🕐 Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"⏱️  Time difference: {time_diff.total_seconds()/60:.1f} minutes")
        
        is_fresh = time_diff <= timedelta(minutes=threshold_minutes)
        
        if is_fresh:
            logger.info(f"✅ File is fresh (modified within {threshold_minutes} minutes)")
        else:
            logger.info(f"⚠️ File is stale (modified more than {threshold_minutes} minutes ago)")
            
        return is_fresh
        
    except Exception as e:
        logger.error(f"💥 Error checking file freshness: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Automated Calendar Status to E-ink Tag Workflow",
        epilog="""
This script automates the complete workflow:
1. Generates calendar status image using outlook_cal_status.py
2. Checks if the image was created/updated recently
3. If fresh, sends the image to the e-ink tag with proper rotation and mirroring

Configuration File:
  The script can read settings from a configuration file (default: calendar_tag_config.ini).
  Use --create-config to generate an example configuration file.
  Command line arguments override configuration file settings.

Examples:
  %(prog)s                                    # Use all defaults with status change detection
  %(prog)s --config my_config.ini            # Use custom configuration file
  %(prog)s --create-config                   # Create example configuration file
  %(prog)s --device AA:BB:CC:DD:EE:FF         # Override device from config
  %(prog)s --rotation 180 --no-mirror-x      # Different rotation, no mirroring
  %(prog)s --ics-url "https://..."           # Use different calendar URL
  %(prog)s --force-calendar-update           # Force calendar update even if status unchanged
  %(prog)s --dry-run                         # Test without sending to device
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Configuration file options
    parser.add_argument("--config", default=DEFAULT_CONFIG_FILE,
                       help=f"Configuration file path (default: {DEFAULT_CONFIG_FILE})")
    parser.add_argument("--create-config", action="store_true",
                       help="Create an example configuration file and exit")
    
    # Parse args once to check for --create-config and --config
    args, remaining = parser.parse_known_args()
    
    # Handle config file creation
    if args.create_config:
        config_path = args.config
        if create_example_config(config_path):
            logger.info(f"✅ Example configuration file created: {config_path}")
            logger.info("📝 Please edit the file with your calendar URL and device address")
            return 0
        else:
            logger.error("❌ Failed to create configuration file")
            return 1
    
    # Load configuration file
    config_data = load_config_file(args.config)
    
    # Calendar generation options (with config file defaults)
    parser.add_argument("--ics-url", 
                       default=config_data.get('ics_url'),
                       help="Outlook ICS calendar URL (passed to outlook_cal_status.py)")
    parser.add_argument("--tag-size", choices=["2.1", "2.9"], 
                       default=config_data.get('tag_size', "2.9"),
                       help="Tag size in inches (default: 2.9)")
    parser.add_argument("--check-window", type=int, 
                       default=config_data.get('check_window', 5),
                       help="Minutes to check ahead for meetings (default: 5)")
    parser.add_argument("--status-file", 
                       default=config_data.get('status_file', "calendar_status.json"),
                       help="File to track status changes (default: calendar_status.json)")
    parser.add_argument("--force-calendar-update", action="store_true",
                       help="Force calendar image generation even if status hasn't changed")
    
    # Device transfer options (with config file defaults)
    parser.add_argument("--device", 
                       default=config_data.get('device', DEFAULT_DEVICE_ADDRESS),
                       help=f"BLE device address (default from config or {DEFAULT_DEVICE_ADDRESS})")
    parser.add_argument("--rotation", type=int, 
                       default=config_data.get('rotation', DEFAULT_ROTATION),
                       help=f"Image rotation in degrees (default from config or {DEFAULT_ROTATION})")
    parser.add_argument("--mirror-x", action="store_true", 
                       default=config_data.get('mirror_x', DEFAULT_MIRROR_X),
                       help="Mirror image horizontally (default from config)")
    parser.add_argument("--no-mirror-x", action="store_true",
                       help="Disable horizontal mirroring")
    parser.add_argument("--mirror-y", action="store_true", 
                       default=config_data.get('mirror_y', DEFAULT_MIRROR_Y),
                       help="Mirror image vertically (default from config)")
    
    # Control options (with config file defaults)
    parser.add_argument("--freshness-threshold", type=int, 
                       default=config_data.get('freshness_threshold', FRESHNESS_THRESHOLD_MINUTES),
                       help=f"Maximum age in minutes for image to be considered fresh (default from config or {FRESHNESS_THRESHOLD_MINUTES})")
    parser.add_argument("--force-send", action="store_true",
                       help="Send to device even if image is not fresh")
    parser.add_argument("--dry-run", action="store_true",
                       help="Generate image but don't send to device")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")
    
    # Parse arguments again with all options
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Handle mirror-x logic
    mirror_x = args.mirror_x and not args.no_mirror_x
    
    logger.info("🏷️  CALENDAR TAG WRAPPER STARTING")
    logger.info("=" * 60)
    
    # Show config file info if it was loaded
    if config_data:
        logger.info(f"📋 Using configuration from: {args.config}")
    else:
        logger.info(f"📋 No configuration file loaded (checked: {args.config})")
    
    logger.info(f"📋 Final configuration:")
    logger.info(f"   Tag size: {args.tag_size}\"")
    logger.info(f"   Device: {args.device}")
    logger.info(f"   Rotation: {args.rotation}°")
    logger.info(f"   Mirror X: {mirror_x}")
    logger.info(f"   Mirror Y: {args.mirror_y}")
    logger.info(f"   Freshness threshold: {args.freshness_threshold} minutes")
    logger.info(f"   Status file: {args.status_file}")
    logger.info(f"   Force calendar update: {args.force_calendar_update}")
    logger.info(f"   Dry run: {args.dry_run}")
    if args.ics_url:
        logger.info(f"   ICS URL: {args.ics_url[:50]}...")
    else:
        logger.info(f"   ICS URL: (not specified - will use outlook_cal_status.py default)")
    
    # Step 1: Generate calendar status image
    logger.info("\n📅 STEP 1: GENERATING CALENDAR STATUS IMAGE")
    logger.info("-" * 50)
    
    outlook_cmd = [
        "python", "outlook_cal_status.py",
        "--tag-size", args.tag_size,
        "--check-window", str(args.check_window),
        "--save-image", STATUS_IMAGE_PATH,
        "--status-file", args.status_file
    ]
    
    if args.ics_url:
        outlook_cmd.extend(["--ics-url", args.ics_url])
    
    if args.force_calendar_update:
        outlook_cmd.append("--force-update")
    
    if args.verbose:
        outlook_cmd.append("--verbose")
    
    success = run_command(outlook_cmd, "Generating calendar status image")
    
    if not success:
        logger.error("💥 Failed to generate calendar status image")
        return 1
    
    # Check if image was actually generated (it might be skipped if status unchanged)
    if not os.path.exists(STATUS_IMAGE_PATH):
        logger.info("📄 No image generated (status unchanged)")
        logger.info("💡 Calendar status hasn't changed, no update needed")
        return 0
    
    # Step 2: Check if image is fresh
    logger.info("\n⏰ STEP 2: CHECKING IMAGE FRESHNESS")
    logger.info("-" * 50)
    
    is_fresh = check_file_freshness(STATUS_IMAGE_PATH, args.freshness_threshold)
    
    if not is_fresh and not args.force_send:
        logger.warning("⚠️ Image is not fresh and --force-send not specified")
        logger.info("💡 Use --force-send to send anyway, or check if calendar generation failed")
        return 0
    
    if args.dry_run:
        logger.info("🏃 DRY RUN: Would send image to device, but skipping due to --dry-run")
        logger.info(f"   Would run: python gicisky_writer.py --device {args.device} --rotation {args.rotation} {STATUS_IMAGE_PATH}")
        if mirror_x:
            logger.info("   Would include: --mirror-x")
        if args.mirror_y:
            logger.info("   Would include: --mirror-y")
        return 0
    
    # Step 3: Send to e-ink device
    logger.info("\n📡 STEP 3: SENDING TO E-INK DEVICE")
    logger.info("-" * 50)
    
    gicisky_cmd = [
        "python", "gicisky_writer.py",
        "--device", args.device,
        "--rotation", str(args.rotation),
        STATUS_IMAGE_PATH
    ]
    
    if mirror_x:
        gicisky_cmd.insert(-1, "--mirror-x")
    
    if args.mirror_y:
        gicisky_cmd.insert(-1, "--mirror-y")
    
    success = run_command(gicisky_cmd, "Sending image to e-ink device")
    
    if success:
        logger.info("\n🎉 WORKFLOW COMPLETED SUCCESSFULLY!")
        logger.info("=" * 60)
        logger.info("✅ Calendar status has been updated on your e-ink tag")
        return 0
    else:
        logger.error("\n💥 WORKFLOW FAILED!")
        logger.error("=" * 60)
        logger.error("❌ Failed to send image to e-ink device")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Workflow interrupted by user (Ctrl+C)")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n💥 Unexpected error: {e}")
        sys.exit(1)
