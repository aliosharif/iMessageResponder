import sqlite3
import time
import subprocess
from openai import OpenAI
import creds
from collections import defaultdict
import random
from contacts import CONTACTS, YOUR_NUMBER

# Configuration
CONFIG = {
    'db_path': '/Users/aliosharif/Library/Messages/chat.db', # change this to your own path
    'poll_interval': 5,  # seconds
    'response_window': 40,  # seconds
    'min_response_delay': 10,  # minimum seconds to wait before sending a response
    'max_response_delay': 40,  # maximum seconds to wait before sending a response
    'contacts': CONTACTS, # access contains from contacts.py
    'your_number': YOUR_NUMBER # access your number from contacts.py
}

# Initialize OpenAI client
client = OpenAI(
    api_key=creds.openai_api_key # access your openai api key from creds.py
)


def chatgpt_responder(imessages, sender):
    combined_messages = " ".join(imessages)
    prompt = (
        f'Please come up with a response to the following text message(s)' # change prompt to anything  
        f': {combined_messages}'
    )

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="gpt-3.5-turbo"
        )
        response = chat_completion.choices[0].message.content.replace('"', '').replace("'", "")
        return response
    except Exception as e:
        print(f"[ERROR] ChatGPT response generation failed: {e}")
        return "Sorry, I'm unable to respond right now."



def send_message(phone_number, message):
    delay = random.uniform(CONFIG['min_response_delay'], CONFIG['max_response_delay'])
    print(f"[DELAY] Waiting {delay:.2f} seconds before sending the message...")
    time.sleep(delay)

    try:
        subprocess.run(['osascript', 'send.scpt', phone_number, message], check=True, text=True)
        print(f"[SENT] Message to {CONFIG['contacts'].get(phone_number, phone_number)}")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to send message to {CONFIG['contacts'].get(phone_number, phone_number)}: {e}")


# sends a summary of the text long to your own number
def send_summary(original_messages, response, sender):
    summary = f"Interaction Summary:\nFrom: {sender}\nReceived: {' | '.join(original_messages)}\nSent: {response}"
    send_message(CONFIG['your_number'], summary)
    print(f"[SUMMARY] Sent interaction summary to your number")



def get_current_timestamp(conn):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(date) FROM message")
        result = cursor.fetchone()
        return result[0] if result[0] else 0
    except sqlite3.Error as e:
        print(f"[ERROR] SQLite error in get_current_timestamp: {e}")
        return 0



def fetch_new_messages(conn, last_date):
    try:
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(CONFIG['contacts']))
        query = f"""
            SELECT text, date, handle.id
            FROM message
            JOIN handle ON message.handle_id = handle.ROWID
            WHERE handle.id IN ({placeholders}) 
            AND message.date > ? 
            AND message.is_from_me = 0
            ORDER BY message.date ASC
        """
        cursor.execute(query, list(CONFIG['contacts'].keys()) + [last_date])
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"[ERROR] SQLite error in fetch_new_messages: {e}")
        return []



def listen_for_messages():
    print("[START] iMessage Auto-Responder activated")
    conn = sqlite3.connect(CONFIG['db_path'])
    last_message_date = get_current_timestamp(conn)
    message_groups = defaultdict(list)
    last_message_time = defaultdict(float)

    while True:
        current_time = time.time()
        new_messages = fetch_new_messages(conn, last_message_date)

        for message in new_messages:
            text, date, handle_id = message
            sender = CONFIG['contacts'].get(handle_id, handle_id)
            if text:
                print(f"[RECEIVED] From {sender}: {text[:50]}{'...' if len(text) > 50 else ''}")
                message_groups[handle_id].append(text)
                last_message_time[handle_id] = current_time
                last_message_date = max(last_message_date, date)
            else:
                print(f"[SKIPPED] Empty message from {sender}")

        # Process message groups
        for handle_id, messages in list(message_groups.items()):
            if current_time - last_message_time[handle_id] >= CONFIG['response_window']:
                sender = CONFIG['contacts'].get(handle_id, handle_id)
                response = chatgpt_responder(messages, sender)
                send_message(handle_id, response)
                send_summary(messages, response, sender)
                del message_groups[handle_id]

        time.sleep(CONFIG['poll_interval'])



if __name__ == "__main__":
    listen_for_messages()