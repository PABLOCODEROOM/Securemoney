#!/usr/bin/env python
"""
Quick test to check login speed and OTP generation.
"""
import time
import sys
sys.path.insert(0, '.')

from app.models import authenticate_user, create_otp
from app.config import get_config

def test_authentication_speed():
    """Test how long authentication takes."""
    print("Testing authentication speed...")
    
    start = time.time()
    try:
        user = authenticate_user("Esau.magaro@securemoney.tz", "Esau.magaro")
        auth_time = time.time() - start
        print(f"✓ Authentication successful in {auth_time:.3f} seconds")
        print(f"  User: {user}")
        
        if user:
            # Test OTP generation
            start = time.time()
            otp = create_otp(user['user_id'])
            otp_time = time.time() - start
            print(f"✓ OTP generated in {otp_time:.3f} seconds")
            print(f"  OTP: {otp}")
            
            total_time = auth_time + otp_time
            print(f"\nTotal time: {total_time:.3f} seconds")
            
            if total_time > 3:
                print("\n⚠ WARNING: Total time is slow (>3 seconds)")
                print("This may be due to:")
                print("  1. PBKDF2 password hashing (600,000 iterations)")
                print("  2. Database connection overhead")
                print("  3. Network latency to MySQL server")
            else:
                print("\n✓ Performance looks good!")
                
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_authentication_speed()
