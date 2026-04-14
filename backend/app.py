from flask import Flask, request, jsonify, render_template, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from openai import OpenAI
import sqlite3
import json
import os

app = Flask(__name__)
app.secret_key = 'aperture_system_override_key'
DATABASE = 'aperture_os.db'

# AI Client configuration (Pointed to Local Ollama by default)
client = OpenAI(base_url="http://localhost:11434/v1", api_key="local-agent")
AI_MODEL = "llama3" # Change to 'gpt-4o' if using OpenAI, or your local Ollama model name

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def init_db():
    if not os.path.exists(DATABASE):
        with app.app_context():
            conn = get_db()
            with open('schema.sql', 'r') as f:
                conn.executescript(f.read())
            conn.commit()
            conn.close()
            print("Aperture OS Database Initialized.")

# --- AGENT TOOLS (PYTHON FUNCTIONS) ---
def tool_add_task(user_id, date, description):
    """Inserts a new task into the database."""
    conn = get_db()
    conn.execute('INSERT INTO calendar_tasks (user_id, task_date, description) VALUES (?, ?, ?)', 
                   (user_id, date, description))
    conn.commit()
    conn.close()
    return f"System Log: Added directive '{description}' to {date}."

def tool_get_tasks(user_id, date):
    """Retrieves tasks for a specific date."""
    conn = get_db()
    tasks = conn.execute('SELECT description FROM calendar_tasks WHERE user_id = ? AND task_date = ?', 
                         (user_id, date)).fetchall()
    conn.close()
    if not tasks: return f"No directives found for {date}."
    return "Directives: " + ", ".join([t['description'] for t in tasks])

# --- AGENT SCHEMA ---
agent_tools = [
    {
        "type": "function",
        "function": {
            "name": "tool_add_task",
            "description": "Add a new task, event, or directive to the user's calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "The date in YYYY-M-D format (e.g., 2026-3-15)."},
                    "description": {"type": "string", "description": "The description of the task."}
                },
                "required": ["date", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tool_get_tasks",
            "description": "Check the database for tasks scheduled on a specific date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "The date in YYYY-M-D format."}
                },
                "required": ["date"]
            }
        }
    }
]

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('main.html')

@app.route('/api/auth/me', methods=['GET'])
def get_me():
    if 'user_id' in session: return jsonify({'logged_in': True, 'email': session['email']})
    return jsonify({'logged_in': False})

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    conn = get_db()
    try:
        conn.execute('INSERT INTO users (email, password_hash) VALUES (?, ?)', 
                     (data.get('email'), generate_password_hash(data.get('password'))))
        user_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.execute("INSERT INTO chat_history (user_id, role, content) VALUES (?, 'ai', 'Aperture System Initialized. Awaiting input.')", (user_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Registration successful.'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Email already exists.'}), 400
    finally:
        conn.close()

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (data.get('email'),)).fetchone()
    conn.close()
    
    if user and check_password_hash(user['password_hash'], data.get('password')):
        session['user_id'] = user['id']
        session['email'] = user['email']
        return jsonify({'success': True, 'email': user['email']})
    return jsonify({'success': False, 'message': 'Invalid credentials.'}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/chat', methods=['GET', 'POST'])
def handle_chat():
    if 'user_id' not in session: return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    conn = get_db()
    
    if request.method == 'GET':
        chats = conn.execute('SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY id ASC', (user_id,)).fetchall()
        conn.close()
        return jsonify([{'role': c['role'], 'content': c['content']} for c in chats])
    
    if request.method == 'POST':
        user_msg = request.get_json().get('message')
        conn.execute('INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)', (user_id, 'user', user_msg))
        
        # 1. State Injection
        today = datetime.now()
        system_prompt = f"You are the Aperture OS AI Core. You manage the user's tactical dashboard. Today's date is {today.year}-{today.month}-{today.day}. Be concise and professional."
        
        # Retrieve recent history for context
        history_rows = conn.execute('SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY id DESC LIMIT 5', (user_id,)).fetchall()
        messages = [{"role": "system", "content": system_prompt}]
        for row in reversed(history_rows):
            messages.append({"role": row['role'], "content": row['content']})

        # 2. First LLM Call (Checking for Tools)
        ui_refresh_needed = False
        try:
            response = client.chat.completions.create(
                model=AI_MODEL,
                messages=messages,
                tools=agent_tools,
                tool_choice="auto"
            )
            response_msg = response.choices[0].message
            
            # 3. Execute Tool if requested
            if response_msg.tool_calls:
                ui_refresh_needed = True # AI modified data, tell UI to refresh
                messages.append(response_msg)
                
                for tool_call in response_msg.tool_calls:
                    fn_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    
                    if fn_name == "tool_add_task":
                        tool_res = tool_add_task(user_id, args.get("date"), args.get("description"))
                    elif fn_name == "tool_get_tasks":
                        tool_res = tool_get_tasks(user_id, args.get("date"))
                    
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": fn_name, "content": tool_res})
                
                # Second call to summarize action
                final_res = client.chat.completions.create(model=AI_MODEL, messages=messages)
                ai_reply = final_res.choices[0].message.content
            else:
                ai_reply = response_msg.content

        except Exception as e:
            ai_reply = f"System Error connecting to AI Core: {str(e)}"

        conn.execute('INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)', (user_id, 'ai', ai_reply))
        conn.commit()
        conn.close()
        
        return jsonify({'reply': ai_reply, 'refresh_ui': ui_refresh_needed})

@app.route('/api/habits', methods=['GET', 'POST'])
def handle_habits():
    if 'user_id' not in session: return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    conn = get_db()
    if request.method == 'GET':
        habits_data = []
        habits = conn.execute('SELECT id, name FROM habits WHERE user_id = ?', (user_id,)).fetchall()
        for h in habits:
            progress_rows = conn.execute('SELECT day_index, is_completed FROM habit_progress WHERE habit_id = ? ORDER BY day_index', (h['id'],)).fetchall()
            progress = [False] * 7
            for p in progress_rows: progress[p['day_index']] = bool(p['is_completed'])
            habits_data.append({'id': h['id'], 'name': h['name'], 'progress': progress})
        conn.close()
        return jsonify(habits_data)
    if request.method == 'POST':
        name = request.get_json().get('name')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO habits (user_id, name) VALUES (?, ?)', (user_id, name))
        habit_id = cursor.lastrowid
        for i in range(7): cursor.execute('INSERT INTO habit_progress (habit_id, day_index, is_completed) VALUES (?, ?, 0)', (habit_id, i))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Habit created', 'id': habit_id})

@app.route('/api/habits/<int:habit_id>', methods=['DELETE'])
def delete_habit(habit_id):
    if 'user_id' not in session: return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    conn.execute('DELETE FROM habits WHERE id = ? AND user_id = ?', (habit_id, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Habit deleted'})

@app.route('/api/habits/toggle', methods=['POST'])
def toggle_habit():
    if 'user_id' not in session: return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    conn = get_db()
    current = conn.execute('SELECT is_completed FROM habit_progress WHERE habit_id = ? AND day_index = ?', (data.get('habit_id'), data.get('day_index'))).fetchone()
    if current:
        conn.execute('UPDATE habit_progress SET is_completed = ? WHERE habit_id = ? AND day_index = ?', (1 if current['is_completed'] == 0 else 0, data.get('habit_id'), data.get('day_index')))
        conn.commit()
    conn.close()
    return jsonify({'message': 'Toggled'})

@app.route('/api/tasks', methods=['GET', 'POST'])
def handle_tasks():
    if 'user_id' not in session: return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    conn = get_db()
    if request.method == 'GET':
        tasks = conn.execute('SELECT id, task_date, description FROM calendar_tasks WHERE user_id = ?', (user_id,)).fetchall()
        conn.close()
        tasks_dict = {}
        for t in tasks:
            date = t['task_date']
            if date not in tasks_dict: tasks_dict[date] = []
            tasks_dict[date].append({'id': t['id'], 'description': t['description']})
        return jsonify(tasks_dict)
    if request.method == 'POST':
        data = request.get_json()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO calendar_tasks (user_id, task_date, description) VALUES (?, ?, ?)', (user_id, data.get('date'), data.get('description')))
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'message': 'Task added', 'id': task_id})

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    if 'user_id' not in session: return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    conn.execute('DELETE FROM calendar_tasks WHERE id = ? AND user_id = ?', (task_id, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Task deleted'})

if __name__ == '__main__':
    init_db()
    from waitress import serve
    print("Aperture OS Backend active on http://localhost:8080...")
    serve(app, host="0.0.0.0", port=8080)