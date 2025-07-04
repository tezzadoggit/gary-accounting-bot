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
        self.ADMIN_PHONE = "+447831971523"  # Admin (Tim) phone number
        
        # Initialize services
        self.setup_google_sheets()
        self.setup_twilio()
        
        # Store pending confirmations (in production, use database)
        self.pending_confirmations = {}
        
        # Test connections on startup
        self.test_connections()
    
    def test_connections(self):
        """Test all connections on startup"""
        print("\n🔧 Testing connections...")
        
        # Test Google Sheets
        try:
            values = self.paye_sheet.get('A1:C1')
            print(f"✅ Google Sheets: Connected to {self.spreadsheet.title}")
            print(f"   PAYE Tracker has {len(self.paye_sheet.get_all_values())} rows")
        except Exception as e:
            print(f"❌ Google Sheets: {e}")
        
        # Test Twilio
        try:
            if self.twilio_client and self.twilio_number:
                print(f"✅ Twilio: Connected with number {self.twilio_number}")
            else:
                print("❌ Twilio: Missing credentials")
        except Exception as e:
            print(f"❌ Twilio: {e}")
    
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
    
    def is_authorized(self, phone_number: str) -> bool:
        """Check if phone number is authorized"""
        return phone_number in [self.GARY_PHONE, self.ADMIN_PHONE]
    
    def is_admin(self, phone_number: str) -> bool:
        """Check if phone number is admin"""
        return phone_number == self.ADMIN_PHONE
    
    def process_message(self, message: str, from_number: str) -> str:
        """Main message processing logic"""
        
        # Check authorization
        if not self.is_authorized(from_number):
            return "Sorry, this bot is only for authorized users."
        
        message = message.lower().strip()
        
        # Admin commands
        if self.is_admin(from_number):
            if message.startswith('admin'):
                return self.handle_admin_command(message, from_number)
        
        # Handle confirmations
        if message in ['yes', 'y', 'confirm', 'ok']:
            return self.handle_confirmation(from_number, True)
        elif message in ['no', 'n', 'cancel']:
            return self.handle_confirmation(from_number, False)
        
        # Handle time messages
        if self.is_time_message(message):
            return self.handle_time_request(message, from_number)
        elif message in ['help', 'status']:
            return self.help_message(from_number)
        else:
            return ("⏰ Send your hours: 'worked 7:30 till 17:00'\n"
                   "📱 Or try: 'worked normal day'\n"
                   "❓ Send 'help' for more commands")
    
    def handle_admin_command(self, message: str, from_number: str) -> str:
        """Handle admin-specific commands"""
        parts = message.split()
        
        if len(parts) == 1 or parts[1] == 'help':
            return ("👨‍💼 Admin Commands:\n\n"
                   "• 'admin status' - System status\n"
                   "• 'admin stats' - Usage statistics\n"
                   "• 'admin test' - Test connections\n"
                   "• 'admin clear' - Clear pending confirmations\n"
                   "• 'admin last' - Show last 5 entries")
        
        elif parts[1] == 'status':
            pending_count = len(self.pending_confirmations)
            return (f"🤖 Bot Status:\n"
                   f"• Gary's phone: {self.GARY_PHONE}\n"
                   f"• Admin phone: {self.ADMIN_PHONE}\n"
                   f"• Pending confirmations: {pending_count}\n"
                   f"• Sheet connected: {'✅' if hasattr(self, 'paye_sheet') else '❌'}")
        
        elif parts[1] == 'stats':
            try:
                all_values = self.paye_sheet.get_all_values()
                total_entries = len(all_values) - 1  # Minus header
                return f"📊 Stats:\n• Total entries: {total_entries}\n• Last updated: {all_values[-1][0] if total_entries > 0 else 'Never'}"
            except:
                return "❌ Error fetching stats"
        
        elif parts[1] == 'test':
            self.test_connections()
            return "✅ Connection test complete. Check logs for details."
        
        elif parts[1] == 'clear':
            self.pending_confirmations.clear()
            return "✅ Cleared all pending confirmations"
        
        elif parts[1] == 'last':
            try:
                all_values = self.paye_sheet.get_all_values()
                if len(all_values) <= 1:
                    return "📋 No entries found"
                
                msg = "📋 Last 5 entries:\n\n"
                for row in all_values[-5:]:
                    if row[0] != 'Date':  # Skip header if present
                        msg += f"• {row[0]}: {row[1]} - {row[2]}\n"
                return msg
            except:
                return "❌ Error fetching entries"
        
        return "❓ Unknown admin command. Try 'admin help'"
    
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
        
        if time_data['type'] == 'weekend':
            msg += f"🗓️ Weekend shift: {time_data['paid_hours']:.1f} hours\n"
            msg += f"💰 Pay: £{time_data['total_pay']:.2f}\n"
        else:
            msg += f"⏰ Hours: {time_data['start_time']} to {time_data['end_time']}\n"
            msg += f"📊 Total: {time_data['total_hours']:.1f}h, Paid: {time_data['paid_hours']:.1f}h"
            
            if time_data['total_hours'] > 6:
                msg += " (lunch deducted)"
            msg += "\n"
            
            if time_data['overtime_hours'] > 0:
                regular_pay = self.DAILY_RATE
                overtime_pay = time_data['overtime_hours'] * self.OVERTIME_RATE
                msg += f"📋 Regular: £{regular_pay:.2f}\n"
                msg += f"⏰ Overtime: {time_data['overtime_hours']:.1f}h = £{overtime_pay:.2f}\n"
                msg += f"💰 Total pay: £{time_data['total_pay']:.2f}\n"
            else:
                msg += f"💰 Normal day pay: £{time_data['total_pay']:.2f}\n"
        
        msg += "\nReply 'YES' to log this, or 'NO' to cancel"
        
        return msg
    
    def handle_confirmation(self, from_number: str, confirmed: bool) -> str:
        """Handle Gary's confirmation response"""
        
        if from_number not in self.pending_confirmations:
            return "No pending confirmation found. Send your work hours first!"
        
        pending = self.pending_confirmations[from_number]
        
        if not confirmed:
            # Gary cancelled
            del self.pending_confirmations[from_number]
            return "❌ Cancelled. Send your work hours again when ready."
        
        # Gary confirmed - process the action
        if pending['type'] == 'time_entry':
            result = self.log_time_entry(pending['data'])
            del self.pending_confirmations[from_number]
            
            if result:
                time_data = pending['data']
                if time_data['overtime_hours'] > 0:
                    return f"✅ Logged! {time_data['overtime_hours']:.1f} hour overtime today. Thanks Gary! 👍"
                elif time_data['type'] == 'weekend':
                    return f"✅ Weekend shift logged. Thanks Gary! 👍"
                else:
                    return f"✅ Normal day logged. Thanks Gary! 👍"
            else:
                return "❌ Error logging entry. Please try again or contact Tim."
        
        return "Unknown confirmation type."
    
    def log_time_entry(self, time_data: dict) -> bool:
        """Log confirmed time entry to Google Sheets"""
        try:
            # Refresh the sheet connection in case it timed out
            try:
                self.paye_sheet.get_all_values()
            except Exception:
                # Reconnect if needed
                self.setup_google_sheets()
            
            # Find the correct row to insert - look for first empty or formula row
            all_values = self.paye_sheet.get_all_values()
            next_row = len(all_values) + 1  # Default to end
            
            # Find first row where column A (date) is empty or starts with "-"
            for i, row in enumerate(all_values[1:], start=2):  # Skip header
                if i > 10 and (not row[0] or row[0].startswith('-')):
                    next_row = i
                    break
            
            # Log only the 3 essential fields - let sheet calculate the rest
            row_data = [
                time_data['date'],
                time_data['start_time'],
                time_data['end_time']
            ]
            
            # Write to the specific row
            range_name = f'A{next_row}:C{next_row}'
            self.paye_sheet.update(range_name, [row_data])
            
            print(f"✅ Logged time entry at row {next_row}: {time_data['date']} {time_data['start_time']}-{time_data['end_time']}")
            return True
            
        except Exception as e:
            print(f"❌ Error logging time entry: {e}")
            # Try one reconnection attempt
            try:
                self.setup_google_sheets()
                self.paye_sheet.append_row(row_data)
                print("✅ Logged after reconnection")
                return True
            except:
                return False
    
    def help_message(self, from_number: str) -> str:
        """General help message"""
        msg = ("🤖 Gary's Accounting Bot\n\n"
               "📱 Commands:\n"
               "• 'worked 7:30 till 17:00' - log hours\n"
               "• 'worked normal day' - standard day\n"
               "• 'worked 8:00 till 13:00 Saturday' - weekend\n"
               "• 'status' - help\n\n"
               "⏰ Always use 24-hour time (17:00 not 5pm)\n"
               "✅ I'll always confirm before saving anything!")
        
        # Add admin help hint
        if self.is_admin(from_number):
            msg += "\n\n👨‍💼 Type 'admin help' for admin commands"
        
        return msg

# Initialize the bot
gary_bot = GaryBot()

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming WhatsApp messages from Twilio"""
    
    try:
        # Get message details
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '').replace('whatsapp:', '')
        
        print(f"📱 Message from {from_number}: {incoming_msg}")
        
        # Process message with Gary's bot
        response_text = gary_bot.process_message(incoming_msg, from_number)
        
        # Send response via Twilio
        resp = MessagingResponse()
        resp.message(response_text)
        
        print(f"🤖 Response: {response_text}")
        
        return str(resp)
        
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        
        # Send error message
        resp = MessagingResponse()
        resp.message("Sorry, there was an error processing your message. Please try again or contact Tim.")
        
        return str(resp)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "bot": "Gary's Accounting Bot"}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
