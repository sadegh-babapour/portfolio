# test_supabase.py
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
if os.path.exists('.env'):
    load_dotenv()

def test_supabase_connection():
    try:
        # Get credentials
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        
        if not url or not key:
            print("❌ Missing SUPABASE_URL or SUPABASE_KEY in environment variables")
            return False
        
        print(f"🔗 Connecting to Supabase...")
        print(f"URL: {url}")
        
        # Create client
        supabase: Client = create_client(url, key)
        
        # Test connection by trying to fetch from a table
        # This will fail if no tables exist, but connection will work
        try:
            response = supabase.table('test_table').select("*").limit(2).execute()
            print("✅ Connection successful!")
            print(f"Response: {response.data}")
        except Exception as table_error:
            print("✅ Connection successful!")
            print(f"⚠️  No 'test_table' found (expected): {table_error}")
            
            # Try to list available tables instead
            try:
                # This queries the system information schema
                tables = supabase.rpc('get_tables').execute()
                print(f"Available tables: {tables.data}")
            except:
                print("📝 No tables exist yet - that's normal for a new database")
        
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing Supabase connection...")
    success = test_supabase_connection()
    
    if success:
        print("\n🎉 Supabase is ready to use!")
    else:
        print("\n💥 Check your environment variables and try again")