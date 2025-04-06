# UK Tax Planning Calculator

A web-based tax planning calculator that helps users calculate their UK tax liability, identify potential tax optimizations, and check benefits eligibility.

## Features

- Modern, responsive web interface
- Real-time tax calculations
- Scotland vs. rUK tax calculations
- National Insurance calculations
- Student loan repayment calculations
- Tax optimization suggestions
- Benefits eligibility checking
- Detailed breakdown of calculations

## Prerequisites

- Python 3.8 or higher
- Google Gemini API key

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd uk-tax-planner
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the project root with your API key:
```
GEMINI_API_KEY=your_gemini_key_here
```

## Running the Application

1. Start the Flask server:
```bash
python app.py
```

2. Open your web browser and navigate to:
```
http://localhost:5000
```

## Deployment Options

### Option 1: Heroku

1. Create a new Heroku app:
```bash
heroku create your-app-name
```

2. Set the environment variable:
```bash
heroku config:set GEMINI_API_KEY=your_gemini_key_here
```

3. Deploy the app:
```bash
git push heroku main
```

### Option 2: Python Anywhere

1. Create a new Python Anywhere account
2. Upload your code files
3. Create a new web app
4. Set up the virtual environment and install requirements
5. Configure the WSGI file
6. Set the environment variable in the web app configuration

### Option 3: AWS Elastic Beanstalk

1. Install the AWS CLI and EB CLI
2. Initialize your EB application:
```bash
eb init -p python-3.8 uk-tax-planner
```

3. Create an environment:
```bash
eb create uk-tax-planner-env
```

4. Set the environment variable:
```bash
eb setenv GEMINI_API_KEY=your_gemini_key_here
```

## Project Structure

```
uk-tax-planner/
├── app.py              # Flask application
├── tax_agent.py        # Tax calculation logic
├── requirements.txt    # Python dependencies
├── .env               # Environment variables
└── templates/
    └── index.html     # Web interface
```

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