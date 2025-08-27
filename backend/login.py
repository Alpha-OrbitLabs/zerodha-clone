from kiteconnect import KiteConnect
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN_FILE = os.getenv("ACCESS_TOKEN_FILE")

kite = KiteConnect(api_key=API_KEY)

# Step 1: Get login URL
print("Login URL:", kite.login_url())

# Step 2: After login, you'll get a 'request_token' in the URL
request_token = input("Enter the request_token from URL: ")

# Step 3: Generate access token
data = kite.generate_session(request_token, api_secret=API_SECRET)
access_token = data["access_token"]

# Save access token to file
with open(ACCESS_TOKEN_FILE, "w") as f:
    f.write(access_token)

print("Access token saved to", ACCESS_TOKEN_FILE)
