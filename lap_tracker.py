#!/usr/bin/env python3
"""
6-Urenloop Lap Tracker
A standalone Python application for tracking laps in real-time.

Requirements:
- Python 3 with tkinter support (install with: brew install python-tk)
- Virtual environment with packages: pip install supabase pandas python-dotenv

Setup:
1. Create virtual environment: python3 -m venv .venv
2. Activate it: source .venv/bin/activate
3. Install packages: pip install supabase pandas python-dotenv
4. Create a .env file with SUPABASE_URL and SUPABASE_KEY

Usage:
1. Activate virtual environment: source .venv/bin/activate
2. Run the script: python lap_tracker.py
3. Paste or type class names to add laps
4. Press Enter to submit
5. Press Escape to exit
"""

import tkinter as tk
from tkinter import messagebox, font
import pandas as pd
import csv
from datetime import datetime
import os
import sys
from typing import Optional
import threading
import time

# Supabase imports
try:
    from supabase import create_client, Client
    from dotenv import load_dotenv
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("Warning: supabase or python-dotenv not installed. Only CSV logging will work.")
    print("Install with: pip install supabase python-dotenv")

class LapTracker:
    def __init__(self):
        self.root = tk.Tk()
        self.processing = False  # Prevent duplicate processing
        self.last_processed_text = ""  # Track last processed text
        self.recent_scans = {}  # Track recent scans by class with timestamps
        self.setup_window()
        self.load_classes_mapping()
        self.setup_supabase()
        self.setup_csv()
        self.setup_ui()
        self.setup_bindings()
        
    def setup_window(self):
        """Configure the main window"""
        self.root.title("6-Urenloop Lap Tracker")
        self.root.configure(bg='black')
        
        # Make fullscreen
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        
        # Get screen dimensions
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
    
    def load_classes_mapping(self):
        """Load class name to ID mapping from CSV file and barcode mapping"""
        self.classes_dict = {}
        self.barcode_dict = {}
        
        try:
            # Load class name to ID mapping from classes_rows.csv
            if os.path.exists("classes_rows.csv"):
                with open("classes_rows.csv", 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        class_name = row['name'].strip()
                        class_id = row['id'].strip()
                        self.classes_dict[class_name] = class_id
                
                print(f"✅ Loaded {len(self.classes_dict)} classes from classes_rows.csv")
                
                # Print first few classes for verification
                if len(self.classes_dict) > 0:
                    print("📚 Sample classes loaded:")
                    for i, (name, id) in enumerate(list(self.classes_dict.items())[:5]):
                        print(f"   - {name}: {id}")
                    if len(self.classes_dict) > 5:
                        print(f"   ... and {len(self.classes_dict) - 5} more")
            else:
                print("⚠️  classes_rows.csv not found. Will use Supabase lookup instead.")
            
            # Load barcode to class mapping from titularis CSV
            barcode_file = "titularis-klassen-barcode-jaar-groep(titulars-klassen).csv"
            if os.path.exists(barcode_file):
                # Try different encodings
                for encoding in ['utf-8', 'latin-1', 'cp1252']:
                    try:
                        with open(barcode_file, 'r', encoding=encoding) as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                barcode = row['barcode'].strip()
                                class_name = row['Klas'].strip()
                                self.barcode_dict[barcode] = class_name
                        print(f"✅ Used encoding: {encoding}")
                        break
                    except UnicodeDecodeError:
                        continue
                
                print(f"✅ Loaded {len(self.barcode_dict)} barcodes from {barcode_file}")
                
                # Print first few barcodes for verification
                if len(self.barcode_dict) > 0:
                    print("🏷️  Sample barcodes loaded:")
                    for i, (barcode, class_name) in enumerate(list(self.barcode_dict.items())[:5]):
                        print(f"   - {barcode} → {class_name}")
                    if len(self.barcode_dict) > 5:
                        print(f"   ... and {len(self.barcode_dict) - 5} more")
            else:
                print("⚠️  Barcode mapping file not found. Only class names will work.")
                
        except Exception as e:
            print(f"❌ Error loading mappings: {e}")
            print("⚠️  Will fallback to Supabase lookup")
        
    def setup_supabase(self):
        """Initialize Supabase client and authenticate"""
        self.supabase: Optional[Client] = None
        
        if not SUPABASE_AVAILABLE:
            return
            
        try:
            # Load environment variables
            load_dotenv()
            
            url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
            
            # Try service role key first (bypasses RLS)
            service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            if service_key:
                self.supabase = create_client(url, service_key)
                print("✅ Supabase connection established with service role key (RLS bypassed)")
                return
            
            # Fall back to regular key with user authentication
            key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
            
            if not url or not key:
                print("Warning: SUPABASE_URL or SUPABASE_KEY not found in environment variables")
                return
                
            self.supabase = create_client(url, key)
            print("✅ Supabase connection established")
            
            # Try to authenticate with user credentials
            self.authenticate_user()
            
        except Exception as e:
            print(f"❌ Failed to connect to Supabase: {e}")
            self.supabase = None
    
    def authenticate_user(self):
        """Authenticate user with Supabase to bypass RLS"""
        if not self.supabase:
            return
            
        try:
            user_email = os.getenv("SUPABASE_USER_EMAIL")
            user_password = os.getenv("SUPABASE_USER_PASSWORD")
            
            if not user_email or not user_password:
                print("⚠️  No user credentials found in .env file. RLS policies may block database writes.")
                print("💡 Add SUPABASE_USER_EMAIL and SUPABASE_USER_PASSWORD to .env file")
                return
                
            # Sign in with email and password
            auth_response = self.supabase.auth.sign_in_with_password({
                "email": user_email,
                "password": user_password
            })
            
            if auth_response.user:
                print(f"✅ Authenticated as user: {auth_response.user.email}")
                print("🔓 RLS policies should now allow database operations")
            else:
                print("❌ Authentication failed")
                
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            print("⚠️  Will proceed without authentication - database writes may fail due to RLS")
    
    def setup_csv(self):
        """Setup CSV logging"""
        self.csv_filename = f"laps_{datetime.now().strftime('%Y%m%d')}.csv"
        
        # Create CSV file with headers if it doesn't exist
        if not os.path.exists(self.csv_filename):
            with open(self.csv_filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'class_name', 'class_id', 'success', 'scan_type'])
                
        print(f"📁 CSV logging to: {self.csv_filename}")
    
    def setup_ui(self):
        """Create the user interface"""
        # Main container
        self.main_frame = tk.Frame(self.root, bg='black')
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_font = font.Font(family="Arial", size=48, weight="bold")
        self.title_label = tk.Label(
            self.main_frame,
            text="6-URENLOOP LAP TRACKER",
            font=title_font,
            fg='white',
            bg='black'
        )
        self.title_label.pack(pady=50)
        
        # Instructions
        instruction_font = font.Font(family="Arial", size=24)
        self.instruction_label = tk.Label(
            self.main_frame,
            text="Plak barcode of klasnaam - automatische verwerking\nDruk Escape om af te sluiten",
            font=instruction_font,
            fg='#cccccc',
            bg='black',
            justify=tk.CENTER
        )
        self.instruction_label.pack(pady=20)
        
        # Input field
        input_font = font.Font(family="Arial", size=36)
        self.input_var = tk.StringVar()
        self.input_entry = tk.Entry(
            self.main_frame,
            textvariable=self.input_var,
            font=input_font,
            justify=tk.CENTER,
            width=20,
            bg='white',
            fg='black',
            insertbackground='black'
        )
        self.input_entry.pack(pady=30)
        self.input_entry.focus_set()
        
        # Status label
        status_font = font.Font(family="Arial", size=18)
        self.status_label = tk.Label(
            self.main_frame,
            text="Klaar voor invoer...",
            font=status_font,
            fg='#888888',
            bg='black'
        )
        self.status_label.pack(pady=20)
        
        # Connection status
        if self.supabase:
            # Check if user is authenticated
            try:
                user = self.supabase.auth.get_user()
                if user.user:
                    supabase_status = f"🟢 Supabase verbonden (🔓 {user.user.email})"
                else:
                    supabase_status = "🟢 Supabase verbonden (⚠️ niet ingelogd)"
            except:
                supabase_status = "🟢 Supabase verbonden"
        else:
            supabase_status = "🔴 Alleen CSV logging"
            
        classes_count = len(getattr(self, 'classes_dict', {}))
        barcodes_count = len(getattr(self, 'barcode_dict', {}))
        classes_status = f"📚 {classes_count} klassen, 🏷️ {barcodes_count} barcodes geladen"
        connection_text = f"{supabase_status} | {classes_status}"
        
        self.connection_label = tk.Label(
            self.main_frame,
            text=connection_text,
            font=font.Font(family="Arial", size=14),
            fg='#666666',
            bg='black'
        )
        self.connection_label.pack(side=tk.BOTTOM, pady=20)
        
    def setup_bindings(self):
        """Setup keyboard bindings"""
        self.root.bind('<Return>', self.process_lap)
        self.root.bind('<Escape>', self.quit_app)
        self.root.bind('<Control-c>', self.quit_app)
        
        # Make sure input field stays focused
        self.input_entry.bind('<FocusOut>', lambda e: self.input_entry.focus_set())
        
        # Auto-submit on paste or text change using KeyRelease
        self.input_entry.bind('<KeyRelease>', self.on_text_change)
        
        # Also bind paste events explicitly
        self.input_entry.bind('<Control-v>', self.on_paste)
        self.input_entry.bind('<Command-v>', self.on_paste)  # macOS
        self.input_entry.bind('<<Paste>>', self.on_paste)
    
    def show_success_screen(self, class_name: str):
        """Show green success screen for 1 second"""
        # Hide main frame
        self.main_frame.pack_forget()
        
        # Create success frame
        success_frame = tk.Frame(self.root, bg='#00ff00')
        success_frame.pack(fill=tk.BOTH, expand=True)
        
        # Success message
        success_font = font.Font(family="Arial", size=72, weight="bold")
        success_label = tk.Label(
            success_frame,
            text=f"LAP TOEGEVOEGD!\n{class_name}",
            font=success_font,
            fg='black',
            bg='#00ff00',
            justify=tk.CENTER
        )
        success_label.pack(expand=True)
        
        # Update display
        self.root.update()
        
        # Wait 1 second then restore main frame
        def restore_main():
            time.sleep(1)
            success_frame.destroy()
            self.main_frame.pack(fill=tk.BOTH, expand=True)
            self.input_var.set("")  # Clear input
            self.input_entry.focus_set()  # Restore focus
            self.status_label.config(text="Klaar voor invoer...")
            
            # Reset processing flag and clear last processed text after success screen
            self.processing = False
            self.last_processed_text = ""
            
        # Run in thread to not block UI
        threading.Thread(target=restore_main, daemon=True).start()
    
    def on_text_change(self, event=None):
        """Handle text changes in input field - auto-submit when text is entered"""
        # Small delay to allow for complete paste operation
        self.root.after(100, self.check_and_process)
    
    def on_paste(self, event=None):
        """Handle paste events explicitly"""
        # Delay processing to allow paste to complete
        self.root.after(200, self.check_and_process)
        
    def check_and_process(self):
        """Check if there's text and process it automatically"""
        text = self.input_var.get().strip()
        
        # Prevent duplicate processing
        if self.processing:
            return
            
        # Don't process if it's the same text we just processed
        if text == self.last_processed_text:
            return
            
        if text and len(text) > 0:
            # Only auto-process if it looks like a class name (has some content)
            self.process_lap()
    
    def get_class_id_by_name(self, input_text: str) -> Optional[str]:
        """Get class ID by input (barcode or class name) - try barcode mapping first, then class name mapping"""
        input_text = input_text.strip()
        final_class_name = input_text
        
        # First check if input is a barcode
        if hasattr(self, 'barcode_dict') and input_text in self.barcode_dict:
            final_class_name = self.barcode_dict[input_text]
            print(f"🏷️  Barcode '{input_text}' mapped to class '{final_class_name}'")
        
        # Now try to find class ID for the final class name
        if hasattr(self, 'classes_dict') and final_class_name in self.classes_dict:
            print(f"✅ Found class '{final_class_name}' in local mapping")
            return self.classes_dict[final_class_name]
        
        # Fallback to Supabase if not found locally
        if not self.supabase:
            print(f"❌ Class '{final_class_name}' not found in local mapping and no Supabase connection")
            return None
            
        try:
            print(f"🔍 Class '{final_class_name}' not in local mapping, trying Supabase...")
            response = self.supabase.table("classes").select("id").eq("name", final_class_name).execute()
            
            if response.data and len(response.data) > 0:
                class_id = response.data[0]["id"]
                print(f"✅ Found class '{final_class_name}' in Supabase")
                # Optionally add to local dict for future use
                self.classes_dict[final_class_name] = class_id
                return class_id
            else:
                print(f"❌ Class '{final_class_name}' not found in Supabase either")
                return None
                
        except Exception as e:
            print(f"❌ Error fetching class ID from Supabase: {e}")
            return None
    
    def add_lap_to_supabase(self, class_id: str) -> bool:
        """Add a lap to Supabase database"""
        if not self.supabase:
            return False
            
        try:
            lap_data = {
                "class_id": class_id,
                "timestamp": datetime.now().isoformat()
            }
            
            response = self.supabase.table("laps").insert(lap_data).execute()
            
            if response.data:
                print(f"✅ Lap added to Supabase for class_id: {class_id}")
                return True
            else:
                print(f"❌ Failed to add lap to Supabase")
                return False
                
        except Exception as e:
            print(f"❌ Error adding lap to Supabase: {e}")
            return False
    
    def add_lap_to_csv(self, class_name: str, class_id: Optional[str], success: bool, is_duplicate: bool = False):
        """Add lap entry to CSV file"""
        try:
            with open(self.csv_filename, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    class_name.strip(),
                    class_id or "UNKNOWN",
                    success,
                    "DUPLICATE_SCAN" if is_duplicate else "NORMAL"
                ])
            status = "duplicate scan" if is_duplicate else "lap"
            print(f"📁 {status.title()} logged to CSV: {class_name}")
            
        except Exception as e:
            print(f"❌ Error writing to CSV: {e}")
    
    def is_recent_scan(self, class_name: str) -> bool:
        """Check if this class was scanned within the last 30 seconds"""
        now = datetime.now()
        if class_name in self.recent_scans:
            last_scan_time = self.recent_scans[class_name]
            time_diff = (now - last_scan_time).total_seconds()
            return time_diff < 30  # Less than 30 seconds
        return False
    
    def update_recent_scan(self, class_name: str):
        """Update the timestamp for this class's most recent scan"""
        self.recent_scans[class_name] = datetime.now()
    
    def process_lap(self, event=None):
        """Process a lap entry"""
        input_text = self.input_var.get().strip()
        
        if not input_text:
            return
        
        # Prevent duplicate processing
        if self.processing:
            return
            
        # Don't process if it's the same text we just processed
        if input_text == self.last_processed_text:
            return
            
        self.processing = True
        self.last_processed_text = input_text
        self.status_label.config(text="Verwerken...")
        self.root.update()
        
        # Resolve barcode to class name if needed
        display_name = input_text
        if hasattr(self, 'barcode_dict') and input_text in self.barcode_dict:
            display_name = self.barcode_dict[input_text]
        
        # Check if this is a recent scan (within 1 minute)
        is_duplicate = self.is_recent_scan(display_name)
        
        # Get class ID
        class_id = self.get_class_id_by_name(input_text)
        success = False
        
        # Only add to Supabase if class found AND not a duplicate scan
        if class_id and not is_duplicate:
            success = self.add_lap_to_supabase(class_id)
            self.update_recent_scan(display_name)  # Update timestamp for successful scans
            print(f"✅ Lap processed for '{display_name}'")
        elif class_id and is_duplicate:
            print(f"⏰ Duplicate scan for '{display_name}' within 1 minute - skipping Supabase, logging to CSV only")
        else:
            print(f"⚠️  Input '{input_text}' (class: '{display_name}') not found, logging to CSV only")
        
        # Always log to CSV with both input and resolved class name
        csv_name = f"{input_text} → {display_name}" if input_text != display_name else display_name
        self.add_lap_to_csv(csv_name, class_id, success, is_duplicate)
        
        # Show success screen with appropriate message
        if is_duplicate:
            self.show_success_screen(f"{display_name}\n(Duplicate - niet geteld)")
        else:
            self.show_success_screen(display_name)
    
    def quit_app(self, event=None):
        """Quit the application"""
        self.root.quit()
        self.root.destroy()
        sys.exit(0)
    
    def run(self):
        """Start the application"""
        print("🚀 Starting 6-Urenloop Lap Tracker...")
        print("📝 Instructions:")
        print("   - Paste barcode or class name - automatic processing (no Enter needed!)")
        print("   - Or type barcode/class name and press Enter")
        print("   - Press Escape to quit")
        print("   - Ctrl+C to force quit")
        print("")
        print("💡 Tip: Barcodes and class names are loaded from CSV files for fast lookup")
        
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            print("\n👋 Lap Tracker stopped by user")
            self.quit_app()

def main():
    """Main entry point"""
    try:
        app = LapTracker()
        app.run()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()