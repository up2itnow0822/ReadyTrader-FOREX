import json
import logging
import os
import sqlite3
import time

import pandas as pd

logger = logging.getLogger(__name__)


class Learner:
    """
    Analyzes past trades to generate insights for the Agent.
    """

    def __init__(self, db_path: str = "paper.db"):
        self.db_path = db_path

    def analyze_performance(self, cur_symbol: str = None) -> str:
        """
        Review past trades and generate a summary of lessons.
        """
        conn = sqlite3.connect(self.db_path)

        # Fetch filled orders with rationale
        query = "SELECT symbol, side, amount, price, total_value, rationale, pnl_realized FROM orders WHERE status='filled'"
        if cur_symbol:
            query += f" AND symbol='{cur_symbol}'"

        try:
            df = pd.read_sql_query(query, conn)
            conn.close()

            if df.empty:
                return "No past trades to learn from yet."

            # Calculate basic stats
            # Note: pnl_realized needs to be populated when closing positions.
            # For now, we might not have it fully wired in paper_engine, so we rely on rationale review.

            # Simple Heuristic: Look for patterns in rationale of losing trades vs winning trades
            # For this MVP, we just summarize the last 5 trades to give context to the LLM.

            recent_trades = df.tail(5)
            summary = "Recent Trade History & Rationale:\n"

            for index, row in recent_trades.iterrows():
                pnl = row.get("pnl_realized")  # Might be None
                outcome = "Unknown"
                if pnl:
                    outcome = "PROFIT" if pnl > 0 else "LOSS"

                summary += f'- {row["side"]} {row["symbol"]} @ {row["price"]}: {outcome}. Rationale: "{row["rationale"]}"\n'

            return summary

        except Exception as e:
            return f"Error analyzing performance: {str(e)}"

    def save_lesson(self, lesson: str):
        """
        Save a learned lesson to the database.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("CREATE TABLE IF NOT EXISTS lessons (id INTEGER PRIMARY KEY, lesson TEXT, created_at REAL)")
            conn.execute("INSERT INTO lessons (lesson, created_at) VALUES (?, ?)", (lesson, pd.Timestamp.now().timestamp()))
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Learning DB write failed: {e} — data: {lesson}")
            # Don't crash the trading loop; log and continue
            # But write to a fallback JSON log so the data isn't lost
            fallback = os.path.join(os.path.dirname(__file__), '../logs/learning_fallback.jsonl')
            os.makedirs(os.path.dirname(fallback), exist_ok=True)
            with open(fallback, 'a') as f:
                f.write(json.dumps({"record": str(lesson), "error": str(e), "ts": time.time()}) + '\n')
