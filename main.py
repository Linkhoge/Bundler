import json
import os
import base64
import requests
from solana.rpc.api import Client
from solana.rpc.types import TxOpts
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
    url = f"https://api.jup.ag/tokens/v1/token/{mint_address}"
    headers = {'Accept': 'application/json'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
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
        "wrapAndUnwrapSol": True,
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
        client = Client(SOLANA_MAINNET)
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

# Main function
def main():
    client = Client(SOLANA_MAINNET)

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
        print("\nFirst wallet details:")
        print(f"Public Key: {wallets[0]['public_key']}")
        print(f"Private Key: {wallets[0]['private_key']}")

        sender_keypair = Keypair.from_bytes(bytes.fromhex(wallets[0]["private_key"]))
        print("Sender Public Key:", sender_keypair.pubkey)

        # Fetch token info
        contract_address = input("Enter the contract address (token mint address): ")
        token_info = fetch_token_info(contract_address, client)

        if token_info:
            print("\nToken Information:")
            print(f"Name: {token_info.get('name')}")
            print(f"Symbol: ${token_info.get('symbol')}")
            print(f"Decimals: {token_info.get('decimals')}")
            print(f"Mint Address: {token_info.get('address')}")
            print(f"Logo URL: {token_info.get('logoURI')}")

        # Fetch swap quote
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
                    print(f"Transaction sent: https://explorer.solana.com/tx/{swap_result['transaction_id']}")
                else:
                    print("Swap failed or transaction ID not found.")
            else:
                print("Swap cancelled.")
        else:
            print("Failed to fetch swap quote.")

if __name__ == "__main__":
    main()
