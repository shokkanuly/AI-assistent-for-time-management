# 🛰️ Aperture OS: AI-Driven Tactical Dashboard

**Aperture OS** is a high-performance web-based AI assistant designed to optimize time management through autonomous task orchestration. Built with a **Python/Flask** backend and a terminal-inspired frontend, it utilizes Large Language Models (LLMs) to bridge the gap between natural language chat and structured database management.

---

## 🧠 System Intelligence
The core of Aperture OS is a **ReAct (Reason + Act)** agent. Unlike standard bots, this system doesn't just talk—it executes.

* **Autonomous Tool Use:** The AI is equipped with Python-defined "tools" (Function Calling) that allow it to read and write to the SQL database.
* **State Injection:** Every interaction is grounded with real-time context, including the current date and recent chat history, allowing for relative commands like *"What do I have planned for tomorrow?"*
* **Local-First Privacy:** Optimized to run with **Ollama (Llama 3)**, ensuring your personal schedule and habits stay on your local machine.

## 🚀 Key Features
* **AI Terminal:** A command-line style interface where the AI manages your calendar via natural language.
* **Habit Engine:** Track daily routines with a built-in 7-day telemetry visualization.
* **Persistent Data:** Secure user authentication and full history storage using SQLite.
* **Agentic Capabilities:**
    * `tool_add_task`: AI can autonomously schedule directives.
    * `tool_get_tasks`: AI can query and summarize your agenda for any specific date.

## 🛠️ Tech Stack
* **Language:** Python 3.x
* **Framework:** Flask
* **Database:** SQLite3
* **AI Orchestration:** OpenAI SDK (configured for local Ollama/Llama 3)
* **Server:** Waitress (WSGI)
* **UI:** HTML5, CSS3, JavaScript

---

## 💻 Installation & Setup

### 1. Prerequisites
* Python 3.10 or higher installed.
* [Ollama](https://ollama.com/) installed and running.
* Pull the model: `ollama run llama3`

### 2. Clone the Repository
```bash
git clone [https://github.com/shokkanuly/AI-assistent-for-time-management.git](https://github.com/shokkanuly/AI-assistent-for-time-management.git)
cd AI-assistent-for-time-management
