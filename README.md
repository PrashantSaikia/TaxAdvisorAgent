# UK Tax Planning Calculator

A web application for calculating UK tax liabilities and optimization strategies.

## Project Structure

```
.
├── backend/                 # Backend Python code
│   ├── app.py              # Flask application
│   ├── tax_agent.py        # Tax calculation logic
│   └── requirements.txt    # Python dependencies
│
├── frontend/               # Frontend code
│   ├── templates/          # HTML templates
│   │   └── index.html     # Main application page
│   └── static/            # Static assets (CSS, JS, images)
│
└── README.md              # This file
```

## Setup Instructions

1. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

3. Set up environment variables:
Create a `.env` file in the backend directory with your API keys:
```
GEMINI_API_KEY=your_api_key_here
```

4. Run the application:
```bash
cd backend
python app.py
```

5. Access the application:
Open your browser and navigate to `http://localhost:5000`

## Features

- Calculate income tax, National Insurance, and student loan repayments
- Get personalized tax optimization suggestions
- Check benefits eligibility
- Generate detailed PDF reports
- Location-based tax calculations (Scotland vs rest of UK)

## Technologies Used

- Backend:
  - Python
  - Flask
  - Pydantic
  - Google Generative AI

- Frontend:
  - HTML5
  - Tailwind CSS
  - JavaScript
  - jsPDF

## Important Notes

- This is a tool for informational purposes only and should not be considered as financial advice
- Tax thresholds and rates are subject to change
- Always consult a qualified tax advisor for specific advice
- The application uses Gemini AI for calculations and suggestions

## Error Handling

The application includes comprehensive error handling for:
- Invalid user input
- API connection issues
- Missing or invalid API keys
- Failed calculations

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is licensed under the MIT License - see the LICENSE file for details. 