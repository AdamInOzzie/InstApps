# Instapp - Google Sheets Integration

A Streamlit web application for managing Google Sheets data with service account authentication. This application provides comprehensive spreadsheet management capabilities including:

- Listing spreadsheets (including shared files)
- Data viewing and manipulation
- CSV upload functionality
- Dynamic form generation from spreadsheet inputs
- Real-time updates

## Features

- 📊 Spreadsheet Management
- 🔄 Real-time Updates
- 📥 CSV Upload Support
- 🔐 Secure Authentication
- 📱 Responsive Design

## Prerequisites

- Python 3.11+
- Google Cloud Service Account
- Required Google API Permissions:
  - Google Sheets API
  - Google Drive API

## Setup

1. Clone the repository
2. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
3. Add your Google Service Account JSON to the environment variables
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Environment Variables

Required environment variables:
- `GOOGLE_SERVICE_ACCOUNT_JSON`: Your Google Service Account credentials in JSON format

## Running the Application

```bash
streamlit run main.py
```

The application will be available at `http://localhost:5000`

## Deployment

This application is configured for deployment on Replit. The necessary configuration files are included in the repository.

## Project Structure

```
├── .streamlit/          # Streamlit configuration
├── utils/              # Utility functions
├── main.py            # Main application file
├── requirements.txt   # Python dependencies
└── README.md         # Documentation
```

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
