import asyncio
from shared import users, db, crypto

def main():
    # Simulate resolution
    issuer = "https://accounts.google.com"
    subject = "test-subject-123"
    email = "test@example.com"
    
    caller = users.resolve(issuer, subject, email)
    print("Resolved caller:", caller)
    
    pan = users.set_pan(caller.user_id, "ABCDE1234F")
    print("Set PAN:", pan)
    
    caller2 = users.resolve(issuer, subject, email)
    print("Resolved caller 2:", caller2)
    
if __name__ == "__main__":
    main()
