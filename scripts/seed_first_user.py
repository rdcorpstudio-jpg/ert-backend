"""
One-time script to get a password hash for your first user.
Run from ERT-Backend folder, then add the user in Railway Database tab.

Usage:
  cd C:\ERT-Backend
  python scripts/seed_first_user.py your@email.com YourPassword "Your Name" manager
"""
import sys
import os

# Allow importing app from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.security import hash_password

def main():
    if len(sys.argv) < 5:
        print("Usage: python scripts/seed_first_user.py <email> <password> <name> <role>")
        print("Example: python scripts/seed_first_user.py admin@example.com mypassword \"Admin\" manager")
        print("Roles: sale, account, pack, manager")
        sys.exit(1)
    email = sys.argv[1]
    password = sys.argv[2]
    name = sys.argv[3]
    role = sys.argv[4]
    if role not in ("sale", "account", "pack", "manager"):
        print("Role must be: sale, account, pack, manager")
        sys.exit(1)
    h = hash_password(password)
    print("\n--- Copy these values into Railway Database -> users -> + Row ---\n")
    print("name:      ", repr(name))
    print("email:     ", repr(email))
    print("password_hash (copy this ENTIRE line, no truncation):")
    print(h)
    print("role:      ", repr(role))
    print("is_active: 1  (or true)")
    print("\nLeave 'id' empty so it auto-generates.")
    print("Hash length:", len(h), "- if DB shows fewer chars, the hash was truncated.\n")

if __name__ == "__main__":
    main()
