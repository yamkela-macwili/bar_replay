"""Centralized system for managing engine lifecycles and state isolation."""

import uuid
import config
from backend.replay_engine import ReplayEngine
from backend.execution_engine import ExecutionEngine
from backend.indicators import compute_indicators

class ReplaySystem:
    """Isolated container for all trading engines in a single session."""
    
    def __init__(self, data, symbol, timeframe, provider, session_id=None,
                 initial_balance=None):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.symbol = symbol
        self.timeframe = timeframe
        self.provider = provider
        self.source_checked_at = data.attrs.get("source_checked_at")
        self.source_refresh_error = data.attrs.get("source_refresh_error")
        
        # Initialize engines
        # Start replay at the newest provider bar; get_visible_data still shows
        # the preceding INITIAL_BAR_COUNT candles for context.
        start_idx = max(0, len(data) - 1)
        self.replay_engine = ReplayEngine(data, start_index=start_idx)
        self.execution_engine = ExecutionEngine(
            initial_balance=initial_balance,
            spread_pips=config.DEFAULT_SPREAD_PIPS,
            commission=config.DEFAULT_COMMISSION
        )
        # Default indicators for better UX
        self.active_indicators = {
            "sma": {"period": 20},
            "rsi": {"period": 14}
        }
        
        # Placeholders for Phase 4
        self.strategy_engine = None
        self.metrics_engine = None
        
        # Initial indicator recalc
        self.refresh_indicators()

    def refresh_indicators(self):
        """Recalculate all indicators for the full engine dataset."""
        indicators_data = compute_indicators(self.replay_engine.data, self.active_indicators)
        self.replay_engine.set_indicators(indicators_data)

    def get_state(self, current_price):
        """Aggregate state for API responses."""
        return {
            "session_id": self.session_id,
            "progress": self.replay_engine.get_progress(),
            "account": self.execution_engine.get_account_state(current_price),
            "open_positions": self.execution_engine.get_open_positions(current_price),
            "trade_history": self.execution_engine.get_trade_history()
        }

class EngineFactory:
    """Factory for creating fresh ReplaySystem instances."""
    
    @staticmethod
    def create(symbol, timeframe, provider, session_id=None, initial_balance=None):
        """Create a new ReplaySystem with fresh data and engines."""
        from backend import data_module
        
        # Load initial data via Provider
        load_count = max(config.INITIAL_BAR_COUNT, 500)
        df = data_module.load_symbol(
            symbol, timeframe, count=load_count, provider_type=provider,
            refresh=(provider == "yfinance")
        )
        
        if df.empty:
            raise ValueError(f"No data found for {symbol} {timeframe}")
            
        return ReplaySystem(
            df, symbol, timeframe, provider, session_id=session_id,
            initial_balance=initial_balance
        )
