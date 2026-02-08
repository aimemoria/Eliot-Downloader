# Eliot Downloader

A comprehensive web-based media downloader built with Flask and yt-dlp. This is one of many programs I have programmed for practice to strengthen my skills in full-stack Python development, user authentication, and real-time web applications.

Eliot Downloader allows users to download videos, extract audio, and save photos from over 1000+ platforms including YouTube, Instagram, TikTok, Facebook, Vimeo, Pinterest, and many more.

## Features

### Core Functionality
- **Multi-Format Downloads**: Videos (MP4), Audio (MP3), and Photos (JPG/PNG/GIF)
- **Universal Platform Support**: Works with 1000+ websites and platforms
- **Quality Selection**: Multiple quality options (1080p, 720p, 480p, etc.)
- **Real-Time Progress**: Live download progress with speed and ETA indicators
- **Cookie Authentication**: Support for restricted/private content access
- **Batch Processing**: Handle multiple downloads efficiently

### User Management
- **User Registration & Login**: Secure account system with password hashing
- **Activity Tracking**: Complete download history and statistics
- **Personal Dashboard**: User-specific analytics and download management
- **Session Management**: Secure user sessions with automatic logout

### Admin System
- **Admin Dashboard**: Complete system overview and analytics
- **User Management**: View and manage all user accounts
- **Contact Inbox**: Manage user inquiries and support requests
- **Traffic Analytics**: Monitor visitor statistics and usage patterns
- **Password Management**: Secure admin password changes
- **System Monitoring**: Real-time activity logs and error tracking

### Platform-Specific Features
- **YouTube**: Videos, Shorts, live streams, and audio extraction
- **Instagram**: Posts, Stories, Reels, and IGTV content
- **TikTok**: Videos and photo downloads
- **Facebook**: Videos and photo content
- **Pinterest**: High-resolution image downloads
- **Vimeo**: All video qualities and formats
- **Twitter/X**: Videos and images
- **Custom Platforms**: Configurable platform-specific settings

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- FFmpeg (optional, for advanced video processing)

### Step 1: Clone or Download
```bash
git clone <repository-url>
cd eliot-downloader
```

### Step 2: Create Virtual Environment (Recommended)
```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Run the Application
```bash
python main.py
```

### Step 5: Access the Application
Open your web browser and navigate to: `http://127.0.0.1:5000`

## Requirements

```txt
Flask==2.3.3
Flask-SocketIO==5.3.6
python-socketio==5.8.0
Werkzeug==2.3.7
yt-dlp>=2024.12.13
```

## Directory Structure

```
Eliot-Downloader/
├── main.py                     # Main application file
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── eliot_downloader.db         # SQLite database (auto-created)
├── downloader.log             # Application logs
├── templates/                  # HTML templates
│   ├── index.html             # Main download page
│   ├── login.html             # User login
│   ├── register.html          # User registration
│   ├── user_dashboard.html    # User dashboard
│   ├── admin_dashboard.html   # Admin dashboard
│   ├── admin_users.html       # Admin user management
│   ├── admin_inbox.html       # Admin contact inbox
│   ├── privacy.html           # Privacy policy
│   ├── terms.html             # Terms of service
│   └── contact.html           # Contact form
├── static/                     # Static files
│   ├── css/
│   │   └── styles.css         # Main stylesheet
│   ├── js/
│   │   ├── main.js            # Main application JavaScript
│   │   ├── auth.js            # Authentication JavaScript
│   │   └── contact.js         # Contact form JavaScript
│   └── image/                 # Platform icons
│       ├── youtube.png
│       ├── instagram.png
│       └── ...
├── downloads/                  # Downloaded files (auto-created)
├── cookies/                    # Uploaded cookie files (auto-created)
└── bin/                       # FFmpeg binaries (optional)
```

## Usage

### For Regular Users

1. **Registration**: Create an account to track your downloads
2. **Login**: Access your personal dashboard and history
3. **Download Content**:
   - Paste any supported URL
   - Select format (Video/Audio/Photo)
   - Choose quality options
   - Click "Analyze Content" then "Start Download"
4. **Cookie Upload**: For restricted content, upload browser cookies
5. **Dashboard**: View download history and statistics

### For Administrators

**Default Admin Credentials:**
- Username: `admin@eliot`
- Password: Set via `ADMIN_PASSWORD` environment variable (defaults to `changeme123`)
- Change the admin password immediately after first login

**Admin Features:**
1. **Dashboard**: System overview and statistics
2. **User Management**: View and manage user accounts
3. **Inbox**: Handle user inquiries from contact forms
4. **Analytics**: Monitor traffic and usage statistics
5. **Settings**: Change admin password and system settings

## Configuration

### Platform Configuration
Edit the `PLATFORM_CONFIGS` dictionary in `main.py` to add or modify platform-specific settings:

```python
PLATFORM_CONFIGS = {
    'example.com': {
        'requires_cookies': True,
        'description': 'Example Platform',
        'user_agent': 'Custom User Agent',
        'headers': {
            'Custom-Header': 'Value'
        }
    }
}
```

### Environment Variables
Set these for production deployment:
```bash
export SECRET_KEY="your-secure-random-key"
export ADMIN_PASSWORD="your-secure-admin-password"
```

### Security Settings
- Set `SECRET_KEY` and `ADMIN_PASSWORD` via environment variables
- Update admin credentials on first login
- Configure HTTPS in production environments
- Set up proper firewall rules

### Database Configuration
The application uses SQLite by default. For production, consider:
- Regular database backups
- Database optimization for large user bases
- Migration to PostgreSQL for high-traffic scenarios

## Cookie Management

### Extracting Browser Cookies
1. **Chrome**: Use browser extensions or developer tools
2. **Firefox**: Export cookies to Netscape format
3. **Safari**: Use third-party cookie exporters

### Supported Cookie Format
- Netscape HTTP Cookie File format (.txt)
- One cookie file per platform/account
- Automatic cleanup after 24 hours

## Troubleshooting

### Common Issues

1. **Module Not Found Errors**
   ```bash
   pip install -r requirements.txt
   ```

2. **FFmpeg Not Found**
   - Download FFmpeg and place in `bin/` directory
   - Or install system-wide

3. **Database Lock Errors**
   - Restart the application
   - Check file permissions
   - Ensure no other instances are running

4. **Download Failures**
   - Check internet connection
   - Verify URL format
   - Try uploading cookies for restricted content
   - Check platform-specific requirements

5. **Port Already in Use**
   - Change port in `main.py`: `socketio.run(app, port=5001)`
   - Or kill existing processes using port 5000

### Performance Optimization
- Use SSD storage for faster file operations
- Increase RAM for handling multiple concurrent downloads
- Configure proper network bandwidth limits
- Regular cleanup of old downloaded files

## API Endpoints

### Public Endpoints
- `GET /` - Main application page
- `POST /get_video_info` - Analyze URL and get video information
- `POST /start_download` - Initiate download process
- `GET /download_file/<session_id>` - Download completed file

### Authentication Endpoints
- `POST /login` - User login
- `POST /register` - User registration
- `GET /logout` - User logout
- `GET /dashboard` - User dashboard (requires login)

### Admin Endpoints (requires admin access)
- `GET /admin/dashboard` - Admin overview
- `GET /admin/users` - User management
- `GET /admin/inbox` - Contact submissions
- `POST /admin/change_password` - Change admin password

## Security Features

- **Password Hashing**: Secure password storage using Werkzeug
- **Session Management**: Secure user sessions with Flask
- **Input Validation**: Comprehensive form and data validation
- **CSRF Protection**: Built-in security measures
- **Rate Limiting**: Prevents abuse and overloading
- **Access Control**: Role-based permissions (user/admin)

## Legal Considerations

**Important**: This tool is for personal use only. Users must:

- Only download content they own or have permission to access
- Respect platform terms of service and community guidelines
- Comply with local copyright and intellectual property laws
- Not use for commercial redistribution without proper licenses
- Understand that some platforms prohibit downloading in their ToS

**Disclaimer**: The developers are not responsible for any misuse of this software. Users assume full responsibility for compliance with applicable laws and platform policies.

## Contributing

### Development Setup
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

### Code Standards
- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Include comments for complex logic
- Test all new features
- Update documentation as needed

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Support

### Getting Help
1. Check this README for common issues
2. Review the application logs (`downloader.log`)
3. Use the contact form for support requests
4. Check platform-specific requirements

### Reporting Issues
When reporting issues, include:
- Operating system and Python version
- Complete error messages
- Steps to reproduce the problem
- Platform URLs that are failing

## Changelog

### Version 1.0.0
- Initial release
- Multi-platform download support
- User authentication system
- Admin dashboard
- Cookie management
- Real-time progress tracking
- Contact form system
- Traffic analytics

---

**Eliot Downloader** - Advanced legitimate application for downloading videos, audio, and photos from 1000+ platforms. Built with Flask, featuring comprehensive user management and admin controls.
