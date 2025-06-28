#!/usr/bin/env python3
"""
Outlook Calendar Status
"""

import asyncio
import sys
import signal
import json
import hashlib
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any
import requests
from icalendar import Calendar
from PIL import Image, ImageDraw, ImageFont
import argparse
import logging



# Configuration
DEFAULT_CHECK_WINDOW_MINUTES = 5
STATUS_FILE = "calendar_status.json"  # File to track previous status

# Supported tag sizes
TAG_SIZES = {
    "1.54": (200, 200),    # 1.54 inch display
    "2.1": (250, 122),     # 2.1 inch display  
    "2.9": (296, 128),     # 2.9 inch display
    "4.2": (400, 300),     # 4.2 inch display
    "7.5": (640, 384),     # 7.5 inch display
}

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_status_hash(status: str, start_time: Optional[datetime], end_time: Optional[datetime], 
                      next_event_time: Optional[datetime]) -> str:
    """Create a hash of the current status for comparison"""
    # Convert datetime objects to ISO strings for consistent hashing
    start_str = start_time.isoformat() if start_time else ""
    end_str = end_time.isoformat() if end_time else ""
    next_str = next_event_time.isoformat() if next_event_time else ""
    
    # Create a string representation of the status
    status_string = f"{status}|{start_str}|{end_str}|{next_str}"
    
    # Return SHA256 hash
    return hashlib.sha256(status_string.encode()).hexdigest()


def load_previous_status(status_file: str = STATUS_FILE) -> Optional[Dict[str, Any]]:
    """Load the previous status from file"""
    try:
        if not os.path.exists(status_file):
            logger.debug(f"Status file {status_file} does not exist")
            return None
            
        with open(status_file, 'r') as f:
            data = json.load(f)
            logger.debug(f"Loaded previous status: {data}")
            return data
            
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Error loading previous status from {status_file}: {e}")
        return None


def save_current_status(status: str, start_time: Optional[datetime], end_time: Optional[datetime], 
                       next_event_time: Optional[datetime], status_hash: str, 
                       status_file: str = STATUS_FILE) -> bool:
    """Save the current status to file"""
    try:
        data = {
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
            "next_event_time": next_event_time.isoformat() if next_event_time else None,
            "status_hash": status_hash
        }
        
        with open(status_file, 'w') as f:
            json.dump(data, f, indent=2)
            
        logger.debug(f"Saved current status to {status_file}")
        return True
        
    except IOError as e:
        logger.error(f"Error saving status to {status_file}: {e}")
        return False


def has_status_changed(current_hash: str, previous_data: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    """Check if the status has changed compared to previous run"""
    if previous_data is None:
        return True, "No previous status found"
    
    previous_hash = previous_data.get("status_hash", "")
    
    if current_hash != previous_hash:
        return True, f"Status changed (hash: {previous_hash[:8]}... -> {current_hash[:8]}...)"
    else:
        return False, f"Status unchanged (hash: {current_hash[:8]}...)"


def get_calendar_events(ics_url: str) -> Optional[Calendar]:
    """
    Fetches and parses calendar events from an ICS URL.
    """
    try:
        logger.info(f"Fetching calendar from: {ics_url}")
        response = requests.get(ics_url, timeout=60)
        response.raise_for_status()
        
        # Check if response looks like HTML instead of iCalendar data
        response_text = response.text.strip()
        if response_text.startswith('<') or 'html' in response_text.lower()[:100]:
            logger.error("❌ Calendar URL returned HTML content instead of iCalendar data")
            logger.error("   This usually means:")
            logger.error("   • The calendar URL requires authentication")
            logger.error("   • The calendar is private and not publicly accessible")
            logger.error("   • The URL format has changed")
            logger.error(f"   Response preview: {response_text[:200]}...")
            return None
        
        cal = Calendar.from_ical(response_text)
        logger.info("Calendar fetched and parsed successfully")
        return cal
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching calendar: {e}")
        return None
    except Exception as e:
        logger.error(f"Error parsing calendar: {e}")
        # If it's a parsing error and we got HTML content, provide helpful message
        if hasattr(e, 'args') and e.args and 'Copyright (C) Microsoft Corporation' in str(e.args[0]):
            logger.error("❌ The calendar URL returned HTML content (likely a Microsoft login page)")
            logger.error("   Please check if the calendar is properly shared and publicly accessible")
        return None


def get_current_status(calendar: Calendar, check_window_minutes: int = 5) -> Tuple[str, Optional[datetime], Optional[datetime], Optional[datetime]]:
    """
    Determines if the user is currently busy or free based on calendar events.
    Returns: (status, start_time, end_time, next_event_start)
    """
    if not calendar:
        return "Error", None, None, None

    now_utc = datetime.now(timezone.utc)
    window_end = now_utc + timedelta(minutes=check_window_minutes)
    future_window = now_utc + timedelta(hours=24)  # Look ahead 24 hours for next event
    
    logger.info(f"Checking status from {now_utc} to {window_end}")

    current_event = None
    upcoming_event = None
    next_future_event = None
    
    for component in calendar.walk():
        if component.name == "VEVENT":
            try:
                dtstart_comp = component.get('dtstart')
                dtend_comp = component.get('dtend')

                if not dtstart_comp or not dtend_comp:
                    continue

                dtstart = dtstart_comp.dt
                dtend = dtend_comp.dt

                # Handle all-day events and ensure all are datetime objects
                from datetime import date as date_class
                
                if isinstance(dtstart, date_class) and not isinstance(dtstart, datetime):
                    dtstart = datetime.combine(dtstart, datetime.min.time()).replace(tzinfo=timezone.utc)
                elif isinstance(dtstart, str):
                    continue
                
                if isinstance(dtend, date_class) and not isinstance(dtend, datetime):
                    dtend = datetime.combine(dtend, datetime.min.time()).replace(tzinfo=timezone.utc)
                elif isinstance(dtend, str):
                    continue

                if not isinstance(dtstart, datetime) or not isinstance(dtend, datetime):
                    logger.debug(f"Skipping event with non-datetime objects")
                    continue

                if dtstart.tzinfo is None:
                    dtstart = dtstart.replace(tzinfo=timezone.utc)
                if dtend.tzinfo is None:
                    dtend = dtend.replace(tzinfo=timezone.utc)

                # Check for transparency
                transp = component.get('TRANSP')
                is_busy_event = True
                if transp and str(transp).upper() == 'TRANSPARENT':
                    is_busy_event = False
                
                # Check for cancelled events
                status = component.get('STATUS')
                if status and str(status).upper() == 'CANCELLED':
                    continue

                # Check for "Out of Office" events
                summary = component.get('SUMMARY', '')
                is_out_of_office = False
                if summary:
                    summary_str = str(summary).lower()
                    if any(phrase in summary_str for phrase in ['out of office', 'ooo', 'vacation', 'off work', 'holiday', 'away']):
                        is_out_of_office = True

                if not is_busy_event and not is_out_of_office:
                    continue

                # Check if currently in meeting or out of office
                if dtstart <= now_utc < dtend:
                    if is_out_of_office:
                        current_event = (dtstart, dtend, 'out_of_office')
                        # Don't break here - we want to prioritize OOO over regular meetings
                        # But if we already found an OOO event, we can break
                        if current_event and current_event[2] == 'out_of_office':
                            break
                    else:
                        # Only set as busy if we haven't already found an OOO event
                        if current_event is None or current_event[2] != 'out_of_office':
                            current_event = (dtstart, dtend, 'busy')
                
                # Check if meeting starts within the window
                elif now_utc <= dtstart < window_end:
                    if is_out_of_office:
                        if upcoming_event is None or dtstart < upcoming_event[0] or upcoming_event[2] != 'out_of_office':
                            upcoming_event = (dtstart, dtend, 'out_of_office')
                    else:
                        # Only set as busy if we haven't found an OOO event or this is earlier
                        if upcoming_event is None or (dtstart < upcoming_event[0] and upcoming_event[2] != 'out_of_office'):
                            upcoming_event = (dtstart, dtend, 'busy')
                
                # Check for next future event (beyond the immediate window)
                elif now_utc < dtstart < future_window:
                    if next_future_event is None or dtstart < next_future_event[0]:
                        if is_out_of_office:
                            next_future_event = (dtstart, dtend, 'out_of_office')
                        else:
                            next_future_event = (dtstart, dtend, 'busy')
                        
            except Exception as e:
                logger.warning(f"Error processing event: {e}")
                continue

    # Determine status
    if current_event:
        start_local = current_event[0].astimezone()
        end_local = current_event[1].astimezone()
        event_type = current_event[2] if len(current_event) > 2 else 'busy'
        next_start = next_future_event[0].astimezone() if next_future_event else None
        
        if event_type == 'out_of_office':
            logger.info(f"Currently out of office: {start_local} to {end_local}")
            return "Out of Office", start_local, end_local, next_start
        else:
            logger.info(f"Currently busy: {start_local} to {end_local}")
            return "Busy", start_local, end_local, next_start
    elif upcoming_event:
        start_local = upcoming_event[0].astimezone()
        end_local = upcoming_event[1].astimezone()
        event_type = upcoming_event[2] if len(upcoming_event) > 2 else 'busy'
        next_start = next_future_event[0].astimezone() if next_future_event else None
        
        if event_type == 'out_of_office':
            logger.info(f"Upcoming out of office: {start_local} to {end_local}")
            return "Out of Office", start_local, end_local, next_start
        else:
            logger.info(f"Upcoming meeting: {start_local} to {end_local}")
            return "Busy", start_local, end_local, next_start
    else:
        next_start = next_future_event[0].astimezone() if next_future_event else None
        logger.info("Currently free")
        return "Free", None, None, next_start


def get_font(size: int) -> ImageFont.ImageFont:
    """Load font with fallback to default if custom fonts not available."""
    font_paths = [
        "/System/Library/Fonts/Arial.ttf",  # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
        "arial.ttf",  # Windows
    ]
    
    for font_path in font_paths:
        try:
            return ImageFont.truetype(font_path, size)
        except (IOError, OSError):
            continue
    
    return ImageFont.load_default()


def create_status_image(status: str, start_time: Optional[datetime], end_time: Optional[datetime], 
                       next_event_time: Optional[datetime] = None, tag_size: str = "2.9") -> Image.Image:
    """Creates a status image for the e-ink display."""
    if tag_size not in TAG_SIZES:
        raise ValueError(f"Unsupported tag size: {tag_size}")
    
    width, height = TAG_SIZES[tag_size]
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)
    
    # Proportional font sizes and dimensions
    # Base these on height, ensuring minimum sizes for very small displays if necessary
    font_large_size = max(12, int(height * 0.375))  # e.g., for 2.9" (h=128): 48
    font_medium_size = max(10, int(height * 0.25)) # e.g., for 2.9" (h=128): 32
    font_small_size = max(8, int(height * 0.1875)) # e.g., for 2.9" (h=128): 24

    font_large = get_font(font_large_size)
    font_medium = get_font(font_medium_size)
    font_small = get_font(font_small_size)

    # Proportional spacing and margins
    general_padding = max(2, int(height * 0.04))       # e.g., ~5 for h=128 (used for line spacing)
    border_thickness = max(1, int(min(width, height) * 0.02)) # e.g., ~2 for 128x296
    top_margin_ooo = max(5, int(height * 0.08))        # e.g., ~10 for h=128
    bottom_margin_ooo = max(8, int(height * 0.12))     # e.g., ~15 for h=128

    if status == "Busy":
        # Top red section with "BUSY"
        top_height = height // 2
        draw.rectangle([0, 0, width, top_height], fill='red')
        
        # Center "BUSY" text in red section
        busy_text = "BUSY"
        busy_bbox = draw.textbbox((0, 0), busy_text, font=font_large)
        busy_width = busy_bbox[2] - busy_bbox[0]
        busy_height = busy_bbox[3] - busy_bbox[1]
        busy_x = (width - busy_width) // 2
        busy_y = (top_height - busy_height) // 2
        draw.text((busy_x, busy_y), busy_text, font=font_large, fill='white')
        
        # Bottom white section with time
        if start_time and end_time:
            time_text = f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
            time_bbox = draw.textbbox((0, 0), time_text, font=font_medium)
            time_width = time_bbox[2] - time_bbox[0]
            time_height = time_bbox[3] - time_bbox[1]
            time_x = (width - time_width) // 2
            time_y = top_height + (height - top_height - time_height) // 2
            draw.text((time_x, time_y), time_text, font=font_medium, fill='red')

    elif status == "Out of Office":
        # White background for entire display
        draw.rectangle([0, 0, width, height], fill='white')
        
        # 2px red border around the entire image
        # border_width = 2 # Replaced by proportional border_thickness
        draw.rectangle([0, 0, width, border_thickness], fill='red')  # top
        draw.rectangle([0, 0, border_thickness, height], fill='red')  # left
        draw.rectangle([width-border_thickness, 0, width, height], fill='red')  # right
        draw.rectangle([0, height-border_thickness, width, height], fill='red')  # bottom
        
        # Red "Out of Office" text higher up
        ooo_text = "Out of Office"
        ooo_bbox = draw.textbbox((0, 0), ooo_text, font=font_large)
        ooo_width = ooo_bbox[2] - ooo_bbox[0]
        ooo_height = ooo_bbox[3] - ooo_bbox[1]
        ooo_x = (width - ooo_width) // 2
        ooo_y = top_margin_ooo  # 10px from top (moved higher) -> use proportional top_margin_ooo
        draw.text((ooo_x, ooo_y), ooo_text, font=font_large, fill='red')
        
        # Black "ending at" and datetime text at bottom on separate lines
        texts_to_draw = []
        
        if end_time:
            ending_label = "ending at"
            ending_datetime = end_time.strftime('%b %d %H:%M')
            texts_to_draw.append((ending_label, font_medium))
            texts_to_draw.append((ending_datetime, font_medium))
        else:
            texts_to_draw.append(("ending time unknown", font_medium))
            
        # Add next event info only if there is an actual next event
        if next_event_time:
            now = datetime.now(timezone.utc).astimezone()
            time_diff = next_event_time - now
            if time_diff.days > 0:
                next_text = f"Next event: {next_event_time.strftime('%b %d %H:%M')}"
            else:
                hours = time_diff.seconds // 3600
                minutes = (time_diff.seconds % 3600) // 60
                if hours > 0:
                    next_text = f"Next event in {hours}h {minutes}m"
                else:
                    next_text = f"Next event in {minutes}m"
            texts_to_draw.append((next_text, font_small))
        
        # Calculate total height needed for all text lines
        line_heights = []
        for text, font in texts_to_draw:
            line_bbox = draw.textbbox((0,0), text, font=font)
            line_heights.append(line_bbox[3] - line_bbox[1])
        
        total_bottom_height = sum(line_heights) + (len(line_heights) - 1) * general_padding  # 5px spacing -> general_padding
        bottom_start_y = height - total_bottom_height - bottom_margin_ooo  # 15px from bottom -> bottom_margin_ooo
        
        # Draw all text lines
        current_y = bottom_start_y
        for i, (text, font) in enumerate(texts_to_draw):
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_x = (width - text_width) // 2
            draw.text((text_x, current_y), text, font=font, fill='black')
            current_y += line_heights[i] + general_padding # 5px spacing -> general_padding

    elif status == "Free":
        # Black rectangle at top with "FREE" in white
        top_height = height // 2
        draw.rectangle([0, 0, width, top_height], fill='black')
        
        # Center "FREE" text in black section
        free_text = "FREE"
        free_bbox = draw.textbbox((0, 0), free_text, font=font_large)
        free_width = free_bbox[2] - free_bbox[0]
        free_height = free_bbox[3] - free_bbox[1]
        free_x = (width - free_width) // 2
        free_y = (top_height - free_height) // 2
        draw.text((free_x, free_y), free_text, font=font_large, fill='white')
        
        # Bottom white section with current time and next event info
        now = datetime.now(timezone.utc).astimezone()
        time_text = f"As of {now.strftime('%H:%M')}"
        
        # Calculate spacing for two lines of text
        if next_event_time:
            # Show next event time
            time_diff = next_event_time - now
            if time_diff.days > 0:
                next_text = f"Next busy: {next_event_time.strftime('%b %d %H:%M')}"
            else:
                next_text = f"Next busy at {next_event_time.strftime('%H:%M')}"
        else:
            next_text = "No upcoming events"
        
        # Position both lines of text
        time_bbox = draw.textbbox((0, 0), time_text, font=font_medium)
        next_bbox = draw.textbbox((0, 0), next_text, font=font_small)
        
        total_height_text = (time_bbox[3] - time_bbox[1]) + (next_bbox[3] - next_bbox[1]) + general_padding  # 5px spacing -> general_padding
        start_y_text = top_height + (height - top_height - total_height_text) // 2
        
        # Draw "As of" line
        time_width = time_bbox[2] - time_bbox[0]
        time_x = (width - time_width) // 2
        draw.text((time_x, start_y_text), time_text, font=font_medium, fill='black')
        
        # Draw "Next event" line
        next_width = next_bbox[2] - next_bbox[0]
        next_x = (width - next_width) // 2
        next_y_pos = start_y_text + (time_bbox[3] - time_bbox[1]) + general_padding # 5px spacing -> general_padding
        draw.text((next_x, next_y_pos), next_text, font=font_small, fill='black')

    else:  # Error
        error_text = "Calendar Error"
        error_bbox = draw.textbbox((0, 0), error_text, font=font_medium)
        error_width = error_bbox[2] - error_bbox[0]
        error_height = error_bbox[3] - error_bbox[1]
        error_x = (width - error_width) // 2
        error_y = (height - error_height) // 2
        draw.text((error_x, error_y), error_text, font=font_medium, fill='red')

    return img




async def main():

    parser = argparse.ArgumentParser(description="Outlook Calendar Status to Image")
    parser.add_argument("--ics-url", default="", help="Outlook ICS calendar URL")
    parser.add_argument("--tag-size", choices=["1.54", "2.1", "2.9", "4.2", "7.5"], default="2.9",
                       help="Tag size in inches (default: 2.9)")
    parser.add_argument("--check-window", type=int, default=DEFAULT_CHECK_WINDOW_MINUTES,
                       help=f"Minutes to check ahead for meetings (default: {DEFAULT_CHECK_WINDOW_MINUTES})")
    parser.add_argument("--save-image", help="Save generated image to this path")
    parser.add_argument("--status-file", default=STATUS_FILE,
                       help=f"File to track status changes (default: {STATUS_FILE})")
    parser.add_argument("--force-update", action="store_true",
                       help="Force image generation even if status hasn't changed")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    

    if not args.ics_url.startswith(('http://', 'https://')):
        logger.error("ICS URL must start with http:// or https://")
        return 1
    
    print("🚀 OUTLOOK CALENDAR STATUS SCRIPT")
    print("=" * 50)
    
    # Fetch calendar
    calendar = get_calendar_events(args.ics_url)
    if not calendar:
        logger.error("Failed to fetch or parse calendar")
        return 1
    
    # Check status
    status, start_time, end_time, next_event_time = get_current_status(calendar, args.check_window)
    logger.info(f"📊 Status: {status}")
    if start_time and end_time:
        logger.info(f"⏰ Event time: {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}")
    
    # Create hash of current status
    current_hash = create_status_hash(status, start_time, end_time, next_event_time)
    
    # Load previous status
    previous_status = load_previous_status(args.status_file)
    
    # Check if status has changed
    status_changed, change_reason = has_status_changed(current_hash, previous_status)
    
    # Check if image file exists (but don't update based on age alone to preserve battery)
    image_path = args.save_image if args.save_image else "status_output.png"
    image_missing = not os.path.exists(image_path)
    
    logger.info(f"🔍 Change detection: {change_reason}")
    
    # Determine if we should generate image (battery-conscious approach)
    # Only update when: status changed, force requested, or image file missing
    should_generate = status_changed or args.force_update or image_missing
    
    if image_missing:
        logger.info("📄 Image file missing, will generate new image")
    
    if not should_generate:
        logger.info("⏭️  Status unchanged, skipping image generation")
        logger.info("💡 Use --force-update to generate image anyway")
        return 0
    
    logger.info("🎨 Status changed or force update requested, generating image...")
    
    # Generate image
    logger.info(f"🖼️  Generating {args.tag_size}\" tag image...")
    image = create_status_image(status, start_time, end_time, next_event_time, args.tag_size)
    
    # Save image (use default filename if none provided)
    save_path = args.save_image if args.save_image else "status_output.png"
    image.save(save_path)
    logger.info(f"💾 Image saved to {save_path}")
    
    # Save current status
    if save_current_status(status, start_time, end_time, next_event_time, current_hash, args.status_file):
        logger.info(f"📄 Status saved to {args.status_file}")
    else:
        logger.warning(f"⚠️ Failed to save status to {args.status_file}")
 
    logger.info("✅ COMPLETE! No hammers needed today! 🔨→😊")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32" and sys.version_info >= (3, 8, 0):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("⚠️ Interrupted by user (Ctrl+C)")
        sys.exit(1)
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        sys.exit(1)
