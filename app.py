import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
CSV_FILE = Path(__file__).parent / "indb_foods.csv"
MODEL    = "meta-llama/llama-3.1-8b-instruct:free"

SYSTEM_TEMPLATE = """\
You are MacroTrack, a friendly Indian nutrition assistant.

Here is the complete nutrition database in CSV format:
{csv_content}

When the user tells you what they ate (e.g. "2 chapatis and 1 bowl dal"):
1. Find each food in the database above
2. Multiply macros by the quantity
3. Return a clean table: Food | Qty | Calories | Protein(g) | Carbs(g) | Fat(g)
4. Show the meal total
5. Show running day total (track across the conversation)
6. One short tip if any macro is very low or high

Daily targets set by the user.
If a food is not in the database, do not estimate, just tell it is not available.
Keep responses concise.
"""

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_csv() -> str:
    if not CSV_FILE.exists():
        sys.exit(f"[ERROR] '{CSV_FILE}' not found. Place indb_foods.csv in the same folder.")
    return CSV_FILE.read_text(encoding="utf-8")


def build_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("[ERROR] OPENROUTER_API_KEY not set. Add it to your .env file.")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)


# ── Main chat loop ────────────────────────────────────────────────────────────
def main() -> None:
    csv_content = load_csv()
    client      = build_client()

    system_msg  = {"role": "system", "content": SYSTEM_TEMPLATE.format(csv_content=csv_content)}
    history     = [system_msg]

    print("🥗  MacroTrack — Indian Nutrition Assistant")
    print("    Type what you ate. Enter 'reset' to start a new day, 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye! Stay healthy 💪")
            break

        if not user_input:
            continue

        if user_input.lower() in {"quit", "exit", "bye"}:
            print("Goodbye! Stay healthy 💪")
            break

        if user_input.lower() == "reset":
            history = [system_msg]
            print("[Day reset — running totals cleared]\n")
            continue

        history.append({"role": "user", "content": user_input})

        try:
            response = client.chat.completions.create(model=MODEL, messages=history)
            reply    = response.choices[0].message.content
        except Exception as exc:
            print(f"[API error] {exc}\n")
            history.pop()          # remove the failed user message
            continue

        history.append({"role": "assistant", "content": reply})
        print(f"\nMacroTrack:\n{reply}\n")


if __name__ == "__main__":
    main()
