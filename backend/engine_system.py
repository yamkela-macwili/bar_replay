"""Centralized system for managing engine lifecycles and state isolation."""

import uuid
import config
from backend.replay_engine import ReplayEngine
from backend.execution_engine import ExecutionEngine
from backend.indicators import compute_indicators

class ReplaySystem:
    """Isolated container for all trading engines in a single session."""
    
    def __init__(self, data, symbol, timeframe, provider):
        self.session_id = str(uuid.uuid4())[:8]
        self.symbol = symbol
        self.timeframe = timeframe
        self.provider = provider
        
        # Initialize engines
        start_idx = max(0, len(data) - config.INITIAL_BAR_COUNT)
        self.replay_engine = ReplayEngine(data, start_index=start_idx)
        self.execution_engine = ExecutionEngine(
            initial_balance=config.INITIAL_BALANCE,
            spread_pips=config.DEFAULT_SPREAD_PIPS,
            commission=config.DEFAULT_COMMISSION
        )
        # Default indicators for better UX
        self.active_indicators = {
            "SMA": {"period": 20},
            "RSI": {"period": 14}
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
            "open_positions": self.execution_engine.get_open_positions(),
            "trade_history": self.execution_engine.get_trade_history()
        }

class EngineFactory:
    """Factory for creating fresh ReplaySystem instances."""
    
    @staticmethod
    def create(symbol, timeframe, provider):
        """Create a new ReplaySystem with fresh data and engines."""
        from backend import data_module
        
        # Load initial data via Provider
        load_count = max(config.INITIAL_BAR_COUNT, 500)
        df = data_module.load_symbol(symbol, timeframe, count=load_count, provider_type=provider)
        
        if df.empty:
            raise ValueError(f"No data found for {symbol} {timeframe}")
            
        return ReplaySystem(df, symbol, timeframe, provider)
