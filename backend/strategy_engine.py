"""Strategy engine for automated backtesting (Phase 2 shell)."""

from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    """Abstract base class for trading strategies.

    Users extend this class and implement on_bar() to define
    their strategy logic.
    """

    def __init__(self):
        self.name = self.__class__.__name__

    @abstractmethod
    def on_bar(self, bar, context):
        """Called on each new bar during replay.

        Args:
            bar: Series with datetime, open, high, low, close, volume.
            context: Dict with:
                - 'engine': ExecutionEngine instance
                - 'history': DataFrame of all bars up to current
                - 'current_price': current close price
                - 'indicators': dict of computed indicator values

        Returns:
            Optional action dict, e.g.:
            {"action": "buy", "lot_size": 0.1, "sl": 1.08, "tp": 1.10}
        """
        pass


class StrategyRunner:
    """Runs a strategy against the replay engine bar by bar.

    Feeds bars from the replay data to the strategy's on_bar method
    and collects results for metrics computation.
    """

    def __init__(self, strategy, execution_engine):
        """Initialize the strategy runner.

        Args:
            strategy: BaseStrategy instance.
            execution_engine: ExecutionEngine instance.
        """
        self.strategy = strategy
        self.engine = execution_engine
        self.signals = []

    def run_bar(self, bar, history, indicators=None):
        """Process a single bar through the strategy.

        Args:
            bar: Current bar Series.
            history: Historical bars DataFrame.
            indicators: Optional computed indicators dict.

        Returns:
            Action dict from strategy, or None.
        """
        context = {
            "engine": self.engine,
            "history": history,
            "current_price": bar["close"],
            "indicators": indicators or {},
        }

        action = self.strategy.on_bar(bar, context)
        if action:
            self.signals.append({
                "datetime": str(bar["datetime"]),
                "action": action,
            })
        return action

    def compute_metrics(self):
        """Compute strategy performance metrics.

        Returns:
            Dict with win_rate, profit_factor, max_drawdown,
            sharpe_ratio, total_trades.
        """
        closed = self.engine.closed_positions
        total_trades = len(closed)

        if total_trades == 0:
            return {
                "win_rate": 0,
                "profit_factor": 0,
                "max_drawdown": 0,
                "sharpe_ratio": 0,
                "total_trades": 0,
                "total_pnl": 0,
            }

        winners = [p for p in closed if p.pnl > 0]
        losers = [p for p in closed if p.pnl <= 0]

        gross_profit = sum(p.pnl for p in winners)
        gross_loss = abs(sum(p.pnl for p in losers))

        win_rate = len(winners) / total_trades * 100
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0 else float("inf")
        )

        # Max drawdown
        peak = self.engine.initial_balance
        max_dd = 0
        running = self.engine.initial_balance
        for p in closed:
            running += p.pnl
            peak = max(peak, running)
            dd = (peak - running) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)

        # Sharpe ratio (simplified)
        pnls = [p.pnl for p in closed]
        import numpy as np
        mean_pnl = np.mean(pnls)
        std_pnl = np.std(pnls) if len(pnls) > 1 else 1
        sharpe = mean_pnl / std_pnl if std_pnl > 0 else 0

        return {
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 3),
            "total_trades": total_trades,
            "total_pnl": round(sum(p.pnl for p in closed), 2),
        }
