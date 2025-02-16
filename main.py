import json
import os
import base64
import requests
import time
from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solana.rpc.types import TokenAccountOpts
from solana.rpc.commitment import Processed
from solders.transaction import VersionedTransaction
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders import message
from solders.signature import Signature

# Constants
CACHE_FILE = "wallets_cache.json"
SOLANA_MAINNET = "https://api.mainnet-beta.solana.com"
JUPITER_API_URL = "https://quote-api.jup.ag/v6"

client = Client(SOLANA_MAINNET)

# Generate a new Solana wallet
def generate_solana_wallet():
    keypair = Keypair()
    return str(keypair.public_key), keypair.secret_key.hex()

# Save wallets to a JSON file
def save_wallets(wallets, filename=CACHE_FILE):
    with open(filename, "w") as file:
        json.dump(wallets, file, indent=4)

# Load wallets from a JSON file
def load_wallets(filename=CACHE_FILE):
    if os.path.exists(filename):
        with open(filename, "r") as file:
            return json.load(file)
    return None

# Fetch token info from Jupiter API
def fetch_token_info(mint_address, client):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{mint_address}"
    headers = {'Accept': 'application/json'}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        data = response.json()
        
        # Check if data is not None and is a dictionary
        if not data or not isinstance(data, dict):
            print("Invalid or empty response from the API.")
            return None
        
        # Check if 'pairs' key exists and is a non-empty list
        if 'pairs' not in data or not isinstance(data['pairs'], list) or len(data['pairs']) == 0:
            print("No token information found in the response.")
            return None
        
        # Extract the first pair in the list
        pair = data['pairs'][0]
        
        # Extract details into a dictionary
        token_details = {
            "url": pair.get('url', 'Unknown'),
            "image_url": pair.get('info', {}).get('imageUrl', 'Unknown'),
            "header": pair.get('info', {}).get('header', 'Unknown'),  # Extract header
            "openGraph": pair.get('info', {}).get('openGraph', 'Unknown'),  # Extract openGraph
            "base_token_name": pair.get('baseToken', {}).get('name', 'Unknown'),
            "base_token_symbol": pair.get('baseToken', {}).get('symbol', 'Unknown'),
            "quote_token_symbol": pair.get('quoteToken', {}).get('symbol', 'Unknown'),
            "price_usd": pair.get('priceUsd', 'Unknown'),
            "price_native": pair.get('priceNative', 'Unknown'),
            "volume_24h": pair.get('volume', {}).get('h24', 'Unknown'),
            "liquidity_usd": pair.get('liquidity', {}).get('usd', 'Unknown'),
        }
        
        return token_details  # Return the extracted information

    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch token info: {e}")
        return None

# Fetch swap quote from Jupiter API
def get_swap_quote(input_mint, output_mint, amount_in_units, slippage_bps=50):
    url = f"{JUPITER_API_URL}/quote"
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": int(amount_in_units),  # Ensure the amount is in the token's smallest unit
        "slippageBps": slippage_bps,
        "onlyDirectRoutes": 'false',  # Allow multiple routes
        "asLegacyTransaction": 'false',  # Use versioned transactions
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print("Failed to fetch swap quote:", response.text)
        return None

# Execute swap using Jupiter API
def execute_swap(quote, wallet_keypair):
    url = f"{JUPITER_API_URL}/swap"
    payload = {
        "quoteResponse": quote,
        "userPublicKey": str(wallet_keypair.pubkey()),
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        swap_route = response.json()["swapTransaction"]

        raw_transaction = VersionedTransaction.from_bytes(base64.b64decode(swap_route))
        signature = wallet_keypair.sign_message(message.to_bytes_versioned(raw_transaction.message))

        signed_txn = VersionedTransaction.populate(raw_transaction.message, [signature])

        # Send the transaction
        opts = TxOpts(skip_preflight=False, preflight_commitment=Processed)
        result = client.send_raw_transaction(txn=bytes(signed_txn), opts=opts)

        transaction_id = json.loads(result.to_json())["result"]
        return {"transaction_id": transaction_id}

    except requests.exceptions.RequestException as e:
        print("Failed to execute swap:", e)
        return None
    except Exception as e:
        print("Error during transaction signing or sending:", e)
        return None
    
def sell_for_sol(token_mint_address, wallet_keypair, slippage_bps=50):
    # Fetch token info
    token_info = fetch_token_info(token_mint_address, client)
    if not token_info:
        print("Failed to fetch token info")
        return None

    # Fetch token balance
    token_balance = get_token_balance(client, str(wallet_keypair.pubkey()), token_mint_address)
    if token_balance is None:
        print("Failed to fetch token balance.")
        return None

    # Calculate the token value in SOL using price_native
    price_native = float(token_info.get("price_native", 0))
    if price_native == 0:
        print("Token price in SOL not found.")
        return None

    token_value_sol = token_balance * price_native
    print(f"\nToken Balance: {token_balance} tokens")
    print(f"Token Value in SOL: {token_value_sol:.6f} SOL")

    if token_balance == 0:
        print("You do not own any tokens of this type.")
        return None

    # Define the WSOL mint address
    wsol_mint_address = "So11111111111111111111111111111111111111112"

    # Fetch the swap quote
    quote = get_swap_quote(token_mint_address, wsol_mint_address, token_balance, slippage_bps)
    if not quote:
        print("Failed to fetch swap quote.")
        return None
    
    # Confirm swap
    confirm = input("\nDo you want to proceed with the swap? (Y/N): ").strip().lower()
    if confirm != 'y':
        print("Swap cancelled.")
        return None

    print("\nSwap quote received:")
    print(f"Input Amount: {quote['inAmount']} units")
    print(f"Estimated SOL to Receive: {int(quote['outAmount']) / 1e9} SOL")

    # Execute the swap
    swap_result = execute_swap(quote, wallet_keypair)
    if swap_result and "transaction_id" in swap_result:
        print("\nSwap executed successfully!")
        print(f"Transaction ID: {swap_result['transaction_id']}")
        print(f"Transaction sent: https://solscan.io/tx/{swap_result['transaction_id']}")
        return swap_result
    else:
        print("Swap failed or transaction ID not found.")
        return None
        
def get_token_value(token_mint_address, token_amount_owned, client):

    token_info = fetch_token_info(token_mint_address, client)
    if not token_info:
        print("Failed to fetch token info.")
        return None
    
    decimals = token_info.get("decimals")
    if decimals is None:
        print("Token decimals not found.")
        return None
    
    url = "https://api.jup.ag/price/v2"

    params = {
    "ids": "J4JbUQRaZMxdoQgY6oEHdkPttoLtZ1oKpBThic76pump",  
    "vsToken": "So11111111111111111111111111111111111111112" 
    }
    
    response = requests.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        token_data = data.get("data", {}).get(token_mint_address, {})

        token_price_in_sol = token_data.get("price", None)
        

        if token_price_in_sol is not None:
            token_amount_base_units = token_amount_owned / (10 ** decimals)


            return {
                "token_price_sol": token_price_in_sol,
                "decimals": decimals,
            }
        else:
            print(f"Price not found for token: {token_mint_address}")
            return None
    else:
        print(f"Error {response.status_code}: {response.text}")
        return None

# Get wallet balance
def get_wallet_balance(client, public_key):
    try:
        if isinstance(public_key, str):
            public_key = Pubkey.from_string(public_key)
        # Fetch the balance
        response = client.get_balance(public_key)
        
        balance_lamports = response.value

        balance_sol = balance_lamports / 1e9
        return balance_sol
    except Exception as e:
        print("Error fetching wallet balance:", e)
        return None
    
def get_token_balance(client, wallet_address, mint_address):
    try:
        time.sleep(1)
        wallet_pubkey = Pubkey.from_string(wallet_address)
        mint_pubkey = Pubkey.from_string(mint_address)

        token_accounts = client.get_token_accounts_by_owner(wallet_pubkey, TokenAccountOpts(mint=mint_pubkey))

        if token_accounts.value:
            token_account_pubkey = token_accounts.value[0].pubkey

            balance_response = client.get_token_account_balance(token_account_pubkey)
            raw_balance = int(balance_response.value.amount)
            
            # Convert raw balance to real value by dividing by 10^6
            real_balance = raw_balance / 10**6
            return real_balance
        else:
            print("No token account found for this mint address.")
            return 0
    except Exception as e:
        print(f"Error fetching token balance: {e}")
        return None
    
def get_wallet_details(wallet):
    return {
        "public_key": wallet["public_key"],
        "private_key": wallet["private_key"]
    }

def get_wallet_details_str(wallet):
    return (
        f"Wallet details:\n"
        f"Public Key: {wallet['public_key']}\n"
        f"Private Key: {wallet['private_key']}\n"
    )

# Main function
def get_total_token_balance(client, wallets, contract_address):
    """
    Calculate the total token balance across all wallets.
    """
    total_balance = 0
    for wallet in wallets:
        balance = get_token_balance(client, wallet["public_key"], contract_address)
        if balance is not None:
            total_balance += balance
        else:
            print(f"Failed to fetch token balance for wallet: {wallet['public_key']}")
    return total_balance


def display_wallet_details(wallets):
    """
    Display public and private keys of all wallets.
    """
    for wallet in wallets:
        print("\nWallet details:")
        print(f"Public Key: {wallet['public_key']}")
        print(f"Private Key: {wallet['private_key']}")


def display_token_info(token_info):
    """
    Display token information.
    """
    if token_info:
        print("Token information retrieved successfully:")
        print(f"URL: {token_info.get('url')}")
        print(f"Image URL: {token_info.get('image_url')}")
        print(f"Base Token Name: {token_info.get('base_token_name')}")
        print(f"Base Token Symbol: {token_info.get('base_token_symbol')}")
        print(f"Quote Token Symbol: {token_info.get('quote_token_symbol')}")
        print(f"Price (USD): {token_info.get('price_usd')}")
        print(f"Price (SOL): {token_info.get('price_native')}")
        print(f"24h Volume: {token_info.get('volume_24h')}")
        print(f"Liquidity (USD): {token_info.get('liquidity_usd')}")
        print(f"Website URL: {token_info.get('website_url')}")
    else:
        print("Failed to fetch token info.")


def execute_swap_flow(client, wallets, contract_address, sender_keypair):
    """
    Handle the swap flow, including fetching quotes, checking balances, and executing swaps.
    """
    amount_in_sol = float(input("Enter the amount of SOL to swap: "))
    sol_mint_address = "So11111111111111111111111111111111111111112"
    amount_in_units = int(amount_in_sol * (10 ** 9))
    quote = get_swap_quote(sol_mint_address, contract_address, amount_in_units)

    if quote:
        print("\nSwap quote received:")
        print(f"Input Amount: {quote['inAmount']} units")
        print("Swap quote received:", quote)

        # Check wallet balance
        wallet_balance = get_wallet_balance(client, wallets[0]["public_key"])
        if wallet_balance is None:
            print("Failed to fetch wallet balance.")
            return

        print(f"Wallet Balance: {wallet_balance} SOL")

        if wallet_balance < amount_in_sol:
            print("Insufficient SOL balance for the swap.")
            return

        confirm = input("\nDo you want to proceed with the swap? (Y/N): ").strip().lower()
        if confirm == 'y':
            swap_result = execute_swap(quote, sender_keypair)
            if swap_result and "transaction_id" in swap_result:
                print("Swap executed successfully! Transaction ID:", swap_result["transaction_id"])
                print(f"Transaction sent: https://solscan.io/tx/{swap_result['transaction_id']}")
            else:
                print("Swap failed or transaction ID not found.")
        else:
            print("Swap cancelled.")
    else:
        print("Failed to fetch swap quote.")

def get_total_holdings_in_sol(client, wallets, token_mint_address):
    """
    Calculate the total holdings of a token across all wallets and return the value in SOL.
    """
    total_balance = 0
    for wallet in wallets:
        balance = get_token_balance(client, wallet["public_key"], token_mint_address)
        if balance is not None:
            total_balance += balance
        else:
            print(f"Failed to fetch token balance for wallet: {wallet['public_key']}")

    # Fetch the token price in SOL
    token_info = fetch_token_info(token_mint_address, client)
    if not token_info:
        print("Failed to fetch token info.")
        return None

    price_native = float(token_info.get("price_native", 0))
    if price_native == 0:
        print("Token price in SOL not found.")
        return None

    # Calculate total holdings in SOL
    total_holdings_sol = total_balance * price_native
    return total_holdings_sol

def sell_all_for_sol(token_mint_address, wallets, slippage_bps=50):
    results = {}

    for wallet in wallets:
        try:
            # Extract wallet details
            public_key = wallet["public_key"]
            private_key = wallet["private_key"]

            # Create a Keypair object from the private key
            keypair = Keypair.from_bytes(bytes.fromhex(private_key))

            # Sell the token for SOL
            print(f"Selling tokens for wallet: {public_key}")
            result = sell_for_sol(token_mint_address, keypair, slippage_bps)

            if result:
                results[public_key] = {
                    "status": "success",
                    "transaction_id": result.get("transaction_id"),
                }
            else:
                results[public_key] = {
                    "status": "failed",
                    "error": "Failed to execute sell_for_sol",
                }

        except Exception as e:
            print(f"Error selling tokens for wallet {public_key}: {e}")
            results[public_key] = {
                "status": "failed",
                "error": str(e),
            }

    return results

def main():

    # Load wallets from the cache file
    wallets = load_wallets()

    if wallets is None:
        num_wallets = int(input("Enter the number of wallets to create: "))
        wallets = [{"public_key": generate_solana_wallet()[0], "private_key": generate_solana_wallet()[1]} for _ in range(num_wallets)]
        save_wallets(wallets)
        print(f"Created {num_wallets} new wallets and saved to cache.")
    else:
        print(f"Loaded {len(wallets)} wallets from cache.")
        
        if wallets:
            # Display wallet details
            display_wallet_details(wallets)
            contract_address = input("Enter the contract address (token mint address): ")
            token_info = fetch_token_info(contract_address, client)

            # Display token information
            display_token_info(token_info)

            # Sell tokens for SOL for each wallet
            for wallet in wallets:
                sender_keypair = Keypair.from_bytes(bytes.fromhex(wallet["private_key"]))
                sell_for_sol(contract_address, sender_keypair)

            # Get total token balance across all wallets
            price_native = float(token_info.get('price_native', 0))
            
            total_token_balance = get_total_token_balance(client, wallets, contract_address) * price_native
            if total_token_balance is None:
                print("Failed to fetch total token balance.")
                return

            print(f"\nTotal Token Balance: {total_token_balance} SOL")


            # Execute swap flow
            execute_swap_flow(client, wallets, contract_address, sender_keypair)


if __name__ == "__main__":
    main()
