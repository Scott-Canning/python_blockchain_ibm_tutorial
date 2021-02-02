"""
Source: https://developer.ibm.com/technologies/blockchain/tutorials/develop-a-blockchain-application-from-scratch-in-python/
"""
from hashlib import sha256
import json
import time

from flask import Flask, request
import requests


"""
Blockchain code
"""

class Block:
    def __init__(self, index, transactions, timestamp, previous_hash, nonce=0):
        """
        >>>Constructor
        param index:            unique ID of the block
        param transactions:     list of transactions
        param timestamp:        time of generation of block
        param previous_hash:    hash of previous block in the chain
        param nonce:            variable to achieve difficutly
        """
        self.index = index
        self.transactions = transactions
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        self.nonce = nonce

    def compute_hash(self):
        """
        Returns hash of block instance by virst converting it into JSON string.
        If the content of any of the previous blocks changes:
            1) The hash of that previous block would change.
            2) This will lead to a mismatch with the previous_hash field in the next block.
            3) Since the input data to compute the hash of any block also consists of the
            previous_hash field, the hash of the next block will also change.
        """
        block_string = json.dumps(self.__dict__, sort_keys=True) # converts Py object into json string
        return sha256(block_string.encode()).hexdigest()

class Blockchain:
    difficulty = 2 # difficulty of PoW algo

    def __init__(self):
        """
        >>>Constructor
        """
        self.unconfirmed_transactions = [] # data yet to get into blockchain
        self.chain = []
        #self.create_genesis_block()

    def create_genesis_block(self):
        """
        Generates genesis block and appends to chain;
        the block has index 0, previous_hash as 0, and a valid hash
        """
        genesis_block = Block(0, [], 0, "0")
        genesis_block.hash = genesis_block.compute_hash()
        self.chain.append(genesis_block)

    @property
    def last_block(self):
        """
        Retrieves most recent block in chain;
        note chain always contains at least gen block
        """
        return self.chain[-1]

    """
    ADD BLOCK TO CHAIN
    """

    def add_block(self, block, proof):
        """
        Function adds block to chain after verification
        Verification requires:
            1) Check that the previous_hash referred in the block and the hash
               of the latest block in the chain match
            2) Checking that the proof is valid

        """
        previous_hash = self.last_block.hash # QUESTION - not sure I understand where .hash pulls from

        if previous_hash != block.previous_hash: # check previous_hash in this block matches hash in previous block
            return False

        if not Blockchain.is_valid_proof(block, proof): # check proof is valid
            return False

        block.hash = proof
        self.chain.append(block)
        return True


    """
    PoW
    """

    @staticmethod
    def proof_of_work(block):
        """
        Function that tries different values of nonce to get has that
        satisfies our difficulty criteria
        """
        block.nonce = 0

        computed_hash = block.compute_hash()
        while not computed_hash.startswith('0' * Blockchain.difficulty):
            block.nonce += 1
            computed_hash = block.compute_hash()

        return computed_hash

    def add_new_transaction(self, transaction): # builds out unconfirmed transaction lists (~mempool?)
        self.unconfirmed_transactions.append(transaction)

    @classmethod
    def is_valid_proof(self, block, block_hash):
        """
        Function to check if block_hash is valid hash of block and satisfies
        difficulty criteria
        """
        return (block_hash.startswith('0' * Blockchain.difficulty) and
                block_hash == block.compute_hash())

    """
    CONSENSUS (by longest chain)
    """
    @classmethod
    def check_chain_validity(cls, chain):
        """
        helper method used to check if the entire blockchain is valid
        """
        result = True
        previous_hash = "0"

        # iterate through every block
        for block in chain:
            block_hash = block.hash
            # remove the hash field to recompute the hash again
            # using `compute_hash` method.
            delattr(block, "hash") # delattr() deletes an attribute from the object (if the object allows it).

            if not cls.is_valid(block, block.hash) or \
                    previous_hash != block.previous_hash: # always use cls for the first argument to class methods.
                result = False
                break

            block.hash, previous_hash = block_hash, block_hash

        return result

    def mine(self):
        """
        Function serving as interface to add pending tx to blockchain by adding
        them to block and figuring out PoW
        """
        if not self.unconfirmed_transactions:
            return False

        last_block = self.last_block

        new_block = Block(index=last_block.index + 1,
                          transactions=self.unconfirmed_transactions,
                          timestamp=time.time(),
                          previous_hash=last_block.hash)

        proof = self.proof_of_work(new_block)
        self.add_block(new_block, proof)

        self.unconfirmed_transactions = []
        return True



# initialize flask application
app = Flask(__name__)

# initialize a blockchain object
blockchain = Blockchain()
blockchain.create_genesis_block()

# mechanism to allow new node to become aware of other peers in the network
# address to other participating members of the network
peers = set()

"""
REST endpoints. Can be used to play around with our blockchain by creating some
                transactions and then mining them.. yay!
"""

# endpoint for our app to submit a new tx
@app.route('/new_transaction', methods=['POST'])
def new_transaction():
    tx_data = request.get_json()
    required_fields = ["author", "content"]

    for field in required_fields:
        if not tx_data.get(field):
            return "Invalid transaction data", 404

    tx_data["timestamp"] = time.time()

    blockchain.add_new_transaction(tx_data)

    return "Success", 201

# endpoint to return the node's copy of the chain (query all data to display)
# app uses this endpoint to query all posts to the display
@app.route('/chain', methods=['GET'])
def get_chain():
    chain_data = []
    for block in blockchain.chain:
        chain_data.append(block.__dict__)
    return json.dumps({"length": len(chain_data),
                       "chain": chain_data,
                       "peers": list(peers)})

# endpoint to request the node to mine the unconfirmed
# transactions (if any). We'll be using it to initiate
# a command to mine from our application itself.
@app.route('/mine', methods=['GET'])
def mine_unconfirmed_transactions():
    result = blockchain.mine()
    if not result:
        return "No txs to mine"
    else:
        # Making sure we have the longest chain before announcing to the network
        chain_length = len(blockchain.chain)
        consensus()
        if chain_length == len(blockchain.chain):
            # announce the recently mined block to the network
            announce_new_block(blockchain.last_block)
        return "Block #{} is mined.".format(blockchain.last_block.index)


# endpoint to add new peers to the network
@app.route('/register_node', methods=['POST'])
def register_new_peers():
    # the host address to the peer node
    node_address = request.get_json()["node_address"]
    if not node_address:
        return "Invalid data", 400

    # add the node to the peer list
    peers.add(node_address)

    # return blockchain to newly registered node so it can sync
    return get_chain()

@app.route('/register_with', methods=['POST'])
def register_with_existing_node():
    """
    Internally calls the `register_node` endpoint to
    register current node with the remote node specified in the
    request, and sync the blockchain as well with the remote node
    """

    node_address = request.get_json()["node_address"]
    if not node_address:
        return "Invalid data", 400

    data = {"node_address": request.host_url}
    headers = {'Content-Type': "application/json"}

    # make request to register with remoate node and obtain information
    response = requests.post(node_address + "/register_node",
                             data=json.dumps(data), headers=headers)

    if response.status_code == 200:
        global blockchain
        global peers
        # update chain and the register_new_peers
        chain_dump = response.json()['chain']
        blockchain = create_chain_from_dump(chain_dump)
        peers.update(response.json()['peers'])
        return "Registration successfull", 200
    else:
        #if something fails, pass it onto the API response
        return response.content, response.status_code

def create_chain_from_dump(chain_dump):
    generated_blockchain = Blockchain()
    generated_blockchain.create_genesis_block()
    for idx, block_data in enumerate(chain_dump):
        if idx ==0:
            continue # skip genesis block
        block = Block(block_data["index"],
                      block_data["transactions"],
                      block_data["timestamp"],
                      block_data["previous_hash"],
                      block_data["nonce"])
        proof = block_data['hash']
        added = generated_blockchain.add_block(block, proof)
        if not added:
            raise Exception("The chain dump is tampered!!")
    return generated_blockchain

# endpoint to add a block mined by someone else to
# the node's chain. The node first verifies the block
# and then adds it to the chain.

@app.route('/add_block', methods=['POST'])
def verify_and_add_block():
    block_data = request.get_json()
    block = Block(block_data["index"],
                  block_data["transactions"],
                  block_data["timestamp"],
                  block_data["previous_hash"],
                  block_data["nonce"])

    proof = block_data['hash']
    added = blockchain.add_block(block, proof)

    if not added:
        return "The block was discarded by the node", 400

    return "Block added to the chain!", 201

# endpoint to query unconfirmed txs
@app.route('/pending_tx')
def get_pending_tx():
    return json.dumps(blockchain.unconfirmed_transactions)


def consensus():
    """
    Simple consensus algo; if longer valid chain is found, our chain is
    replaced with it
    """

    global blockchain

    longest_chain = None
    current_len = len(blockchain.chain)

    for node in peers:
        response = requests.get('{}/chain'.format(node))
        length = response.json()['length']
        chain = response.json()['chain']
        if length > current_len and blockchain.check_chain_validity(chain):
            # longer valid chain was found!
            current_len = length
            longest_chain = chain

    if longest_chain:
        blockchain = longest_chain
        return True

    return False

def announce_new_block(block):
    """
    A function to announce to the network once a block has been mined.
    Other blocks can simply verify the proof of work and add it to their
    respective chains.

    The announce_new_block method should be called after every block is
    mined by the node so that peers can add it to their chains.
    """
    for peer in peers:
        url = "{}add_block".format(peer)
        headers = {'Content-Type': "application/json"}
        requests.post(url,
                      data=json.dumps(block.__dict__, sort_keys=True),
                      headers=headers)

# Uncomment this line if you want to specify the port number in the code
#app.run(debug=True, port=8000)
