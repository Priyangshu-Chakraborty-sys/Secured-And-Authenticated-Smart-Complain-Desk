#!/usr/bin/env python3
"""
Script to fix the complaints.csv header to include blockchain fields
"""

import pandas as pd
import csv

def fix_complaints_csv():
    """Fix the CSV header and add missing columns for old records"""
    
    # Read the current CSV
    print("📁 Reading current complaints.csv...")
    
    # Define the correct column names
    new_columns = [
        "Reference No", "Wallet Address", "Name", "Email", "Phone", 
        "Address", "City", "State", "Zip", "Complaint", "Department", 
        "Status", "Date", "Blockchain Status", "Transaction Hash"
    ]
    
    # Read the raw CSV data
    with open('complaints.csv', 'r', newline='', encoding='utf-8') as file:
        reader = csv.reader(file)
        rows = list(reader)
    
    print(f"📊 Found {len(rows)} rows in CSV")
    
    # Get the header
    if rows:
        current_header = rows[0]
        print(f"🔍 Current header: {current_header}")
        
        # Check if we have the new format or old format
        if len(current_header) < len(new_columns):
            print("🔧 Converting old format to new format...")
            
            # Create new data with proper headers
            new_data = []
            
            for i, row in enumerate(rows):
                if i == 0:
                    # Skip the old header
                    continue
                
                # Check if this row has the new format (more columns)
                if len(row) >= 15:  # New format
                    new_data.append(row)
                elif len(row) >= 11:  # Old format
                    # Convert old format to new format
                    new_row = [
                        row[0] if len(row) > 0 else "",  # Reference No
                        "",  # Wallet Address (unknown for old records)
                        row[1] if len(row) > 1 else "",  # Name
                        row[2] if len(row) > 2 else "",  # Email
                        row[3] if len(row) > 3 else "",  # Phone
                        row[4] if len(row) > 4 else "",  # Address
                        row[5] if len(row) > 5 else "",  # City
                        row[6] if len(row) > 6 else "",  # State
                        row[7] if len(row) > 7 else "",  # Zip
                        row[8] if len(row) > 8 else "",  # Complaint
                        row[9] if len(row) > 9 else "",  # Department
                        "Submitted",  # Status (default)
                        row[10] if len(row) > 10 else "",  # Date
                        "Legacy",  # Blockchain Status
                        "N/A"  # Transaction Hash
                    ]
                    new_data.append(new_row)
            
            # Write the fixed CSV
            print("💾 Writing fixed CSV...")
            df = pd.DataFrame(new_data, columns=new_columns)
            df.to_csv('complaints.csv', index=False, quoting=csv.QUOTE_MINIMAL)
            
            print(f"✅ Fixed CSV with {len(new_data)} records")
            print("📋 New header:", new_columns)
            
        else:
            print("✅ CSV already has correct format")
    
    else:
        print("❌ CSV file is empty")

if __name__ == "__main__":
    fix_complaints_csv()
