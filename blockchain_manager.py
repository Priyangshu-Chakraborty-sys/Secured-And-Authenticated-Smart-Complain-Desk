from web3 import Web3
import hashlib
import json
from datetime import datetime
from config import Config

class BlockchainManager:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(Config.BLOCKCHAIN_NETWORK))
        self.contract = None
        self.network_info = None
        
        # Get network information
        if self.w3.is_connected():
            try:
                self.network_info = {
                    'chain_id': self.w3.eth.chain_id,
                    'latest_block': self.w3.eth.block_number,
                    'is_testnet': Config.IS_TESTNET,
                    'explorer_url': Config.get_block_explorer_url()
                }
                print(f"✅ Connected to {self._get_network_name()}")
            except Exception as e:
                print(f"❌ Error getting network info: {e}")
        
        if self.w3.is_connected() and Config.CONTRACT_ADDRESS and Config.CONTRACT_ABI:
            try:
                self.contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(Config.CONTRACT_ADDRESS),
                    abi=Config.CONTRACT_ABI
                )
                print("✅ Blockchain connected and contract loaded")
                print(f"📍 Contract address: {Config.CONTRACT_ADDRESS}")
                if self.network_info:
                    print(f"🔍 View contract: {self.network_info['explorer_url']}/address/{Config.CONTRACT_ADDRESS}")
            except Exception as e:
                print(f"❌ Contract loading failed: {e}")
        else:
            print("❌ Blockchain connection or contract loading failed")
    
    def _get_network_name(self):
        """Get human-readable network name"""
        if not self.network_info:
            return "Unknown Network"
        
        network_names = {
            1: "Ethereum Mainnet",
            11155111: "Sepolia Testnet", 
            5: "Goerli Testnet",
            137: "Polygon Mainnet",
            80001: "Mumbai Testnet"
        }
        return network_names.get(self.network_info['chain_id'], f"Unknown Network (Chain ID: {self.network_info['chain_id']})")
    
    def get_network_info(self):
        """Get current network information"""
        return {
            **self.network_info,
            'network_name': self._get_network_name(),
            'contract_address': Config.CONTRACT_ADDRESS
        }
    
    def is_connected(self):
        return self.w3.is_connected() and self.contract is not None
    
    def is_valid_address(self, address):
        """Validate Ethereum address"""
        try:
            return Web3.is_address(address)
        except:
            return False
    
    def hash_complaint_data(self, complaint_data):
        """Create a hash of sensitive complaint data"""
        data_string = f"{complaint_data['name']}{complaint_data['email']}{complaint_data['complaint']}{complaint_data['phone']}"
        return hashlib.sha256(data_string.encode()).hexdigest()
    
    def submit_complaint_to_blockchain(self, reference_no, complaint_data, department, user_wallet_address):
        """Submit complaint to blockchain with user's wallet address"""
        if not self.is_connected():
            return {"success": False, "message": "Blockchain not available"}
        
        try:
            # Hash sensitive data for privacy
            complaint_hash = self.hash_complaint_data(complaint_data)
            
            # Get account from private key (this is the contract owner/admin account)
            admin_account = self.w3.eth.account.from_key(Config.PRIVATE_KEY)
            
            # Check admin account balance
            balance = self.w3.eth.get_balance(admin_account.address)
            balance_eth = self.w3.from_wei(balance, 'ether')
            
            if balance_eth < 0.001:  # Less than 0.001 ETH
                return {
                    "success": False, 
                    "message": f"Insufficient balance for gas fees. Current balance: {balance_eth:.6f} ETH"
                }
            
            # Estimate gas for the transaction
            try:
                gas_estimate = self.contract.functions.submitComplaintForUser(
                    reference_no,
                    complaint_hash,
                    department,
                    "Submitted",
                    Web3.to_checksum_address(user_wallet_address)
                ).estimate_gas({'from': admin_account.address})
                
                # Add 20% buffer to gas estimate
                gas_limit = int(gas_estimate * 1.2)
            except Exception as e:
                print(f"⚠️  Could not estimate gas, using default: {e}")
                gas_limit = Config.GAS_LIMIT
            
            # Build transaction - submit on behalf of user but from admin account
            transaction = self.contract.functions.submitComplaintForUser(
                reference_no,
                complaint_hash,
                department,
                "Submitted",
                Web3.to_checksum_address(user_wallet_address)  # Pass user's wallet address
            ).build_transaction({
                'from': admin_account.address,
                'gas': gas_limit,
                'gasPrice': self.w3.to_wei(str(Config.GAS_PRICE), 'gwei'),
                'nonce': self.w3.eth.get_transaction_count(admin_account.address)
            })
            
            # Calculate estimated cost
            estimated_cost = transaction['gas'] * transaction['gasPrice']
            estimated_cost_eth = self.w3.from_wei(estimated_cost, 'ether')
            
            print(f"💸 Estimated transaction cost: {estimated_cost_eth:.6f} ETH")
            
            # Sign and send transaction
            signed_txn = self.w3.eth.account.sign_transaction(transaction, Config.PRIVATE_KEY)
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            
            print(f"📤 Transaction sent: {tx_hash.hex()}")
            
            # Wait for transaction receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            
            print(f"✅ Complaint {reference_no} submitted to blockchain for user {user_wallet_address}")
            
            # Generate explorer URLs
            explorer_url = self.network_info['explorer_url'] if self.network_info else Config.get_block_explorer_url()
            
            return {
                "success": True,
                "tx_hash": receipt.transactionHash.hex(),
                "block_number": receipt.blockNumber,
                "gas_used": receipt.gasUsed,
                "actual_cost_eth": float(self.w3.from_wei(receipt.gasUsed * transaction['gasPrice'], 'ether')),
                "network": self._get_network_name(),
                "explorer_urls": {
                    "transaction": f"{explorer_url}/tx/0x{receipt.transactionHash.hex()}",
                    "contract": f"{explorer_url}/address/{Config.CONTRACT_ADDRESS}"
                }
            }
            
        except Exception as e:
            print(f"❌ Blockchain submission failed: {e}")
            # Fallback: Try with original method if the new method fails
            try:
                transaction = self.contract.functions.submitComplaint(
                    reference_no,
                    complaint_hash,
                    department,
                    "Submitted"
                ).build_transaction({
                    'from': admin_account.address,
                    'gas': Config.GAS_LIMIT,
                    'gasPrice': self.w3.to_wei(str(Config.GAS_PRICE), 'gwei'),
                    'nonce': self.w3.eth.get_transaction_count(admin_account.address)
                })
                
                signed_txn = self.w3.eth.account.sign_transaction(transaction, Config.PRIVATE_KEY)
                tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                
                explorer_url = self.network_info['explorer_url'] if self.network_info else Config.get_block_explorer_url()
                
                return {
                    "success": True,
                    "tx_hash": receipt.transactionHash.hex(),
                    "block_number": receipt.blockNumber,
                    "gas_used": receipt.gasUsed,
                    "network": self._get_network_name(),
                    "explorer_urls": {
                        "transaction": f"{explorer_url}/tx/0x{receipt.transactionHash.hex()}",
                        "contract": f"{explorer_url}/address/{Config.CONTRACT_ADDRESS}"
                    }
                }
            except Exception as e2:
                print(f"❌ Fallback blockchain submission also failed: {e2}")
                return {"success": False, "message": str(e2)}
    
    def get_complaint_from_blockchain(self, reference_no):
        """Retrieve complaint from blockchain"""
        if not self.is_connected():
            print("❌ Blockchain not connected")
            return None
        
        try:
            result = self.contract.functions.getComplaint(reference_no).call()
            return {
                "user": result[0],
                "complaint_hash": result[1],
                "department": result[2],
                "status": result[3],
                "timestamp": result[4],
                "formatted_date": datetime.fromtimestamp(result[4]).strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            print(f"❌ Error retrieving complaint {reference_no} from blockchain: {e}")
            return None
    
    def get_user_complaints(self, user_address):
        """Get all complaint reference numbers for a user"""
        if not self.is_connected():
            print("❌ Blockchain not connected")
            return []
        
        try:
            # Convert to checksum address
            checksum_address = Web3.to_checksum_address(user_address)
            result = self.contract.functions.getUserComplaints(checksum_address).call()
            print(f"✅ Found {len(result)} complaints on blockchain for {user_address}")
            return result
        except Exception as e:
            print(f"❌ Error retrieving user complaints for {user_address}: {e}")
            return []
    
    def verify_complaint_ownership(self, reference_no, user_address):
        """Verify if a complaint belongs to a specific user"""
        if not self.is_connected():
            print("❌ Blockchain not connected")
            return False
        
        try:
            checksum_address = Web3.to_checksum_address(user_address)
            result = self.contract.functions.verifyComplaintOwnership(reference_no, checksum_address).call()
            print(f"✅ Ownership verification for {reference_no}: {result}")
            return result
        except Exception as e:
            print(f"❌ Error verifying complaint ownership for {reference_no}: {e}")
            return False
    
    def get_transaction_details(self, tx_hash):
        """Get detailed information about a transaction"""
        if not self.w3.is_connected():
            return None
        
        try:
            # Get transaction details
            tx = self.w3.eth.get_transaction(tx_hash)
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            
            # Get current block for confirmations
            current_block = self.w3.eth.block_number
            confirmations = current_block - receipt.blockNumber
            
            explorer_url = self.network_info['explorer_url'] if self.network_info else Config.get_block_explorer_url()
            
            return {
                "hash": tx_hash,
                "block_number": receipt.blockNumber,
                "confirmations": confirmations,
                "gas_used": receipt.gasUsed,
                "gas_price": tx.gasPrice,
                "cost_eth": float(self.w3.from_wei(receipt.gasUsed * tx.gasPrice, 'ether')),
                "status": "Success" if receipt.status == 1 else "Failed",
                "timestamp": self.w3.eth.get_block(receipt.blockNumber).timestamp,
                "explorer_url": f"{explorer_url}/tx/{tx_hash if tx_hash.startswith('0x') else '0x' + tx_hash}",
                "from_address": tx["from"],
                "to_address": tx.to
            }
        except Exception as e:
            print(f"❌ Error getting transaction details: {e}")
            return None

    def update_complaint_status(self, reference_no, new_status):
        """Update complaint status (admin function)"""
        if not self.is_connected():
            return {"success": False, "message": "Blockchain not available"}
        
        try:
            account = self.w3.eth.account.from_key(Config.PRIVATE_KEY)
            
            # Estimate gas
            try:
                gas_estimate = self.contract.functions.updateComplaintStatus(
                    reference_no, new_status
                ).estimate_gas({'from': account.address})
                gas_limit = int(gas_estimate * 1.2)
            except:
                gas_limit = Config.GAS_LIMIT
            
            transaction = self.contract.functions.updateComplaintStatus(
                reference_no,
                new_status
            ).build_transaction({
                'from': account.address,
                'gas': gas_limit,
                'gasPrice': self.w3.to_wei(str(Config.GAS_PRICE), 'gwei'),
                'nonce': self.w3.eth.get_transaction_count(account.address)
            })
            
            signed_txn = self.w3.eth.account.sign_transaction(transaction, Config.PRIVATE_KEY)
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            explorer_url = self.network_info['explorer_url'] if self.network_info else Config.get_block_explorer_url()
            
            return {
                "success": True,
                "tx_hash": receipt.transactionHash.hex(),
                "explorer_url": f"{explorer_url}/tx/0x{receipt.transactionHash.hex()}"
            }
            
        except Exception as e:
            return {"success": False, "message": str(e)}