# BLE E-ink Calendar Status Display

An intelligent system for displaying Outlook calendar status on Bluetooth Low Energy (BLE) e-ink tags with smart change detection and minimal power consumption.

## 🎯 Why E-ink Tags for Calendar Status?

E-ink displays are perfect for calendar status indicators because they:

- **Ultra-low power consumption**: Display persists for weeks without power
- **Always visible**: No need to wake up devices or check screens
- **Professional appearance**: Clean, paper-like display perfect for office environments
- **Instant status awareness**: See your availability at a glance from across the room
- **Privacy-friendly**: Shows only availability status, not meeting details
- **Wireless updates**: Automatically sync with your calendar via Bluetooth

Perfect for:
- **Office doors**: Let colleagues know when you're available
- **Remote work**: Show household members your meeting status
- **Hot-desking**: Mark desk availability in shared workspaces
- **Conference rooms**: Display room availability status

## 🚀 Features

### Intelligent Change Detection
- **SHA256-based status tracking**: Only updates display when calendar status actually changes
- **Minimal resource usage**: Prevents unnecessary BLE transfers and image processing
- **Status persistence**: Tracks availability state between runs

### Advanced Image Processing
- **Rotation support**: 0°, 90°, 180°, 270° rotation options
- **Mirroring capabilities**: Horizontal and vertical image mirroring
- **Smart compression**: Gicisky-compatible image compression for faster transfers
- **Multiple tag sizes**: Support for 2.1" and 2.9" e-ink displays

### Robust BLE Communication
- **Enhanced reliability**: 30-second timeouts with exponential backoff retry
- **Event-driven protocol**: Asynchronous notification handling for responsive transfers
- **Connection management**: Automatic cleanup and error handling

### Configuration Management
- **INI-based configuration**: Easy-to-edit configuration files
- **Command-line overrides**: Flexible parameter customization
- **Dry-run mode**: Test configurations without sending to device

### Automated Workflow
- **End-to-end automation**: Single command runs entire workflow
- **Image freshness checking**: Avoids regenerating recent images
- **Comprehensive logging**: Detailed operation tracking for troubleshooting

## 📁 Project Structure

```
BLETag/
├── calendar_tag_wrapper.py      # Main automation script
├── outlook_cal_status.py        # Calendar status detection & image generation
├── gicisky_writer.py           # Enhanced BLE communication
├── image_transfer.py           # Advanced image processing (DEPRECATED - functionality moved to gicisky_writer.py)
├── calendar_tag_config.ini     # Configuration template
├── requirements.txt            # Python dependencies
├── calendar_status.json        # Status tracking file (auto-generated)
├── status_output.png          # Generated status image (auto-generated)
└── README.md                   # This file
```

## 🛠️ Installation

### Prerequisites
- Python 3.8 or higher
- Gicisky or compatible BLE e-ink tag
- Outlook calendar with public ICS URL access

### Setup

1. **Clone and navigate to the project:**
   ```bash
   git clone <your-repo-url>
   cd BLETag
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure your settings:**
   ```bash
   cp calendar_tag_config.ini my_config.ini
   # Edit my_config.ini with your calendar URL and device address
   ```

## ⚙️ Configuration

### Calendar Setup

1. **Get your Outlook ICS URL:**
   - Open Outlook Web App
   - Go to Calendar → Settings → Shared Calendars
   - Copy the ICS URL for your calendar

2. **Update configuration:**
   ```ini
   [calendar]
   ics_url = https://outlook.office365.com/owa/calendar/YOUR_CALENDAR_ID/calendar.ics
   tag_size = 2.9
   check_window = 5
   
   [device]
   address = YOUR_TAG_BLE_ADDRESS
   rotation = 90
   mirror_x = true
   mirror_y = false
   
   [options]
   freshness_threshold = 5
   status_file = calendar_status.json
   ```
  (Note: your tag may require different rotation or mirror settings)
## 🚀 Usage

### Quick Start

Run the complete automated workflow:
```bash
python calendar_tag_wrapper.py --config my_config.ini
```

### Advanced Options

**Test without sending to device:**
```bash
python calendar_tag_wrapper.py --config my_config.ini --dry-run
```

**Force update regardless of status changes:**
```bash
python calendar_tag_wrapper.py --config my_config.ini --force-update
```

**Use command-line overrides:**
```bash
python calendar_tag_wrapper.py \
  --config my_config.ini \
  --device AA:BB:CC:DD:EE:FF \
  --rotation 180 \
  --mirror-x
```

### Individual Components

**Generate calendar status image only:**
```bash
python outlook_cal_status.py \
  --ics-url "YOUR_ICS_URL" \
  --output status_output.png \
  --status-file calendar_status.json
```

**Send image to e-ink tag only:**
```bash
python gicisky_writer.py \
  --device AA:BB:CC:DD:EE:FF \
  --image status_output.png \
  --rotation 90 \
  --mirror-x
```

## 📋 Command Reference

### calendar_tag_wrapper.py
Main automation script that orchestrates the entire workflow.

```bash
python calendar_tag_wrapper.py [OPTIONS]
```

**Key Options:**
- `--config FILE`: Configuration file path
- `--dry-run`: Test mode - don't send to device
- `--force-update`: Force update even if status unchanged
- `--device ADDRESS`: Override BLE device address
- `--rotation DEGREES`: Image rotation (0, 90, 180, 270)
- `--mirror-x`: Mirror image horizontally
- `--mirror-y`: Mirror image vertically

### outlook_cal_status.py
Calendar status detection and image generation.

```bash
python outlook_cal_status.py [OPTIONS]
```

**Key Options:**
- `--ics-url URL`: Outlook calendar ICS URL
- `--output FILE`: Output image path
- `--status-file FILE`: Status tracking JSON file
- `--force-update`: Ignore status cache and force regeneration
- `--check-window MINUTES`: Minutes to look ahead for meetings

### gicisky_writer.py
BLE communication and image transfer to e-ink tags.

```bash
python gicisky_writer.py IMAGE --device ADDRESS [OPTIONS]
```

**Key Options:**
- `IMAGE`: Path to image file
- `--device ADDRESS`: BLE device address (required)
- `--rotation DEGREES`: Image rotation
- `--mirror-x`: Mirror horizontally
- `--mirror-y`: Mirror vertically
- `--threshold VALUE`: Black/white threshold (0-255)
- `--compression`: Enable image compression

## 🔧 Automation & Scheduling

### Cron Job Setup (Linux/macOS)

Add to your crontab to update every 5 minutes:
```bash
# Edit crontab
crontab -e

# Add this line (adjust paths as needed)
*/5 * * * * cd /path/to/BLETag && /usr/bin/python3 calendar_tag_wrapper.py --config my_config.ini
```

### Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Daily, repeat every 5 minutes
4. Set action: Start program
   - Program: `python`
   - Arguments: `calendar_tag_wrapper.py --config my_config.ini`
   - Start in: `C:\path\to\BLETag`

## 🐛 Troubleshooting

### Common Issues

**"No BLE device found"**
- Ensure your e-ink tag is powered on and in pairing mode
- Check that the device address in config is correct
- Try scanning: `python gicisky_writer.py --scan`

**"Connection timeout"**
- Tag may be out of range or low battery
- Try moving closer to the tag
- Restart the tag by power cycling

**"Calendar not updating"**
- Verify ICS URL is accessible
- Check internet connection
- Use `--force-update` to bypass cache

**"Image looks wrong"**
- Adjust rotation and mirroring settings
- Check that tag size matches your device
- Verify image generation with `--dry-run`

### Debug Mode

Enable verbose logging:
```bash
python calendar_tag_wrapper.py --config my_config.ini --verbose
```

## 💡 Customization

### Status Display Customization

Edit `outlook_cal_status.py` to customize:
- Status messages and icons
- Color schemes
- Font sizes and styles
- Layout and positioning

### Adding New Tag Types

Extend `gicisky_writer.py` to support additional e-ink tag models:
- Add new device configurations
- Implement specific protocol variations
- Add size-specific image processing

## 📊 Status Change Detection

The system uses intelligent change detection to minimize unnecessary updates:

- **Status tracking**: JSON file stores current status with SHA256 hash
- **Change detection**: Only updates when calendar status actually changes
- **Battery preservation**: Avoids unnecessary BLE transfers
- **Resource efficiency**: Prevents redundant image processing

Status file example:
```json
{
  "status": "In Meeting",
  "status_hash": "a1b2c3d4...",
  "last_updated": "2024-01-15T10:30:00",
  "next_event_start": "2024-01-15T11:00:00",
  "next_event_end": "2024-01-15T12:00:00"
}
```

## 🤝 Credits & Attribution

This project builds upon the excellent work from the **Gicisky Home Assistant integration**:

- **Original Project**: [hass-gicisky](https://github.com/eigger/hass-gicisky)
- **Original Author**: [eigger](https://github.com/eigger)
- **License**: MIT License


## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

The original gicisky BLE communication code is also under MIT License.


## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

### Development Setup

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

