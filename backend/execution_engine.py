"""Execution engine for trade simulation."""

import uuid
from datetime import datetime

import config


class Position:
    """Represents an open or closed trading position."""

    def __init__(self, direction, lot_size, entry_price, sl=None, tp=None,
                 spread=0.0, commission=0.0, entry_time=None):
        self.id = str(uuid.uuid4())[:8]
        self.direction = direction  # "buy" or "sell"
        self.lot_size = lot_size
        self.entry_price = entry_price
        self.sl = sl
        self.tp = tp
        self.spread = spread
        self.commission = commission
        self.entry_time = entry_time or datetime.now().isoformat()
        self.exit_price = None
        self.exit_time = None
        self.pnl = 0.0
        self.status = "open"  # "open" or "closed"

    def calculate_floating_pnl(self, current_price):
        """Calculate unrealized P&L at current price.

        Args:
            current_price: Current market price.

        Returns:
            Float P&L in account currency.
        """
        if self.direction == "buy":
            raw = current_price - self.entry_price - self.spread
        else:
            raw = self.entry_price - current_price - self.spread

        # P&L = price_diff / pip_value * pip_worth * lot_size
        # Simplified: assume 1 standard lot = 100,000 units
        pnl = raw * 100000 * self.lot_size
        return round(pnl - self.commission, 2)

    def close(self, exit_price, exit_time=None):
        """Close this position.

        Args:
            exit_price: Price at which to close.
            exit_time: Time of closing.
        """
        self.exit_price = exit_price
        self.exit_time = exit_time or datetime.now().isoformat()
        self.pnl = self.calculate_floating_pnl(exit_price)
        self.status = "closed"

    def to_dict(self):
        """Convert position to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "direction": self.direction,
            "lot_size": self.lot_size,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "sl": self.sl,
            "tp": self.tp,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "pnl": self.pnl,
            "status": self.status,
            "spread": self.spread,
            "commission": self.commission,
        }


class ExecutionEngine:
    """Handles trade execution, position management, and account tracking.

    Simulates realistic trading with spreads, commissions, SL/TP,
    and full account state management.
    """

    def __init__(self, initial_balance=None, spread_pips=None,
                 commission=None):
        self.initial_balance = initial_balance or config.INITIAL_BALANCE
        self.balance = self.initial_balance
        self.spread = (spread_pips or config.DEFAULT_SPREAD_PIPS) * \
            config.PIP_VALUE
        self.commission = commission or config.DEFAULT_COMMISSION
        self.open_positions = []
        self.closed_positions = []
        self.max_balance = self.initial_balance
        self.min_balance = self.initial_balance

    def open_position(self, direction, lot_size=None, sl=None, tp=None,
                      current_price=None, current_time=None):
        """Open a new trading position.

        Args:
            direction: 'buy' or 'sell'.
            lot_size: Position size in lots.
            sl: Stop loss price.
            tp: Take profit price.
            current_price: Current market price.
            current_time: Current bar datetime.

        Returns:
            Position dict if successful, None if invalid.
        """
        if direction not in ("buy", "sell"):
            return None
        if current_price is None:
            return None

        lot_size = lot_size or config.DEFAULT_LOT_SIZE

        # Entry price includes spread for buy orders
        if direction == "buy":
            entry = current_price + self.spread / 2
        else:
            entry = current_price - self.spread / 2

        pos = Position(
            direction=direction,
            lot_size=lot_size,
            entry_price=round(entry, 5),
            sl=sl,
            tp=tp,
            spread=self.spread,
            commission=self.commission * lot_size,
            entry_time=str(current_time) if current_time else None
        )

        self.open_positions.append(pos)
        self.balance -= self.commission * lot_size
        return pos.to_dict()

    def close_position(self, position_id, current_price, current_time=None):
        """Close a specific open position.

        Args:
            position_id: ID of the position to close.
            current_price: Current market price.
            current_time: Current datetime.

        Returns:
            Closed position dict if found, None otherwise.
        """
        for i, pos in enumerate(self.open_positions):
            if pos.id == position_id:
                pos.close(current_price, str(current_time) if current_time
                          else None)
                self.balance += pos.pnl
                self._update_balance_extremes()
                self.closed_positions.append(pos)
                self.open_positions.pop(i)
                return pos.to_dict()
        return None

    def close_all_positions(self, current_price, current_time=None):
        """Close all open positions.

        Args:
            current_price: Current market price.
            current_time: Current datetime.

        Returns:
            List of closed position dicts.
        """
        closed = []
        while self.open_positions:
            pos = self.open_positions[0]
            result = self.close_position(pos.id, current_price, current_time)
            if result:
                closed.append(result)
        return closed

    def modify_position(self, position_id, sl=None, tp=None):
        """Modify SL/TP on an open position.

        Args:
            position_id: ID of the position to modify.
            sl: New stop loss price (None to keep current).
            tp: New take profit price (None to keep current).

        Returns:
            Modified position dict if found, None otherwise.
        """
        for pos in self.open_positions:
            if pos.id == position_id:
                if sl is not None:
                    pos.sl = sl
                if tp is not None:
                    pos.tp = tp
                return pos.to_dict()
        return None

    def check_sl_tp(self, current_bar):
        """Check if any positions hit their SL or TP on the current bar.

        Args:
            current_bar: Series with high, low, close, datetime.

        Returns:
            List of positions that were closed.
        """
        closed = []
        high = current_bar["high"]
        low = current_bar["low"]
        bar_time = current_bar.get("datetime")

        positions_to_check = self.open_positions.copy()
        for pos in positions_to_check:
            close_price = None

            if pos.direction == "buy":
                if pos.sl is not None and low <= pos.sl:
                    close_price = pos.sl
                elif pos.tp is not None and high >= pos.tp:
                    close_price = pos.tp
            else:  # sell
                if pos.sl is not None and high >= pos.sl:
                    close_price = pos.sl
                elif pos.tp is not None and low <= pos.tp:
                    close_price = pos.tp

            if close_price is not None:
                result = self.close_position(pos.id, close_price, bar_time)
                if result:
                    closed.append(result)

        return closed

    def get_floating_pnl(self, current_price):
        """Calculate total floating P&L for all open positions.

        Args:
            current_price: Current market price.

        Returns:
            Total floating P&L.
        """
        total = sum(
            pos.calculate_floating_pnl(current_price)
            for pos in self.open_positions
        )
        return round(total, 2)

    def get_equity(self, current_price):
        """Calculate account equity (balance + floating P&L).

        Args:
            current_price: Current market price.

        Returns:
            Total equity value.
        """
        return round(self.balance + self.get_floating_pnl(current_price), 2)

    def get_account_state(self, current_price):
        """Get full account state snapshot.

        Args:
            current_price: Current market price.

        Returns:
            Dict with balance, equity, floating_pnl, closed_pnl,
            max_drawdown, win_rate, total_trades.
        """
        equity = self.get_equity(current_price)
        floating = self.get_floating_pnl(current_price)
        closed_pnl = sum(p.pnl for p in self.closed_positions)

        # Calculate stats
        total_trades = len(self.closed_positions)
        winners = sum(1 for p in self.closed_positions if p.pnl > 0)
        win_rate = (winners / total_trades * 100) if total_trades > 0 else 0

        # Max drawdown
        peak = self.initial_balance
        max_dd = 0
        running = self.initial_balance
        for p in self.closed_positions:
            running += p.pnl
            peak = max(peak, running)
            dd = (peak - running) / peak * 100
            max_dd = max(max_dd, dd)

        return {
            "balance": round(self.balance, 2),
            "equity": equity,
            "floating_pnl": floating,
            "closed_pnl": round(closed_pnl, 2),
            "max_drawdown": round(max_dd, 2),
            "win_rate": round(win_rate, 1),
            "total_trades": total_trades,
            "open_positions": len(self.open_positions),
            "initial_balance": self.initial_balance,
        }

    def get_trade_history(self):
        """Get list of all closed trades.

        Returns:
            List of position dicts.
        """
        return [p.to_dict() for p in self.closed_positions]

    def get_open_positions(self):
        """Get list of all open positions.

        Returns:
            List of position dicts.
        """
        return [p.to_dict() for p in self.open_positions]

    def _update_balance_extremes(self):
        """Track peak and trough balance for drawdown calculation."""
        self.max_balance = max(self.max_balance, self.balance)
        self.min_balance = min(self.min_balance, self.balance)

    def reset(self):
        """Reset the execution engine to initial state."""
        self.balance = self.initial_balance
        self.open_positions = []
        self.closed_positions = []
        self.max_balance = self.initial_balance
        self.min_balance = self.initial_balance
