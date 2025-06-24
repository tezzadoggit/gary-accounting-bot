#!/usr/bin/env python3
"""
Gary's Accounting Bot - Production Server
Handles WhatsApp messages and updates Google Sheets
"""

import os
import json
import re
from datetime import datetime
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

class GaryBot:
    def __init__(self):
        # Gary's configuration
        self.DAILY_RATE = 320.11
        self.OVERTIME_RATE = 61.56
        self.GARY_PHONE = "+447827491339"
        
        # Initialize services
        self.setup_google_sheets()
        self.setup_twilio()
        
        # Store pending confirmations (in production, use database)
        self.pending_confirmations = {}
    
    def setup_google_sheets(self):
        """Setup Google Sheets connection"""
        try:
            # Get credentials from environment variable
            creds_json = os.getenv('GOOGLE_CREDENTIALS')
            if not creds_json:
                raise Exception("GOOGLE_CREDENTIALS environment variable not found")
            
            creds_dict = json.loads(creds_json)
            
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
            self.gc = gspread.authorize(credentials)
            
            # Open Gary's sheet
            sheet_id = "1FIus7iR4iMbxjuDMDYwpg8dxsb-suh6O6EbA_yJ4Oi0"
            self.spreadsheet = self.gc.open_by_key(sheet_id)
            self.paye_sheet = self.spreadsheet.worksheet('PAYE Tracker')
            
            print("✅ Google Sheets connected successfully")
            
        except Exception as e:
            print(f"❌ Google Sheets setup error: {e}")
    
    def setup_twilio(self):
        """Setup Twilio client"""
        try:
            account_sid = os.getenv('TWILIO_ACCOUNT_SID')
            auth_token = os.getenv('TWILIO_AUTH_TOKEN')
            self.twilio_client = Client(account_sid, auth_token)
            self.twilio_number = os.getenv('TWILIO_WHATSAPP_NUMBER')
            
            print("✅ Twilio connected successfully")
            
        except Exception as e:
            print(f"❌ Twilio setup error: {e}")
    
    def process_message(self, message: str, from_number: str) -> str:
        """Main message processing logic"""
        
        # Only respond to Gary's number
        if from_number != self.GARY_PHONE:
            return "Sorry, this bot is only for Gary's use."
        
        message = message.lower().strip()
        
        # Handle confirmations
        if message in ['yes', 'y', 'confirm', 'ok']:
            return self.handle_confirmation(from_number, True)
        elif message in ['no', 'n', 'cancel']:
            return self.handle_confirmation(from_number, False)
        
        # Handle time messages
        if self.is_time_message(message):
            return self.handle_time_request(message, from_number)
        elif message in ['help', 'status']:
            return self.help_message()
        else:
            return ("⏰ Send your hours: 'worked 7:30 till 17:00'\n"
                   "📱 Or try: 'worked normal day'\n"
                   "❓ Send 'help' for more commands")
    
    def is_time_message(self, message: str) -> bool:
        """Check if message is about time worked"""
        time_keywords = ['worked', 'work', 'till', 'until', 'to', ':', 'normal', 'day', 'saturday', 'sunday']
        return any(keyword in message for keyword in time_keywords)
    
    def handle_time_request(self, message: str, from_number: str) -> str:
        """Process time entry request - ALWAYS confirm first"""
        
        # Parse the time message
        time_data = self.parse_time_message(message)
        
        if 'error' in time_data:
            return ("⏰ Time format help:\n\n"
                   "✅ 'worked 7:30 till 16:00' (normal day)\n"
                   "✅ 'worked 7:30 till 17:00' (1hr overtime)\n" 
                   "✅ 'worked 8:00 till 13:00 Saturday'\n"
                   "✅ 'worked normal day'\n\n"
                   "📝 Use 24-hour format (17:00 not 5pm)")
        
        # Store for confirmation
        self.pending_confirmations[from_number] = {
            'type': 'time_entry',
            'data': time_data,
            'original_message': message
        }
        
        # Generate confirmation message
        return self.format_time_confirmation(time_data)
    
    def parse_time_message(self, message: str) -> dict:
        """Parse time message - expects 24-hour format"""
        
        # Handle simple patterns first
        if 'normal' in message or 'standard' in message:
            return {
                'type': 'weekday',
                'start_time': '07:30',
                'end_time': '16:00',
                'total_hours': 8.5,
                'paid_hours': 7.5,
                'overtime_hours': 0,
                'total_pay': self.DAILY_RATE,
                'date': datetime.now().strftime("%Y-%m-%d")
            }
        
        # Check for weekend
        is_weekend = any(day in message for day in ['saturday', 'sunday', 'weekend'])
        
        if is_weekend:
            return {
                'type': 'weekend',
                'start_time': '08:00',
                'end_time': '13:00',
                'total_hours': 5.0,
                'paid_hours': 5.0,
                'overtime_hours': 0,
                'total_pay': self.DAILY_RATE,
                'date': datetime.now().strftime("%Y-%m-%d")
            }
        
        # Parse 24-hour time ranges
        time_match = re.search(r'(\d{1,2}:\d{2})\s*(?:till?|to|until|-)\s*(\d{1,2}:\d{2})', message)
        
        if not time_match:
            return {'error': 'Could not parse time format'}
        
        start_time = time_match.group(1)
        end_time = time_match.group(2)
        
        # Validate 24-hour format
        if not self.is_valid_24hour_time(start_time) or not self.is_valid_24hour_time(end_time):
            return {'error': 'Invalid time format'}
        
        # Calculate hours and overtime
        total_hours = self.calculate_hours_between(start_time, end_time)
        paid_hours = total_hours - 1.0 if total_hours > 6 else total_hours
        
        # Calculate overtime (anything after 16:00)
        end_hour = int(end_time.split(':')[0])
        end_minute = int(end_time.split(':')[1])
        
        normal_end_minutes = 16 * 60  # 16:00 = 960 minutes
        actual_end_minutes = end_hour * 60 + end_minute
        
        if actual_end_minutes > normal_end_minutes:
            overtime_hours = (actual_end_minutes - normal_end_minutes) / 60.0
        else:
            overtime_hours = 0
        
        total_pay = self.DAILY_RATE + (overtime_hours * self.OVERTIME_RATE)
        
        return {
            'type': 'weekday',
            'start_time': start_time,
            'end_time': end_time,
            'total_hours': total_hours,
            'paid_hours': paid_hours,
            'overtime_hours': overtime_hours,
            'total_pay': total_pay,
            'date': datetime.now().strftime("%Y-%m-%d")
        }
    
    def is_valid_24hour_time(self, time_str: str) -> bool:
        """Validate 24-hour time format"""
        try:
            parts = time_str.split(':')
            if len(parts) != 2:
                return False
            
            hour = int(parts[0])
            minute = int(parts[1])
            
            return 0 <= hour <= 23 and 0 <= minute <= 59
        except:
            return False
    
    def calculate_hours_between(self, start_time: str, end_time: str) -> float:
        """Calculate hours between two 24-hour times"""
        start_hour, start_min = map(int, start_time.split(':'))
        end_hour, end_min = map(int, end_time.split(':'))
        
        start_total_min = start_hour * 60 + start_min
        end_total_min = end_hour * 60 + end_min
        
        # Handle crossing midnight
        if end_total_min < start_total_min:
            end_total_min += 24 * 60
        
        return (end_total_min - start_total_min) / 60.0
    
    def format_time_confirmation(self, time_data: dict) -> str:
        """Format confirmation message for time entry"""
        
        msg = "📋 Please confirm:\n\n"
        msg += f"📅 Date: {datetime.strptime(time_data['date'], '%Y-%m-%d').strftime('%d %B %Y')}\n"
        
        if time_data['t
