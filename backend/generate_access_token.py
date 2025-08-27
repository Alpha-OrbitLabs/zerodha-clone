from kiteconnect import KiteConnect

API_KEY = "2ocqgjbjp3vnw58v"       # apna API Key
API_SECRET = "zxfgh18kv9pysurtekz8v17ii5w57e83" # apna API Secret
REQUEST_TOKEN = "FwdBGQ5stSgtRH5yzzrpYNxZYnMRbxaW"  # jo tumhe mila hai

kite = KiteConnect(api_key=API_KEY)

# Request token exchange karke access token lena
data = kite.generate_session(REQUEST_TOKEN, api_secret=API_SECRET)
print("Access Token:", data["access_token"])

# Access token ko ek file me save kar do
with open("access_token.txt", "w") as f:
    f.write(data["access_token"])
