import json
import os
from solana.keypair import Keypair
from solana.rpc.api import Client
from solana.system_program import TransferParams, transfer
from solana.transaction import Transaction
from solana.publickey import PublicKey


# Constants
CACHE_FILE = "wallets_cache.json"
SOLANA_TESTNET = "https://api.devnet.solana.com"
SOLANA_MAINNET = "https://api.mainnet-beta.solana.com"
JUPITER_API_URL = ""
LAMPORTS = 1000000000


def generate_solana_wallet():
    """Generate a new Solana wallet and return its public and private keys."""
    keypair = Keypair.generate()
    return str(keypair.public_key), keypair.secret_key.hex()

def save_wallets(wallets, filename=CACHE_FILE):
    """Save wallets to a JSON file."""
    with open(filename, "w") as file:
        json.dump(wallets, file, indent=4)

def load_wallets(filename=CACHE_FILE):
    """Load wallets from a JSON file."""
    if os.path.exists(filename):
        with open(filename, "r") as file:
            return json.load(file)
    return None

def airdrop_sol(client, public_key, amount):
    """Airdrop sol to wallet on devnet"""
    print(f"Airdropping {amount} SOL to {public_key}.")
    response = client.request_airdrop(public_key, int(amount * LAMPORTS))
    if response.get("error"):
        print("Failed to airdrop!", response)
    else:
        print("Airdrop successful")

def send_sol(client, sender_keypair, receiver_public_key, amount):
    """Send SOL from one wallet to another."""
    print(f"Sending {amount} SOL from {sender_keypair.public_key} to {receiver_public_key}.")

    # Convert receiver puiblic key to a PublicKey Obj.
    receiver_public_key = PublicKey(receiver_public_key)

    transfer_instruction = transfer(
            TransferParams(
                from_pubkey=sender_keypair.public_key,
                to_pubkey=receiver_public_key,
                lamports=int(amount * LAMPORTS),
            )
        )
    
    TXID= Transaction().add(transfer_instruction)
    
    response = client.send_transaction(TXID, sender_keypair)
    if response.get("error"):
        print("Transaction failed: ", response)
    else:
        print("Transaction successful! Transaction ID:", response["result"])
def create_wallets(num_wallets):
    """Create a specified number of Solana wallets."""
    wallets = []
    for _ in range(num_wallets):
        public_key, private_key = generate_solana_wallet()
        wallets.append({"public_key": public_key, "private_key": private_key})
    return wallets

def main():

    client = Client(SOLANA_NETWORK)
    # Load wallets from the cache file (if it exists)
    wallets = load_wallets()

    if wallets is None:
        # If no cache file exists, ask the user how many wallets to create
        num_wallets = int(input("Enter the number of wallets to create: "))
        wallets = create_wallets(num_wallets)
        save_wallets(wallets)
        print(f"Created {num_wallets} new wallets and saved to cache.")
    else:
        print(f"Loaded {len(wallets)} wallets from cache.")

    # Print details of the first wallet (if any exist)
    if wallets:
        print("\nFirst wallet details:")
        print(f"Public Key: {wallets[0]['public_key']}")
        print(f"Private Key: {wallets[0]['private_key']}")

        # airdrop_sol(client, wallets[0]["public_key"], 5)

        sender_keypair = Keypair.from_secret_key(bytes.fromhex(wallets[0]["private_key"]))
        
        #send_sol(client, sender_keypair, wallets[1]["public_key"], 0.5)

        recipient_address = "7twsymEvi4cQb1g9LrNwENRXi4KwsqChcSCCVLvMeur7"
        send_sol(client, sender_keypair, recipient_address, 0.5)
if __name__ == "__main__":
    main()
