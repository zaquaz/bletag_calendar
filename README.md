# BLE E-ink Calendar Status Display

An "intelligent" system for displaying Outlook calendar status on Bluetooth Low Energy (BLE) e-ink tags with change detection and minimal power consumption.

Supports gicisky tags (PICKSMART / NEMR********) tags.


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

### Display Modes
- **Status Display**: Classic calendar status with availability indicators
- **Proportional scaling**: Support for 1.54", 2.13", 2.9", 4.2", and 7.5" e-ink displays

### Advanced Image Processing
- **Rotation support**: 0°, 90°, 180°, 270° rotation options
- **Mirroring capabilities**: Horizontal and vertical image mirroring
- **Smart compression**: Gicisky-compatible image compression for faster transfers

### Robust BLE Communication
- **Enhanced device discovery**: Multi-method BLE scanning with smart fallbacks
- **Device pattern recognition**: Automatically detects PICKSMART, GICISKY, EINK, and TAG devices
- **Configurable timeouts**: Adjustable scan and connection timeouts for different environments
- **Interactive device selection**: User-guided device discovery and selection
- **Connection testing**: Test device connectivity without writing images
- **Service inspection**: Detailed BLE service and characteristic discovery
- **Enhanced reliability**: Configurable timeouts with exponential backoff retry
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

## 🛠️ Installation

### Prerequisites
- Python 3.8 or higher
- Gicisky or compatible BLE e-ink tag
- Outlook calendar with public ICS URL access

### Setup

1. **Clone and navigate to the project:**
   ```bash
   git clone https://github.com/zaquaz/bletag_calendar.git
   cd bletag_calendar
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure your settings:**
   ```bash
   cp calendar_tag_config.ini.example calendar_tag_config.ini
   # Edit calendar_tag_config.ini with your calendar URL and device address
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
   tag_size = 2.9  # Supported sizes: 1.54, 2.13, 2.9, 4.2, 7.5
   check_window = 5
   
   [device]
   address = YOUR_TAG_BLE_ADDRESS
   rotation = 90
   mirror_x = false
   mirror_y = false
   scan_timeout = 10
   connection_timeout = 30
   compression = false
   no_red = true
   
   [options]
   freshness_threshold = 5
   status_file = calendar_status.json
   ```

## 🚀 Usage

### Quick Start

**Status Display Mode:**
```bash
python calendar_tag_wrapper.py --config calendar_tag_config.ini
```

### Advanced Options

**Test without sending to device:**
```bash
python calendar_tag_wrapper.py --config calendar_tag_config.ini --dry-run
```

**Force update regardless of status changes:**
```bash
python calendar_tag_wrapper.py --config calendar_tag_config.ini --force-update
```

**Use command-line overrides:**
```bash
python calendar_tag_wrapper.py \
  --config calendar_tag_config.ini \
  --device AA:BB:CC:DD:EE:FF \
  --rotation 180 \
  --mirror-x \
  --scan-timeout 30 \
  --connection-timeout 60
```

### BLE Device Discovery

**Scan for all BLE devices:**
```bash
python gicisky_writer.py --scan-devices --scan-timeout 10
```

**Find Gicisky-compatible devices:**
```bash
python gicisky_writer.py --find-gicisky --scan-timeout 10
```

**Interactive device selection:**
```bash
python gicisky_writer.py --interactive --scan-timeout 10
```

**Test device connectivity:**
```bash
python gicisky_writer.py --test-connection "PICKSMART" --scan-timeout 10
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
  --mirror-x \
  --scan-timeout 15 \
  --connection-timeout 45
```

## 📋 Command Reference

### calendar_tag_wrapper.py
Main automation script for status display mode.

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
- `--scan-timeout SECONDS`: BLE scan timeout (default: 10s)
- `--connection-timeout SECONDS`: BLE connection timeout (default: 30s)
- `--compression`: Enable image compression
- `--no-red`: Disable red channel processing

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
- `--tag-size SIZE`: Tag size for proportional scaling (1.54, 2.13, 2.9, 4.2, 7.5)
- `--save-image`: Save generated image to file

### gicisky_writer.py
BLE communication and image transfer to e-ink tags.

```bash
python gicisky_writer.py [IMAGE] --device ADDRESS [OPTIONS]
```

**Key Options:**
- `IMAGE`: Path to image file (required for writing)
- `--device ADDRESS`: BLE device address (required for image writing)
- `--rotation DEGREES`: Image rotation (0, 90, 180, 270)
- `--mirror-x`: Mirror horizontally
- `--mirror-y`: Mirror vertically
- `--threshold VALUE`: Black/white threshold (0-255)
- `--compression`: Enable image compression
- `--scan-timeout SECONDS`: BLE scan timeout (default: 10s)
- `--connection-timeout SECONDS`: BLE connection timeout (default: 30s)
- `--scan-devices`: Scan for all BLE devices and exit
- `--find-gicisky`: Find Gicisky-compatible devices and exit
- `--interactive`: Interactive device selection and exit
- `--test-connection DEVICE`: Test connection to specific device and exit

## 📡 BLE Device Discovery & Scanning

The system includes comprehensive Bluetooth Low Energy device discovery tools to improve connection reliability and help troubleshoot device issues.

### Smart Discovery Algorithm

The BLE discovery system uses multiple methods to find your device:

1. **Direct address lookup** - Exact MAC address matching
2. **Name pattern matching** - Search by device name or partial string
3. **Gicisky device detection** - Automatic recognition of common patterns:
   - PICKSMART
   - GICISKY 
   - EINK / E-INK
   - TAG

### Discovery Tools

**Scan all BLE devices in range:**
```bash
python gicisky_writer.py --scan-devices --scan-timeout 15
```

**Find only Gicisky-compatible devices:**
```bash
python gicisky_writer.py --find-gicisky --scan-timeout 10
```

**Interactive device selection:**
```bash
python gicisky_writer.py --interactive
```

**Test device connectivity:**
```bash
python gicisky_writer.py --test-connection "PICKSMART"
python gicisky_writer.py --test-connection "AA:BB:CC:DD:EE:FF"
```

### Configuration Options

Configure BLE timeouts and options in your config file:

```ini
[device]
# Device address or name pattern
address = PICKSMART

# BLE scanning timeouts (in seconds)
scan_timeout = 10
connection_timeout = 30

# Device options
compression = false
no_red = true
```

### Timeout Tuning

Adjust timeouts based on your environment:

- **Fast/Stable**: `scan_timeout = 5`, `connection_timeout = 15`
- **Reliable/Default**: `scan_timeout = 10`, `connection_timeout = 30` 
- **High Reliability**: `scan_timeout = 30`, `connection_timeout = 90`

## 🔧 Automation & Scheduling

### Cron Job Setup (Linux/macOS)

Add to your crontab to update every 5 minutes:
```bash
# Edit crontab
crontab -e

# Add this line (adjust paths as needed)
*/5 * * * * cd /path/to/bletag_calendar && /usr/bin/python3 calendar_tag_wrapper.py --config my_config.ini
```

### Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Daily, repeat every 5 minutes
4. Set action: Start program
   - Program: `python`
   - Arguments: `calendar_tag_wrapper.py --config my_config.ini`
   - Start in: `C:\path\to\bletag_calendar`

## 🐛 Troubleshooting

### Common Issues

**"No BLE device found"**
- Ensure your e-ink tag is powered on and in pairing mode
- Check that the device address in config is correct
- Use device discovery tools:
  ```bash
  python gicisky_writer.py --scan-devices
  python gicisky_writer.py --find-gicisky
  python gicisky_writer.py --interactive
  ```
- Try using device name instead of address (e.g., "PICKSMART")

**"Connection timeout"**
- Tag may be out of range or low battery
- Try moving closer to the tag
- Increase timeout values in config or command line:
  ```bash
  --scan-timeout 30 --connection-timeout 90
  ```
- Test connectivity: `python gicisky_writer.py --test-connection "YOUR_DEVICE"`
- Restart the tag by power cycling

**"Calendar not updating"**
- Verify ICS URL is accessible
- Check internet connection
- Use `--force-update` to bypass cache
- Test URL: `python test_calendar_url.py "YOUR_ICS_URL"`

**"Image looks wrong"**
- Adjust rotation and mirroring settings
- Check that tag size matches your device
- Verify image generation with `--dry-run`

### Debug Mode

Enable verbose logging by setting log level:
```bash
# Python logging shows INFO level by default
# All scripts now use consistent logging framework
python calendar_tag_wrapper.py --config my_config.ini
```

### Content-Type Detection Issues

If calendar URL returns HTML instead of iCalendar data:
- Check calendar sharing permissions in Outlook
- Verify the ICS URL is publicly accessible
- Use the test tool: `python test_content_type_detection.py`

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

The image generation system automatically scales fonts, borders, and spacing proportionally based on the selected tag size, ensuring consistent appearance across all supported display dimensions.

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

## 🆕 Recent Updates

### BLE Device Discovery & Connection Improvements
- **Enhanced device scanning**: Multi-method BLE discovery with smart fallbacks
- **Device pattern recognition**: Automatic detection of PICKSMART, GICISKY, EINK devices
- **Configurable timeouts**: Adjustable scan and connection timeouts for reliability
- **Interactive tools**: User-guided device selection and connection testing
- **Service inspection**: Detailed BLE service discovery for debugging
- **Smart discovery algorithm**: Tries multiple methods (address, name, pattern) automatically

### Logging Framework Standardization
- **Consistent logging**: All scripts now use Python logging framework instead of print statements
- **Log level control**: INFO, WARNING, ERROR levels for different message types
- **Module-level configuration**: Proper logger setup for library usage
- **User interface preservation**: Interactive prompts still use print for immediate feedback

### Calendar Processing Enhancements
- **Improved error handling**: Better ICS URL parsing and network error recovery
- **Content-Type detection**: Proper HTTP header checking for HTML vs iCalendar content
- **Enhanced logging**: More detailed status information and error messages
- **Configuration flexibility**: More granular control over device and display options

### Code Quality Improvements
- **Import organization**: Standardized import grouping (stdlib, third-party, local)
- **Modern Python compatibility**: Updated deprecated asyncio usage
- **Enhanced documentation**: Improved code comments and function documentation
- **Error handling**: Robust exception handling throughout the codebase

### Files Modified
- **gicisky_writer.py**: Added comprehensive BLE scanning, device discovery, connection testing, and logging
- **calendar_tag_wrapper.py**: Integrated BLE scanning options and enhanced configuration
- **outlook_cal_status.py**: Improved error handling, content-type detection, and logging
- **README.md**: Complete documentation overhaul reflecting all changes

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
4. Test thoroughly with various tag sizes and configurations
5. Update documentation if needed
6. Submit a pull request

### Testing

Use the included test tools:
- `test_calendar_url.py` - Verify calendar URL access
- `test_content_type_detection.py` - Test content-type detection logic
- `--dry-run` mode - Test configurations safely
