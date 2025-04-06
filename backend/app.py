from flask import Flask, render_template, request, jsonify, send_from_directory
from tax_agent import TaxCalculator, UserDetails
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, 
            template_folder='../frontend/templates',
            static_folder='../frontend/static')

def safe_float_convert(value, default=0.0):
    """Safely convert a value to float, returning default if conversion fails"""
    try:
        return float(value) if value else default
    except (ValueError, TypeError):
        return default

def safe_int_convert(value, default=0):
    """Safely convert a value to int, returning default if conversion fails"""
    try:
        return int(value) if value else default
    except (ValueError, TypeError):
        return default

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        data = request.get_json()
        
        # Safely convert and validate numeric inputs
        annual_income = safe_float_convert(data.get('annual_income'))
        spouse_income = safe_float_convert(data.get('spouse_income'))
        pension_contribution = safe_float_convert(data.get('pension_contribution'))
        num_children = safe_int_convert(data.get('num_children'))
        
        # Initialize user details with validated data
        user = UserDetails(
            annual_income=annual_income,
            spouse_income=spouse_income if spouse_income > 0 else None,
            has_children=num_children > 0,
            num_children=num_children if num_children > 0 else None,
            postcode=str(data.get('postcode', '')),
            has_student_loan=data.get('student_loan_plan') != 'none',
            student_loan_plan=str(data.get('student_loan_plan', 'none')),
            pension_contribution=pension_contribution
        )
        
        # Initialize tax calculator
        calculator = TaxCalculator()
        
        # Get tax thresholds
        thresholds = calculator.fetch_tax_thresholds()
        
        # Calculate tax
        calculation = calculator.calculate_tax(user, thresholds)
        
        # Get optimizations and benefits
        optimizations = calculator.get_tax_optimizations(user, calculation)
        benefits = calculator.get_benefits_eligibility(user)
        
        return jsonify({
            'success': True,
            'calculation': calculation,
            'optimizations': optimizations,
            'benefits': benefits
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

if __name__ == '__main__':
    app.run(debug=True) 