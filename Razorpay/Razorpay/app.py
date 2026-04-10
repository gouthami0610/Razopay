from flask import Flask, render_template, request, jsonify
import razorpay
import sqlite3
from datetime import datetime
from cryptography.fernet import Fernet 
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.asymmetric import rsa, padding

app = Flask(__name__)

# Razorpay configuration - Test keys (Replace with your actual test keys)
RAZORPAY_KEY_ID = 'rzp_test_SatINEIIe1eyvB'  # Replace with actual Razorpay test key ID
RAZORPAY_KEY_SECRET = 'W6esDtSnE2A4kyB8W35GOsU0'  # Replace with actual Razorpay test key secret


client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

def key_gen():
    key=Fernet.generate_key()
    print('Key:-',key)
    return key

def En_crypt(message, key):
    K=Fernet(key)
    en_crypto=K.encrypt(message.encode())
    print("En_crypto:- ", en_crypto)
    return en_crypto

def De_crypt(encryp_data, key): 
    S=Fernet(key)
    de_crypto=S.decrypt(encryp_data.decode())
    print("De_crypto", de_crypto)
    return de_crypto

class Wallet:
    def __init__(self):
        self.privatekey = rsa.generate_private_key(65537, 2048)
    
    def sing(self, message_hash):
        message = message_hash
        return self.privatekey.sign(
            message, padding.PSS( mgf= padding.MGF(hashes.SHA256())),
            sat_length =padding.PSS.MAX_LENGTH
        ), hashes.SHA256()

wallet = Wallet()

import json
import hashlib
import time
class Block:
    def __init__(self, index, transaction, previoushash):
        self.index = index
        self.transaction =transaction
        self.previoushash=previoushash
        self.timestamp= time.time()
        self.nonce = 0
        self.hash =self.Cre_hashh()
    
    def Cre_hashh(self):
        data=json.dumps({
            "index" : self.index,
            "transaction" : self.transaction,
            "previoushash" :self.previoushash,
            "nonce" :   self.nonce,
            "time"  :   self.timestamp
            }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()
    def mine(self, difficulty=3):
        target = "0" * difficulty
        while self.hash[:difficulty] != target:
            self.nonce += 1
            self.hash = self.Cre_hashh

# Database setup
def init_db():
    conn = sqlite3.connect('Razor.db') #Razorpaydb.sqlite3
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT,
        payment_id TEXT,
        signature TEXT,
        amount INTEGER,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    
    c.execute('''CREATE TABLE IF NOT EXISTS Blocks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        Block_No TEXT,
        Block_Data TEXT,
        Keys TEXT, 
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        Block_Id TEXT,
        Data TEXT, 
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    c.execute('''CREATE TABLE IF NOT EXISTS Blockchain (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        Hash TEXT,
        Prev_hash TEXT,
        Nonce TEXT,  
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.close()

init_db()

def get_last_hash():
    conn = sqlite3.connect('Razor.db') #Razorpaydb.sqlite3
    c = conn.cursor()
    c.execute("select Hash from  Blockchain  order by id DESC ")
    Rows=c.fetchone()
    conn.close()
    return Rows[0] if Rows else "0"

def save_blockchain(block):
    conn = sqlite3.connect('Razor.db') #Razorpaydb.sqlite3
    c = conn.cursor()

    print("data: --- ",block.index, block.hash, block.previoushash, block.nonce, block.timestamp)
 
    c.execute("insert into  Blockchain values (?,?,?,?,?) ",
              (block.index, block.hash, block.previoushash, block.nonce, block.timestamp))
    for tx in block.transaction:
         c.execute("insert into  transactions (Block_Id, Data) values (?,?) ",
              (block.index, json.dumps(tx)))
    conn.commit()
    conn.close()
    






@app.route('/')
def index():
    return render_template('index.html', key_id=RAZORPAY_KEY_ID)

@app.route('/create_order', methods=['POST'])
def create_order():
    amount = request.form.get('amount')
    if not amount or not amount.isdigit():
        return jsonify({'error': 'Invalid amount'}), 400
    
    amount_paise = int(amount) * 100  # Convert to paise
    
    order_data = {
        'amount': amount_paise,
        'currency': 'INR',
        'payment_capture': '1'
    }
    
    order = client.order.create(data=order_data)
    order_id = order['id']
    
    # Store in DB
    conn = sqlite3.connect('Razor.db')
    c = conn.cursor()
    c.execute('INSERT INTO payments (order_id, amount, status) VALUES (?, ?, ?)',
              (order_id, amount_paise, 'created'))
    

    B_data={
        'amount': amount_paise,
        'currency': 'INR',
        'payment_capture': '1',
        'order_id': order_id
    }
    B_data= str(B_data)
    key= key_gen()
    Encrypt_message=En_crypt(B_data, key)

    Block_Nums = conn.execute("select count(*) from Blocks").fetchone()[0]
    
    print("Block_No:-",Block_Nums)
    
    c.execute('INSERT INTO Blocks (Block_No, Block_Data, Keys, status) VALUES (?, ?, ?, ?)',
              (Block_Nums, Encrypt_message, key, 'created'))
    
    conn.commit()
    conn.close()
    
    return jsonify({'order_id': order_id, 'amount': amount_paise})

@app.route('/verify', methods=['POST'])
def verify():
    data = request.get_json()
    razorpay_order_id = data.get('razorpay_order_id')
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_signature = data.get('razorpay_signature')
    
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        })
        
        # Update DB
        conn = sqlite3.connect('Razor.db')
        c = conn.cursor()
        c.execute('UPDATE payments SET payment_id=?, signature=?, status=? WHERE order_id=?',
                  (razorpay_payment_id, razorpay_signature, 'success', razorpay_order_id))
        
        B_data={
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature,
        }
        B_data= str(B_data)
        key= key_gen()
        Encrypt_message=En_crypt(B_data, key)
        
        Block_Nums = conn.execute("select count(*) from Blocks").fetchone()[0]
        print("Block_No:-",Block_Nums)
        c.execute('INSERT INTO Blocks (Block_No, Block_Data, Keys, status) VALUES (?, ?, ?, ?)',
              (Block_Nums, Encrypt_message, key, 'success'))
        conn.commit()

        encryptedmessage=Encrypt_message
        print("---------------------------------------------------------")
        print("-----------------BLOCK-CHAIN-PROCESS----------------------")
        print("----------------------------------------------------------")
        print("[Info-EncryptedMessage] :: ",encryptedmessage)
        mes_hash =  hashlib.sha256(encryptedmessage).digest()
        print("----------------------------------------------------------")
        print("[Info-Mes_hash] :: ",mes_hash)
        signature = razorpay_signature
        print("----------------------------------------------------------")
        print("[Info-razorpay_signature] :: ",razorpay_signature)
        # Wallet_signature = wallet.sing(mes_hash)
        # print("----------------------------------------------------------")
        # print("[Info-Wallet_signature] :: ",Wallet_signature)
        
        tx= {
            "msg": encryptedmessage.hex(),
            "hash": mes_hash.hex(),
            "sig": mes_hash.hex()
        }
        
        print("----------------------------------------------------------")
        print("[Info-tx] :: ",tx)
        pre_hash= get_last_hash()
        print("----------------------------------------------------------")
        print("[Info-pre_hash] :: ",pre_hash)
        block = Block(int(time.time()),[tx], pre_hash)
        print("----------------------------------------------------------")
        print("[Info-block] :: createed ")
        
        save_blockchain(block)
        print("[Info-save_blockchain] :: save_blockchain ")


        conn.close()
        
        return jsonify({'status': 'success'})
    except Exception as e:
        print(f"Verification failed: {e}")
        
        # Update DB
        conn = sqlite3.connect('Razor.db')
        c = conn.cursor()
        c.execute('UPDATE payments SET payment_id=?, signature=?, status=? WHERE order_id=?',
                  (razorpay_payment_id, razorpay_signature, 'failed', razorpay_order_id))
        B_data={
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature,
        }
        B_data= str(B_data)
        key= key_gen()
        Encrypt_message=En_crypt(B_data, key)
        Block_Nums = conn.execute("select count(*) from Blocks").fetchone()[0]
        print("Block_No:-",Block_Nums)
        c.execute('INSERT INTO Blocks (Block_No, Block_Data, Keys, status) VALUES (?, ?, ?, ?)',
              (Block_Nums, Encrypt_message, key, 'failed'))
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'failed'})

@app.route('/payments')
def payments():
    conn = sqlite3.connect('Razor.db')
    c = conn.cursor()
    c.execute('SELECT order_id, payment_id, amount, status, created_at FROM payments ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    
    return render_template('payments.html', payments=rows)


@app.route('/viewBlocks')
def view_blocks():
    conn = sqlite3.connect('Razor.db')
    c = conn.cursor()
    c.execute('SELECT id, Block_No, Block_Data, Keys,status, created_at FROM Blocks ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    
    return render_template('viewblocks.html', blocks=rows)


@app.route('/success')
def success():
    return render_template('success.html')

@app.route('/failure')
def failure():
    return render_template('failure.html')

if __name__ == '__main__':
    app.run(debug=True)