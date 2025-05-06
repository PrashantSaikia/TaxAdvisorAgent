import os
import re
import json
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator
import google.generativeai as genai
import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Load environment variables
load_dotenv()

# Initialize console for rich output
console = Console()

class UserDetails(BaseModel):
    annual_income: float = Field(..., description="Annual income in GBP")
    spouse_income: Optional[float] = Field(None, description="Spouse's annual income in GBP")
    has_children: bool = Field(False, description="Whether the user has children")
    num_children: Optional[int] = Field(None, description="Number of children")
    postcode: str = Field(..., description="UK postcode")
    has_student_loan: bool = Field(False, description="Whether the user has a student loan")
    student_loan_plan: Optional[str] = Field(None, description="Student loan plan type")
    pension_contribution: float = Field(0.0, description="Current pension contribution percentage")
    employment_type: str = Field("employed", description="Employment type: employed, self_employed, ltd_director")
    salary_taken: Optional[float] = Field(None, description="Salary taken by Ltd Company Director")
    
    @validator('annual_income', 'spouse_income', 'pension_contribution')
    def validate_positive_numbers(cls, v):
        if v is not None and v < 0:
            raise ValueError("Value must be positive")
        return v

class TaxThresholds(BaseModel):
    personal_allowance: float
    basic_rate_threshold: float
    higher_rate_threshold: float
    additional_rate_threshold: float
    ni_primary_threshold: float
    ni_upper_earnings_limit: float
    scotland_basic_rate: float
    scotland_intermediate_rate: float
    scotland_higher_rate: float
    scotland_top_rate: float

class TaxCalculator:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        if not self.gemini_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        genai.configure(api_key=self.gemini_key)
        self.model = genai.GenerativeModel('gemini-1.0-pro')
    
    def fetch_tax_thresholds(self) -> TaxThresholds:
        """Return current UK tax thresholds for 2024/25"""
        # Using hardcoded values for 2024/25 as they are well-known and stable
        return TaxThresholds(
            personal_allowance=12570,
            basic_rate_threshold=50270,
            higher_rate_threshold=125140,
            additional_rate_threshold=125140,
            ni_primary_threshold=12570,
            ni_upper_earnings_limit=50270,
            scotland_basic_rate=19,
            scotland_intermediate_rate=20,
            scotland_higher_rate=21,
            scotland_top_rate=47
        )
    
    def calculate_tax(self, user: UserDetails, thresholds: TaxThresholds) -> Dict:
        """Calculate tax liability based on user details and thresholds"""
        # Determine if user is in Scotland
        is_scotland = self._is_scottish_postcode(user.postcode)

        # Calculate taxable income after pension contributions
        pension_amount = user.annual_income * (user.pension_contribution / 100)
        taxable_income = user.annual_income - pension_amount

        # Employment type logic
        if user.employment_type == "ltd_director":
            # Use salary_taken if provided, otherwise up to personal allowance
            salary = user.salary_taken if user.salary_taken is not None else min(user.annual_income, thresholds.personal_allowance)
            remaining_profit = user.annual_income - salary

            # Step 2: Corporation tax on remaining profit
            corp_tax = remaining_profit * 0.25 if remaining_profit > 0 else 0
            post_corp_profit = remaining_profit - corp_tax

            # Step 3: Dividends from post-corp profit
            dividends = post_corp_profit
            dividend_taxable = max(0, dividends - 500)

            # Calculate income tax on salary
            if is_scotland:
                salary_income_tax = self._calculate_scottish_tax(salary, thresholds)
            else:
                salary_income_tax = self._calculate_rUK_tax(salary, thresholds)

            # Apply dividend tax bands (using rUK bands for simplicity)
            total_income = salary + dividends
            basic_band = thresholds.basic_rate_threshold - thresholds.personal_allowance
            higher_band = thresholds.higher_rate_threshold - thresholds.basic_rate_threshold

            dividend_tax = 0
            if dividend_taxable > 0:
                if dividend_taxable <= basic_band:
                    dividend_tax += dividend_taxable * 0.0875
                elif dividend_taxable <= basic_band + higher_band:
                    dividend_tax += basic_band * 0.0875
                    dividend_tax += (dividend_taxable - basic_band) * 0.3375
                else:
                    dividend_tax += basic_band * 0.0875
                    dividend_tax += higher_band * 0.3375
                    dividend_tax += (dividend_taxable - basic_band - higher_band) * 0.3935

            # NI is only on salary above primary threshold
            ni = self._calculate_ni(salary, thresholds)

            # Student loan on total income if applicable
            student_loan = self._calculate_student_loan(total_income) if user.has_student_loan else 0

            net_income = salary + dividends - corp_tax - dividend_tax - ni - student_loan - pension_amount - salary_income_tax

            return {
                "gross_income": user.annual_income,
                "salary": salary,
                "dividends": dividends,
                "corporation_tax": corp_tax,
                "dividend_tax": dividend_tax,
                "pension_contribution": pension_amount,
                "taxable_income": taxable_income,
                "income_tax": salary_income_tax,
                "national_insurance": ni,
                "student_loan": student_loan,
                "net_income": net_income,
                "is_scotland": is_scotland,
                "employment_type": user.employment_type
            }
        elif user.employment_type == "self_employed":
            # Self-employed: tax on profits, Class 2 and Class 4 NI
            # For simplicity, assume all income is profit (no expenses deducted)
            profit = taxable_income
            # Income tax
            if is_scotland:
                tax = self._calculate_scottish_tax(profit, thresholds)
            else:
                tax = self._calculate_rUK_tax(profit, thresholds)
            # Class 2 NI (flat rate, 2024/25: £3.45/week if profits > £12,570)
            class2_ni = 3.45 * 52 if profit > 12570 else 0
            # Class 4 NI (9% on profits between £12,570 and £50,270, 2% above £50,270)
            class4_ni = 0
            if profit > 12570:
                upper_band = min(profit, 50270) - 12570
                if upper_band > 0:
                    class4_ni += upper_band * 0.09
                if profit > 50270:
                    class4_ni += (profit - 50270) * 0.02
            # Student loan
            student_loan = self._calculate_student_loan(profit) if user.has_student_loan else 0
            # Net income
            net_income = user.annual_income - tax - class2_ni - class4_ni - student_loan - pension_amount
            return {
                "gross_income": user.annual_income,
                "pension_contribution": pension_amount,
                "taxable_income": profit,
                "income_tax": tax,
                "class2_ni": class2_ni,
                "class4_ni": class4_ni,
                "national_insurance": class2_ni + class4_ni,
                "student_loan": student_loan,
                "net_income": net_income,
                "is_scotland": is_scotland,
                "employment_type": user.employment_type
            }
        else:
            # Calculate income tax
            if is_scotland:
                tax = self._calculate_scottish_tax(taxable_income, thresholds)
            else:
                tax = self._calculate_rUK_tax(taxable_income, thresholds)
            
            # Calculate National Insurance
            ni = self._calculate_ni(taxable_income, thresholds)
            
            # Calculate student loan repayment if applicable
            student_loan = self._calculate_student_loan(taxable_income) if user.has_student_loan else 0
            
            # Calculate net income
            net_income = user.annual_income - tax - ni - student_loan - pension_amount
            
            return {
                "gross_income": user.annual_income,
                "pension_contribution": pension_amount,
                "taxable_income": taxable_income,
                "income_tax": tax,
                "national_insurance": ni,
                "student_loan": student_loan,
                "net_income": net_income,
                "is_scotland": is_scotland,
                "employment_type": user.employment_type
            }
    
    def _is_scottish_postcode(self, postcode: str) -> bool:
        """Check if postcode is in Scotland"""
        scottish_prefixes = ["AB", "DD", "DG", "EH", "FK", "G", "HS", "IV", "KA", "KW", "KY", "ML", "PA", "PH", "TD", "ZE"]
        return any(postcode.upper().startswith(prefix) for prefix in scottish_prefixes)
    
    def _calculate_scottish_tax(self, income: float, thresholds: TaxThresholds) -> float:
        """Calculate Scottish income tax"""
        tax = 0.0
        if income > thresholds.personal_allowance:
            # Calculate tax on income above personal allowance
            taxable_income = income - thresholds.personal_allowance
            
            # Starter rate (19%)
            if taxable_income > 0:
                starter_rate_band = min(taxable_income, 2306)  # £14,876 - £12,570
                tax += starter_rate_band * 0.19
            
            # Basic rate (20%)
            if taxable_income > 2306:
                basic_rate_band = min(taxable_income - 2306, 11685)  # £26,561 - £14,876
                tax += basic_rate_band * 0.20
            
            # Intermediate rate (21%)
            if taxable_income > (2306 + 11685):
                intermediate_rate_band = min(taxable_income - (2306 + 11685), 17100)  # £43,662 - £26,561
                tax += intermediate_rate_band * 0.21
            
            # Higher rate (42%)
            if taxable_income > (2306 + 11685 + 17100):
                higher_rate_band = min(
                    taxable_income - (2306 + 11685 + 17100),
                    thresholds.higher_rate_threshold - thresholds.personal_allowance - (2306 + 11685 + 17100)
                )
                tax += higher_rate_band * 0.42
            
            # Top rate (47%)
            if taxable_income > (thresholds.higher_rate_threshold - thresholds.personal_allowance):
                top_rate_band = taxable_income - (thresholds.higher_rate_threshold - thresholds.personal_allowance)
                tax += top_rate_band * 0.47
        
        return tax
    
    def _calculate_rUK_tax(self, income: float, thresholds: TaxThresholds) -> float:
        """Calculate rest of the UK income tax"""
        tax = 0.0
        if income > thresholds.personal_allowance:
            # Calculate tax on income above personal allowance
            taxable_income = income - thresholds.personal_allowance
            
            # Basic rate (20%)
            if taxable_income > 0:
                basic_rate_band = min(taxable_income, thresholds.basic_rate_threshold - thresholds.personal_allowance)
                tax += basic_rate_band * 0.20
            
            # Higher rate (40%)
            if taxable_income > (thresholds.basic_rate_threshold - thresholds.personal_allowance):
                higher_rate_band = min(
                    taxable_income - (thresholds.basic_rate_threshold - thresholds.personal_allowance),
                    thresholds.higher_rate_threshold - thresholds.basic_rate_threshold
                )
                tax += higher_rate_band * 0.40
            
            # Additional rate (45%)
            if taxable_income > (thresholds.higher_rate_threshold - thresholds.personal_allowance):
                additional_rate_band = taxable_income - (thresholds.higher_rate_threshold - thresholds.personal_allowance)
                tax += additional_rate_band * 0.45
        
        return tax
    
    def _calculate_ni(self, income: float, thresholds: TaxThresholds) -> float:
        """Calculate National Insurance contributions"""
        ni = 0.0
        if income > thresholds.ni_primary_threshold:
            if income <= thresholds.ni_upper_earnings_limit:
                ni = (income - thresholds.ni_primary_threshold) * 0.12
            else:
                ni = ((thresholds.ni_upper_earnings_limit - thresholds.ni_primary_threshold) * 0.12 +
                      (income - thresholds.ni_upper_earnings_limit) * 0.02)
        return ni
    
    def _calculate_student_loan(self, income: float) -> float:
        """Calculate student loan repayment"""
        threshold = 27295  # Plan 2 threshold for 2024/25
        if income > threshold:
            return (income - threshold) * 0.09
        return 0.0
    
    def get_tax_optimizations(self, user: UserDetails, calculation: Dict) -> List[Dict]:
        """Generate tax optimization suggestions with specific calculations"""
        optimizations = []
        thresholds = self.fetch_tax_thresholds()
        
        # 1. Location-based Tax Optimization
        is_scotland = self._is_scottish_postcode(user.postcode)
        if is_scotland:
            # Calculate tax in rest of the UK for comparison
            rest_of_uk_tax = self._calculate_rUK_tax(user.annual_income, thresholds)
            scottish_tax = calculation['income_tax']
            tax_difference = scottish_tax - rest_of_uk_tax
            
            if tax_difference > 0:
                optimizations.append({
                    "strategy": "Location-based Tax Optimization",
                    "current_value": f"Paying £{scottish_tax:,.2f} in Scottish tax",
                    "suggested_value": f"Move to rest of the UK to pay £{rest_of_uk_tax:,.2f}",
                    "tax_saving": f"£{tax_difference:,.2f} per year",
                    "net_cost": "Moving costs",
                    "explanation": f"As a Scottish taxpayer, you're paying £{tax_difference:,.2f} more in income tax compared to the rest of the UK. This is because Scotland has different tax bands and rates. For example, on an income of £{user.annual_income:,.2f}:"
                    f"\n- Scotland: £{scottish_tax:,.2f} (using Scottish rates: 19% starter, 20% basic, 21% intermediate, 42% higher, 47% top)"
                    f"\n- Rest of the UK: £{rest_of_uk_tax:,.2f} (using rest of the UK rates: 20% basic, 40% higher, 45% additional)"
                    f"\nMoving to the rest of the UK could save you £{tax_difference:,.2f} per year in income tax."
                })
        
        # 2. Pension Contribution Optimization
        if user.pension_contribution < 20:  # If contributing less than 20%
            suggested_pension = min(20, 100)  # Suggest up to 20%
            new_taxable = user.annual_income * (1 - suggested_pension/100)
            new_tax = self._calculate_rUK_tax(new_taxable, thresholds) if not is_scotland else self._calculate_scottish_tax(new_taxable, thresholds)
            tax_saving = calculation['income_tax'] - new_tax
            
            optimizations.append({
                "strategy": "Increase Pension Contributions",
                "current_value": f"{user.pension_contribution}% (£{user.pension_contribution/100 * user.annual_income:,.2f})",
                "suggested_value": f"{suggested_pension}% (£{suggested_pension/100 * user.annual_income:,.2f})",
                "tax_saving": f"£{tax_saving:,.2f}",
                "net_cost": f"£{suggested_pension/100 * user.annual_income - user.pension_contribution/100 * user.annual_income:,.2f}",
                "explanation": f"By increasing your pension contributions to {suggested_pension}%, you would save £{tax_saving:,.2f} in tax. For example, if you contribute £100 to your pension, the government adds £25 in tax relief, so it only costs you £75. This means you're effectively getting £125 in your pension for every £75 you contribute."
            })
        
        # 3. Marriage Allowance (if applicable)
        if user.spouse_income is not None and user.spouse_income < thresholds.personal_allowance:
            marriage_allowance = 1260  # 2024/25 marriage allowance
            tax_saving = marriage_allowance * 0.20  # Basic rate tax relief
            
            optimizations.append({
                "strategy": "Marriage Allowance Transfer",
                "current_value": "Not Claimed",
                "suggested_value": "Claim £1,260 allowance",
                "tax_saving": f"£{tax_saving:,.2f}",
                "net_cost": "£0.00",
                "explanation": f"You can transfer £1,260 of your personal allowance to your spouse, saving £{tax_saving:,.2f} in tax. This is completely free - there's no cost to you, and you don't need to make any payments."
            })
        
        # 4. Child Benefit Optimization
        if user.has_children and user.annual_income > 50000:
            child_benefit = 24.00 * 52  # Weekly rate * 52 weeks
            if user.annual_income > 60000:
                # Full clawback - suggest maximum pension contribution
                max_pension_contribution = 60000  # Annual allowance
                current_pension = user.annual_income * (user.pension_contribution / 100)
                remaining_allowance = max_pension_contribution - current_pension
                
                if remaining_allowance > 0:
                    optimizations.append({
                        "strategy": "Child Benefit Optimization",
                        "current_value": "Full Clawback",
                        "suggested_value": f"Use remaining pension allowance (£{remaining_allowance:,.2f})",
                        "tax_saving": f"£{child_benefit:,.2f}",
                        "net_cost": f"£{remaining_allowance * 0.60:,.2f}",
                        "explanation": f"Your income is above £60,000, so you're losing the full Child Benefit of £{child_benefit:,.2f} per year. You can contribute up to £{remaining_allowance:,.2f} more to your pension this year (after considering your current contributions). The government would add tax relief to your contribution, so the actual cost to you would be £{remaining_allowance * 0.60:,.2f}. Note: You may be able to contribute more if you have unused allowance from previous years."
                    })
            else:
                # Partial clawback
                clawback = (user.annual_income - 50000) / 10000 * child_benefit
                amount_to_sacrifice = user.annual_income - 49999
                current_pension = user.annual_income * (user.pension_contribution / 100)
                remaining_allowance = max_pension_contribution - current_pension
                
                if amount_to_sacrifice <= remaining_allowance:
                    optimizations.append({
                        "strategy": "Child Benefit Optimization",
                        "current_value": f"Partial Clawback (£{clawback:,.2f})",
                        "suggested_value": f"Salary sacrifice £{amount_to_sacrifice:,.2f}",
                        "tax_saving": f"£{clawback:,.2f}",
                        "net_cost": f"£{amount_to_sacrifice * 0.60:,.2f}",
                        "explanation": f"By putting £{amount_to_sacrifice:,.2f} into your pension, you could reduce your taxable income to £49,999 and keep the full Child Benefit. The government would add tax relief to your contribution, so the actual cost to you would be £{amount_to_sacrifice * 0.60:,.2f}."
                    })
        
        # 5. Personal Allowance Tapering (for incomes between £100,000 and £125,140)
        if 100000 <= user.annual_income < 125140:
            # Calculate how much personal allowance is lost
            reduction = (user.annual_income - 100000) / 2
            effective_pa = max(0, thresholds.personal_allowance - reduction)
            tax_saving = reduction * 0.40  # Higher rate tax saving
            
            # Calculate exact salary sacrifice needed
            sacrifice_needed = user.annual_income - 99999
            net_cost = sacrifice_needed * 0.60  # After 40% tax relief
            
            optimizations.append({
                "strategy": "Personal Allowance Tapering",
                "current_value": f"£{reduction:,.2f} reduction in PA",
                "suggested_value": f"Salary sacrifice £{sacrifice_needed:,.2f}",
                "tax_saving": f"£{tax_saving:,.2f}",
                "net_cost": f"£{net_cost:,.2f}",
                "explanation": f"By putting £{sacrifice_needed:,.2f} into your pension, you could reduce your taxable income to £99,999 and keep your full personal allowance. The government would add tax relief to your pension contribution, so the actual cost to you would be £{net_cost:,.2f}."
            })
        
        # 6. Gift Aid Optimization
        if user.annual_income > thresholds.basic_rate_threshold:
            # Calculate potential tax relief on charitable donations
            donation = 1000  # Example donation amount
            tax_relief = donation * 0.25  # Basic rate tax relief
            higher_rate_relief = donation * 0.20  # Additional higher rate relief
            
            optimizations.append({
                "strategy": "Gift Aid Optimization",
                "current_value": "Not Claimed",
                "suggested_value": f"Use Gift Aid on £{donation:,.2f} donation",
                "tax_saving": f"£{tax_relief + higher_rate_relief:,.2f}",
                "net_cost": f"£{donation:,.2f}",
                "explanation": f"If you donate £{donation:,.2f} to charity using Gift Aid, the charity gets £{donation + tax_relief:,.2f} (including £{tax_relief:,.2f} from the government). As a higher rate taxpayer, you can claim back £{higher_rate_relief:,.2f} through your tax return. This means your £{donation:,.2f} donation effectively costs you £{donation - higher_rate_relief:,.2f}."
            })
        
        # 7. Salary Sacrifice for Benefits
        if user.annual_income > thresholds.basic_rate_threshold:
            # Example: Cycle to Work scheme
            cycle_value = 1000  # Example value
            tax_saving = cycle_value * 0.40  # Higher rate tax saving
            ni_saving = cycle_value * 0.02  # NI saving
            
            optimizations.append({
                "strategy": "Salary Sacrifice Benefits",
                "current_value": "Not Using",
                "suggested_value": "Use salary sacrifice for benefits",
                "tax_saving": f"£{tax_saving + ni_saving:,.2f}",
                "net_cost": f"£{cycle_value:,.2f}",
                "explanation": f"Consider using salary sacrifice for benefits like Cycle to Work scheme. For example, a £{cycle_value:,.2f} bike would cost you £{cycle_value - tax_saving - ni_saving:,.2f} after tax and NI savings. Other benefits you could consider:"
                f"\n- Electric car scheme (2% BIK rate)"
                f"\n- Childcare vouchers"
                f"\n- Technology schemes"
            })
        
        return optimizations
    
    def get_benefits_eligibility(self, user: UserDetails) -> List[Dict]:
        """Check benefits eligibility with specific calculations"""
        benefits = []
        thresholds = self.fetch_tax_thresholds()
        
        # 1. Child Benefit
        if user.has_children:
            weekly_rate = 24.00  # First child
            additional_rate = 15.90  # Additional children
            annual_amount = weekly_rate * 52
            if user.num_children and user.num_children > 1:
                annual_amount += (user.num_children - 1) * additional_rate * 52
            
            if user.annual_income <= 50000:
                benefits.append({
                    "benefit": "Child Benefit",
                    "eligible": True,
                    "amount": f"£{annual_amount:,.2f} per year",
                    "explanation": f"You are eligible for the full Child Benefit amount of £{annual_amount:,.2f} per year."
                })
            elif user.annual_income <= 60000:
                reduction = (user.annual_income - 50000) / 10000
                reduced_amount = annual_amount * (1 - reduction)
                benefits.append({
                    "benefit": "Child Benefit",
                    "eligible": True,
                    "amount": f"£{reduced_amount:,.2f} per year (reduced)",
                    "explanation": f"You are eligible for a reduced Child Benefit amount of £{reduced_amount:,.2f} per year due to the High Income Child Benefit Charge."
                })
            else:
                benefits.append({
                    "benefit": "Child Benefit",
                    "eligible": False,
                    "amount": "£0.00",
                    "explanation": "Your income is above £60,000, so you are not eligible for Child Benefit."
                })
        
        # 2. Marriage Allowance
        if user.spouse_income is not None and user.spouse_income < thresholds.personal_allowance:
            benefits.append({
                "benefit": "Marriage Allowance",
                "eligible": True,
                "amount": "£252 per year",
                "explanation": "You can transfer £1,260 of your personal allowance to your spouse, potentially saving £252 in tax per year."
            })
        
        # 3. Tax-Free Childcare
        if user.has_children and user.annual_income <= 100000:
            benefits.append({
                "benefit": "Tax-Free Childcare",
                "eligible": True,
                "amount": "Up to £2,000 per child per year",
                "explanation": "You can get up to £2,000 per child per year towards childcare costs through the Tax-Free Childcare scheme."
            })
        
        # 4. Working Tax Credit
        if user.annual_income <= 18000:  # Approximate threshold
            benefits.append({
                "benefit": "Working Tax Credit",
                "eligible": True,
                "amount": "Variable based on circumstances",
                "explanation": "You may be eligible for Working Tax Credit based on your income and working hours."
            })
        
        # 5. Universal Credit
        if user.annual_income <= 25000:  # Approximate threshold
            benefits.append({
                "benefit": "Universal Credit",
                "eligible": True,
                "amount": "Variable based on circumstances",
                "explanation": "You may be eligible for Universal Credit based on your income and circumstances."
            })
        
        return benefits

def get_user_input() -> UserDetails:
    """Collect user details through console input"""
    console.print(Panel.fit("UK Tax Planning Calculator", style="bold blue"))
    
    try:
        annual_income = float(console.input("[bold]Enter your annual income (£): [/bold]"))
        spouse_income = console.input("[bold]Enter spouse's annual income (£) or press Enter if none: [/bold]")
        spouse_income = float(spouse_income) if spouse_income else None
        
        has_children = console.input("[bold]Do you have children? (y/n): [/bold]").lower() == 'y'
        num_children = None
        if has_children:
            num_children = int(console.input("[bold]How many children? [/bold]"))
        
        postcode = console.input("[bold]Enter your postcode: [/bold]").strip()
        has_student_loan = console.input("[bold]Do you have a student loan? (y/n): [/bold]").lower() == 'y'
        
        pension_contribution = float(console.input("[bold]Enter your current pension contribution percentage: [/bold]"))
        
        employment_type = console.input("[bold]Enter your employment type (employed, self_employed, ltd_director): [/bold]").strip()
        
        return UserDetails(
            annual_income=annual_income,
            spouse_income=spouse_income,
            has_children=has_children,
            num_children=num_children,
            postcode=postcode,
            has_student_loan=has_student_loan,
            pension_contribution=pension_contribution,
            employment_type=employment_type
        )
    except ValueError as e:
        console.print(f"[red]Invalid input: {str(e)}[/red]")
        raise

def display_results(calculation: Dict, optimizations: List[Dict], benefits: List[Dict]):
    """Display calculation results and recommendations"""
    # Create a table for the calculation breakdown
    table = Table(title="Tax Calculation Breakdown")
    table.add_column("Item", style="cyan")
    table.add_column("Amount (£)", justify="right", style="green")
    
    table.add_row("Gross Income", f"{calculation['gross_income']:,.2f}")
    table.add_row("Pension Contribution", f"{calculation['pension_contribution']:,.2f}")
    table.add_row("Taxable Income", f"{calculation['taxable_income']:,.2f}")
    table.add_row("Income Tax", f"{calculation['income_tax']:,.2f}")
    table.add_row("National Insurance", f"{calculation['national_insurance']:,.2f}")
    table.add_row("Student Loan", f"{calculation['student_loan']:,.2f}")
    table.add_row("Net Income", f"{calculation['net_income']:,.2f}")
    
    console.print(table)
    
    # Display tax optimizations
    console.print("\n[bold blue]Tax Optimization Suggestions:[/bold blue]")
    for opt in optimizations:
        console.print(f"\n[bold]{opt['strategy']}[/bold]")
        console.print(f"Current: {opt['current_value']}")
        console.print(f"Suggested: {opt['suggested_value']}")
        console.print(f"Potential Tax Saving: {opt['tax_saving']}")
        console.print(f"Net Cost: {opt['net_cost']}")
        console.print(f"Explanation: {opt['explanation']}")
    
    # Display benefits eligibility
    console.print("\n[bold blue]Benefits Eligibility:[/bold blue]")
    for benefit in benefits:
        status = "[green]Eligible[/green]" if benefit['eligible'] else "[red]Not Eligible[/red]"
        console.print(f"\n[bold]{benefit['benefit']}[/bold] - {status}")
        console.print(f"Amount: {benefit['amount']}")
        console.print(f"Explanation: {benefit['explanation']}")
    
    # Display disclaimer
    console.print("\n[bold red]Disclaimer:[/bold red]")
    console.print("This calculation is for informational purposes only and should not be considered as financial advice.")
    console.print("Tax thresholds and rates are subject to change. Please consult a qualified tax advisor for specific advice.")

def main():
    try:
        # Initialize calculator
        calculator = TaxCalculator()
        
        # Get user input
        user_details = get_user_input()
        
        # Fetch current tax thresholds
        thresholds = calculator.fetch_tax_thresholds()
        
        # Calculate tax
        calculation = calculator.calculate_tax(user_details, thresholds)
        
        # Get optimizations and benefits
        optimizations = calculator.get_tax_optimizations(user_details, calculation)
        benefits = calculator.get_benefits_eligibility(user_details)
        
        # Display results
        display_results(calculation, optimizations, benefits)
        
    except Exception as e:
        console.print(f"[red]An error occurred: {str(e)}[/red]")
        console.print("Please ensure you have set up your API keys in the .env file:")
        console.print("GEMINI_API_KEY=your_gemini_key")

if __name__ == "__main__":
    main() 