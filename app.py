from flask import Flask, render_template, request, jsonify
from tax_agent import TaxCalculator, UserDetails
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        data = request.json
        
        # Create user details
        user = UserDetails(
            annual_income=float(data['annual_income']),
            spouse_income=float(data['spouse_income']) if data['spouse_income'] else None,
            has_children=data['has_children'] == 'true',
            num_children=int(data['num_children']) if data['num_children'] else None,
            postcode=data['postcode'],
            has_student_loan=data['has_student_loan'] == 'true',
            pension_contribution=float(data['pension_contribution'])
        )
        
        # Initialize calculator
        calculator = TaxCalculator()
        
        # Fetch thresholds and calculate
        thresholds = calculator.fetch_tax_thresholds()
        calculation = calculator.calculate_tax(user, thresholds)
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