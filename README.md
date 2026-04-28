# J. Lambert Foundry — Lead Extraction Agent

An autonomous B2B lead generation agent that discovers high-quality prospects using AI (Groq/Llama 3), verifies email deliverability, and maintains a local deduplicated database.

## 🚀 Features
- **Autonomous Discovery:** Automatically rotates through industries and locations to find target companies.
- **Executive Enrichment:** Identifies key decision-makers (CEO, CTO, etc.) at discovered companies.
- **Email Intelligence:** Deduces corporate email formats and verifies deliverability via MX record lookups to prevent bounces.
- **Smart Deduplication:** Uses a local SQLite database to ensure you never extract or contact the same lead twice.
- **CSV Export:** Generates clean, ready-to-use CSV files for outreach.

## 🛠️ Tech Stack
- **AI Brain:** [Groq](https://groq.com/) (Llama 3.3 70B)
- **Database:** SQLite
- **Language:** Python 3.10+
- **Key Libraries:** `openai`, `rich`, `email-validator`

## 📦 Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/lead_agent.git
   cd lead_agent
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set your API Key:**
   Get a free API key from [Groq Console](https://console.groq.com/) and set it as an environment variable:
   ```powershell
   # Windows (PowerShell)
   $env:GROQ_API_KEY="your_key_here"

   # Linux/macOS
   export GROQ_API_KEY="your_key_here"
   ```

## ⚙️ Configuration

Edit `config.json` to customize your targeting:
```json
{
  "target_industries": ["Fintech", "Legal Tech"],
  "target_locations": ["NYC", "London"],
  "target_titles": ["CEO", "CTO"],
  "daily_quota": 200,
  "groq_model": "llama-3.3-70b-versatile"
}
```

## 🚀 Usage

**Run the agent:**
```bash
python main.py
```

**Run with a specific quota:**
```bash
python main.py --quota 50
```

**Export today's leads to CSV without running a new search:**
```bash
python main.py --export-only
```

**Dry run (test without API calls):**
```bash
python main.py --dry-run
```

## 📂 Project Structure
- `main.py`: The core orchestrator and CLI entry point.
- `search.py`: Handles API interactions with Groq.
- `db.py`: SQLite database layer and deduplication logic.
- `utils.py`: Email verification and formatting utilities.
- `exports/`: Directory where daily CSV files are saved.
- `leads.db`: Local SQLite database (git-ignored).

## 📄 License
MIT License - see [LICENSE](LICENSE) for details.
