import csv
import random
from datetime import date
from pathlib import Path

from dateutil.relativedelta import relativedelta


def generate():
    out_path = Path(__file__).parent / "synthetic_edge_case.csv"
    
    start_date = date(2022, 1, 1)
    periods = [start_date + relativedelta(months=i) for i in range(36)]
    
    # Define our chart of accounts
    # Tuple of (Account Code, Description, Type (Dr/Cr), Base Monthly Amount)
    accounts = [
        ("4000", "Revenue - Subscription", "Cr", 500000),
        ("4001", "Revenue - One-time implementation", "Cr", 25000),
        ("4002", "Misc Income - Ask Accountant", "Cr", 500), # Ambiguous
        ("4100", "PPP Loan Forgiveness", "Cr", 0), # Edge case: massive one time
        
        ("5000", "COGS - Cloud Hosting", "Dr", 80000),
        ("5001", "COGS - Support Labor", "Dr", 120000),
        
        ("6000", "Salaries & Wages", "Dr", 200000),
        ("6001", "Owner's Discretionary Bonus - Non-Operating", "Dr", 0), # Edge case
        ("6002", "Misc Expense - Do Not Use", "Dr", 1500), # Ambiguous
        
        ("7000", "Rent Expense", "Dr", 25000),
        ("7001", "Legal fees - Standard Corporate", "Dr", 5000),
        ("7002", "Legal fees - Settlement of pending IP litigation", "Dr", 0), # Edge case
        
        ("8000", "Consulting fees - XYZ Management LLC", "Dr", 0), # Edge case related party
        
        ("1000", "Cash", "Dr", 0), # Plug account to balance the books
        ("2000", "Retained Earnings", "Cr", 0) # Equity
    ]
    
    rows = []
    
    for period in periods:
        monthly_debits = 0
        monthly_credits = 0
        
        for acct_code, desc, acct_type, base_amt in accounts:
            if acct_code in ["1000", "2000"]:
                continue
                
            amount = base_amt + random.randint(int(-base_amt*0.1), int(base_amt*0.1)) if base_amt > 0 else 0
            
            # Inject edge cases
            if acct_code == "4100" and period == date(2023, 5, 1):
                amount = 1500000  # PPP Loan forgiven
            elif acct_code == "6001" and period.month == 12:
                amount = 500000  # End of year owner bonus
            elif acct_code == "7002" and period == date(2024, 2, 1):
                amount = 2500000  # Massive IP litigation settlement
            elif acct_code == "8000" and period.month % 3 == 0:
                amount = 75000  # Quarterly related party consulting fee
                
            if amount > 0:
                if acct_type == "Dr":
                    monthly_debits += amount
                    rows.append({
                        "period": period.strftime("%Y-%m-%d"),
                        "account_code": acct_code,
                        "account_description": desc,
                        "debit": amount,
                        "credit": 0
                    })
                else:
                    monthly_credits += amount
                    rows.append({
                        "period": period.strftime("%Y-%m-%d"),
                        "account_code": acct_code,
                        "account_description": desc,
                        "debit": 0,
                        "credit": amount
                    })
                    
        # Balance the books for the month using Cash
        net = monthly_debits - monthly_credits
        if net > 0:
            rows.append({
                "period": period.strftime("%Y-%m-%d"),
                "account_code": "1000",
                "account_description": "Cash",
                "debit": 0,
                "credit": net
            })
        elif net < 0:
            rows.append({
                "period": period.strftime("%Y-%m-%d"),
                "account_code": "1000",
                "account_description": "Cash",
                "debit": -net,
                "credit": 0
            })

    with open(out_path, "w", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["period", "account_code", "account_description", "debit", "credit"])
        writer.writeheader()
        writer.writerows(rows)
        
    print(f"Generated {out_path} with {len(rows)} rows.")

if __name__ == "__main__":
    generate()
